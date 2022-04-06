#!/usr/bin/env python3
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import argh
from argh import aliases
from argh import arg
import boto3
from botocore.exceptions import ClientError
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import difflib
from fnmatch import fnmatch
import hashlib
import inspect
import jmespath
import json
import os
import re

from rich.console import Console
from rich.prompt import Prompt
from rich.rule import Rule
from rich.style import Style
from rich.table import Table
import sys
import tempfile
import time
import timeago

__version__ = '1.0.2'

EX = ThreadPoolExecutor(max_workers=5)
BINARY_EXTS = ['.zip', '.docx', '.pptx']

global CONSOLE
CONSOLE = None


def set_console(console):
    global CONSOLE
    CONSOLE = console


def get_console(highlight=True):
    global CONSOLE
    if CONSOLE is None:
        set_console(Console(highlight=highlight))
    return CONSOLE


def fatal(msg):
    if os.environ.get('CCPR_FATAL_RAISE', 'FALSE') == 'TRUE':
        raise Exception(msg)
    get_console().print('[red bold]ERROR: %s[/]' % msg)
    sys.exit(1)


def git_repo(path=None):
    'get current get repo and path to .git'
    path_parts = (path or os.getcwd()).split(os.sep)
    (repo, git_path) = (None, None)
    for i in range(1, len(path_parts)):
        _path = os.path.join(os.sep, *list(path_parts[0:i+1]))
        if "win" in sys.platform:
            _path = _path.replace(":", ":" + os.sep)
        _git_path = os.path.join(_path, '.git')
        if os.path.isdir(_git_path):
            repo = path_parts[i]
            git_path = _git_path
            break
    return (repo, git_path)


def current_repo():
    'get current git repo'
    return os.environ.get('CCPR_REPO', git_repo()[0])


def current_branch(master_ok=False):
    'get current git branch'
    (repo, git_path) = git_repo()
    if not all([repo, git_path]):
        fatal('must be in a repo directory')
    head_file = os.path.join(git_path, 'HEAD')
    branch = None
    with open(head_file, 'r') as fh:
        for line in fh.read().splitlines():
            if line.startswith('ref: refs/heads/'):
                branch = line.split('/')[-1]
    if branch is None:
        fatal('no branch found in repo %s' % repo)
    if master_ok is False and branch in ['main', 'master']:
        fatal('branch must not be main or master')
    return branch


def last_commit_message():
    'get last commit message in current git repo and branch'
    (repo, git_path) = git_repo()
    message = None
    branch = current_branch()
    log_file = os.path.join(git_path, 'logs', 'refs', 'heads', branch)
    if not os.path.isfile(log_file):
        return None
    with open(log_file, 'r') as fh:
        for line in fh.read().splitlines():
            if 'commit:' not in line:
                continue
            parts = line.split(None, 7)
            if len(parts) == 8 and parts[6] == 'commit:':
                message = parts[7]
    return message


CURRENT_REPO = current_repo()


def ptable(
    data, headers, title=None, colorize=None, counter=None, timeagos=None
):
    'print table using rich'
    if not isinstance(data, list):
        data = [data]
    table = Table(title=title, title_justify='left')
    if colorize is not None:
        for attr in colorize.keys():
            vals = colorize[attr]
            colorize[attr] = {}
            if not isinstance(vals, list):
                vals = [vals]
            for i in range(len(vals)):
                if '=' in vals[i]:
                    (pattern, color) = vals[i].rsplit('=', 1)
                    colorize[attr][re.compile(pattern)] = color
    else:
        colorize = {}

    if not isinstance(timeagos, list):
        timeagos = []
    if counter is not None:
        table.add_column('#' if counter is True else '[%s]#' % counter)

    _headers = {}
    for h in headers:
        (label, attr) = h.split('=', 1) if '=' in h else (h, h)
        _headers[attr] = label
        table.add_column(label)
    rc = 0
    now = datetime.now()
    for rd in data:
        rc += 1
        row = []
        if counter is not None:
            row.append(
                str(rc) if counter is True else '[%s]%s' % (counter, rc)
            )
        for attr, label in _headers.items():
            val = jq(attr, rd)
            if isinstance(val, datetime):
                val = dt_timestamp(val)
            elif val is None:
                val = ''
            val = str(val)
            if label in timeagos and val is not None and val.strip() != '':
                val = timeago.format(val.replace('T', ' '), now)
            if label in colorize:
                for pattern, color in colorize[label].items():
                    if re.match(pattern, val):
                        val = '[%s]%s' % (color, val)
                        break
            if rd.get('_dim') is True:
                val = '[dim]%s[/]' % val
            row.append(val)
        table.add_row(*row)
    get_console().print(table)


def aws_link(path, _print=True, name=None):
    if path is None:
        return None  # pragma: no cover
    region = boto3.session.Session().region_name
    url = path
    if path.startswith('/'):
        url = 'https://%s.console.aws.amazon.com/codesuite' % region
        url += path
        url += ('?' if '?' not in path else '&') + 'region=' + region
    if name is not None:
        return '[link=%s]%s[/]' % (url, name)
    if _print is True:
        get_console().print('[cyan]link: [underline]%s[/][/]' % url)
    return url


def dt_timestamp(dt):
    return dt.isoformat().split('.')[0].replace('T', ' ')


def json_serial(obj):
    if isinstance(obj, datetime):
        return dt_timestamp(obj)
    if isinstance(obj, set):
        return list(obj)


def jq(query, data):
    'jmespath search'
    return jmespath.search(query, data)


def ccapi(method, **kwargs):
    'call boto3 codecommit and cache responses'
    kwargs = dict(kwargs)
    _client = kwargs.pop('client', 'codecommit')
    cache_secs = kwargs.pop('cache_secs', 20)
    if 'CCPR_CACHE_SECS' in os.environ:
        cache_secs = int(os.environ['CCPR_CACHE_SECS'])

    join_key = kwargs.pop('_join_key', None)
    cache_dir = os.path.join(
        tempfile.gettempdir(), 'ccpr'
    )
    if not os.path.isdir(cache_dir):
        os.makedirs(cache_dir)  # pragma: no cover
    now = time.time()
    for f in os.listdir(cache_dir):
        fp = os.path.join(cache_dir, f)
        if not os.path.isfile(fp) or not fp.endswith('.cache'):
            continue  # pragma: no cover
        # sometimes this fails when concurrent as already removed
        try:
            if os.stat(fp).st_mtime < now - cache_secs:
                # print('removing %s' % fp)
                os.remove(fp)
        except Exception:  # pragma: no cover
            pass
    cache_file = os.path.join(cache_dir, '%s-%s.cache' % (
        method,
        hashlib.sha256(json.dumps(dict(kwargs)).encode('UTF-8')).hexdigest()
    ))
    r = None
    if cache_secs > 0 and os.path.isfile(cache_file):
        r = json.loads(open(cache_file, 'r').read())
    else:
        r = None
        try:
            r = getattr(boto3.client(_client), method)(**kwargs)
        except ClientError as e:
            fatal('unable to %s: %s' % (method, e))
        r.pop('ResponseMetadata', None)
        if cache_secs > 0:
            json_txt = json.dumps(r, default=json_serial)
            # print(json_txt)
            open(cache_file, 'w').write(json_txt)
            # print('written %s' % cache_file)
    if join_key is not None:
        r['_join_key'] = join_key
    return r


def cc(method, **kwargs):
    'perform codecommit api calls with joins, filtering etc'

    kwargs = dict(kwargs)
    q = kwargs.pop('q', None)  # query
    j = kwargs.pop('j', None)  # join(s)
    f = kwargs.pop('f', None)  # filter

    # get boto3 method
    r = ccapi(method, **kwargs)
    data = []

    # apply jmespath transform/query
    if q is not None:
        data = jq(q, r)

    # automatically get list from first list value attr
    else:
        for k, v in r.items():
            if isinstance(v, list):
                data = r[k]
                break
        if data == [] and isinstance(r, dict):
            data = r

    # filter attribute
    if f is not None:
        (filter_attr, filter_pattern) = f.split('=', 1)
        _data = []
        for i in range(len(data)):
            v = data[i].get(filter_attr)
            if v is not None and re.match('.*%s.*' % filter_pattern, v):
                _data.append(data[i])
        data = _data

    listified = False
    if j is not None:
        if not isinstance(data, list):
            data = [data]
            listified = True

    # join dataset to other boto3 calls
    def _join_data(join_idx, _j):
        # codecommit boto3 method and attributes to query on
        (join_method, join_attrs) = _j[0:2]
        join_kwargs = []
        store_root = None
        for i in range(len(data)):
            jd = _j[2].copy() if len(_j) >= 3 else {}
            if 'cache_secs' in kwargs:
                jd['cache_secs'] = kwargs['cache_secs']  # pragma: no cover
            # store_root used to store root of lookup_data rather than
            # specific sub entity
            store_root = jd.pop('store_root', join_idx > 0)
            join_key = []
            for join_query in join_attrs.split('|'):
                join_attr = join_query.split('.')[-1]
                jd[join_attr] = jq(join_query, data[i])
                join_key.append(jd[join_attr])
            jd['_join_key'] = '|'.join(join_key)
            data[i]['_join_key'] = jd['_join_key']
            join_kwargs.append(jd)

        # concurrently query boto3 join method
        join_data = list(EX.map(lambda _: ccapi(
            join_method,
            **_
        ), join_kwargs))

        # join datasets
        lookup_data = {}
        for d in join_data:
            entity_keys = [k for k in d.keys() if not k.startswith('_')]
            lookup_data[d['_join_key']] = (
                d if store_root is True else d[entity_keys[0]]
            )
        for i in range(len(data)):
            data[i].update(lookup_data.get(data[i]['_join_key'], {}))

    # perform join(s)
    if j is not None:
        if not isinstance(j, list):
            j = [j]
        for i in range(len(j)):
            _join_data(i, j[i])

    if listified is True:
        return data[0]

    return data


def print_diff(
    from_txt, to_txt, name=None, comments=None, print_name=True,
    print_modified=False
):
    'print color diff of two strings'
    console = get_console()
    if comments is None:
        comments = {}
    if name is not None and print_name is True:
        meta_msg = '[green]+modified+[/] ' if print_modified else ''
        if name in comments:
            meta_msg += '[cyan] %s comment(s)[/]' % len(comments[name])
        console.print('[bold white]%s %s[/]' % (name, meta_msg))
    from_lines = from_txt.splitlines()
    from_lines_stripped = [line.lstrip().rstrip() for line in from_lines]
    to_lines = to_txt.splitlines()
    to_lines_stripped = [line.lstrip().rstrip() for line in to_lines]
    diff = list(difflib._mdiff(
        from_lines_stripped, to_lines_stripped, context=3
    ))

    def leading(line):
        _leading = ''
        for i in range(len(line)):
            if line[i] in ' \t':
                _leading += line[i]  # pragma: no cover
            else:
                break
        return _leading

    def print_line(code, from_lc, to_lc, line):
        colors = {
            '-': 'red',
            '+': 'green',
            ' ': 'white'
        }

        # some issues replacing formats when line ends with /
        for x in '^+-':
            line = line.replace('\x00' + x, '')  # replace with [bold]
            line = line.replace('\x01', '')  # replace with [/]
        console.print(
            '[%s]%4s %4s: %s %s' % (
                colors[code], from_lc, to_lc, code, line
            ),
            highlight=False
        )

    for (_from, _to, changed) in diff:
        if not all([_from, _to]):
            console.print(Rule(style=Style(color='white')))  # pragma: no cover
            continue  # pragma: no cover
        (from_lc, from_line, to_lc, to_line) = (*_from, *_to)
        if str(from_lc) != '':
            from_line = leading(from_lines[from_lc - 1]) + from_line
        if str(to_lc) != '':
            to_line = leading(to_lines[to_lc - 1]) + to_line
        if str(from_lc) == '':
            print_line('+', from_lc, to_lc, to_line)
        elif str(to_lc) == '':
            print_line('-', from_lc, to_lc, from_line)  # pragma: no cover
        elif changed is True:
            print_line('-', from_lc, '', from_line)
            print_line('+', '', to_lc, to_line)
        else:
            print_line(' ', from_lc, to_lc, to_line)
        if name in comments:
            cd = comments[name].get(to_lc)
            if cd is not None:
                ptable(cd, ['author', 'comment'], colorize={
                    'author': '.*=cyan', 'comment': '.*=cyan'
                })


def enrich_pr(d):
    'enrich PR data with stuff like approval status to pr/ls'
    satisfied = jq('length(evaluation.approvalRulesSatisfied)', d)
    not_satisfied = jq('length(evaluation.approvalRulesNotSatisfied)', d)
    d['approvalStatus'] = (
        '[cyan]Approved[/]' if jq('evaluation.approved', d) else
        '[red]%s of %s rules satisfied[/]' % (
            satisfied, satisfied + not_satisfied
        )
    )
    d['author'] = d['authorArn'].split('/')[-1]


def repos_completer(prefix, parsed_args, **kwargs):
    'command line completer for listing repos'
    return [
        v for v in cc('list_repositories', q='repositories[].repositoryName')
        if v.startswith(prefix)
    ]


def pr_files_completer(prefix, parsed_args, **kwargs):
    'command line completer for PR files'
    r = cc(
        'get_pull_request', pullRequestId=(
            parsed_args if isinstance(parsed_args, str)
            else parsed_args.id
        ), q='pullRequest'
    )
    (repo, before, after) = jq(
        'pullRequestTargets[0].'
        + '[repositoryName, destinationCommit, sourceCommit]',
        r
    )
    files = jq('[*].afterBlob.path', cc(
        'get_differences',
        repositoryName=repo,
        beforeCommitSpecifier=before,
        afterCommitSpecifier=after,
    ))
    if isinstance(parsed_args, str):
        return (repo, files, before, after)
    return [
        f for f in files if f.startswith(prefix)
    ]


@arg('-f', '--filter', help='filter repos on pattern')
@aliases('r')
def repos(filter=None):
    'list repos'
    ptable(
        cc(
            'list_repositories',
            f='repositoryName=%s' % filter if filter else None
        ),
        ['name=repositoryName']
    )


@arg(
    'repo',
    completer=repos_completer,
    nargs='?' if CURRENT_REPO else None,
    default=CURRENT_REPO,
    help='repo name'
)
@arg('-a', '--any', help='show PRs with any state')
@arg('-c', '--closed', help='show PRs with CLOSED state')
@aliases('ls')
def prs(repo, any=False, closed=False):
    'list PRs for repo - OPEN by default'
    state = 'CLOSED' if closed else 'any' if any else 'OPEN'
    kwargs = dict(
        q='pullRequestIds[].{pullRequestId: @}',
        j=[
            ('get_pull_request', 'pullRequestId'),
            ('evaluate_pull_request_approval_rules',
             'pullRequestId|revisionId')
        ],
        repositoryName=repo
    )
    if state != 'any':
        kwargs['pullRequestStatus'] = state
    data = cc('list_pull_requests', **kwargs)
    if len(data) == 0:
        fatal('no PRs with %s state in repo %s' % (state, repo))
    for i in range(len(data)):
        enrich_pr(data[i])
    ptable(
        data,
        [
            'id=pullRequestId',
            'title',
            'author',
            'activity=lastActivityDate',
            'status=pullRequestStatus',
            'approvals=approvalStatus'
        ],
        timeagos=['activity']
    )


@arg('-d', '--diffs', help='show differences')
@arg('-c', '--comments', help='show diff comments')
@arg('-f', '--file', help='filter diff files on matching file pattern')
@aliases('id')
def pr(id, diffs=False, comments=False, file=None):
    'show details for specific PR (colorized diffs with comments etc)'
    console = get_console()
    if any([comments, file]):
        diffs = True
    r = cc(
        'get_pull_request', pullRequestId=id, q='pullRequest',
        j=(
            'evaluate_pull_request_approval_rules',
            'pullRequestId|revisionId', {'store_root': True}
        )
    )
    repo = jq('pullRequestTargets[0].repositoryName', r)
    if repo != CURRENT_REPO:
        console.print('repo: [bold red]%s[/]' % repo)
    enrich_pr(r)
    ptable(r, [
        'id=pullRequestId',
        'title',
        'author',
        'activity=lastActivityDate',
        'status=pullRequestStatus',
        'approvals=approvalStatus'
    ], timeagos=['activity'])
    rd = cc(
        'get_differences',
        repositoryName=repo,
        beforeCommitSpecifier=jq('pullRequestTargets[0].destinationCommit', r),
        afterCommitSpecifier=jq('pullRequestTargets[0].sourceCommit', r)
    )
    files = []
    for d in rd:
        _path = jq('afterBlob.path || beforeBlob.path', d)
        change = {
            'D': 'deleted',
            'A': 'added',
            'M': 'modified'
        }[d['changeType']]
        files.append({
            'file': _path,
            'after': jq('afterBlob.blobId', d),
            'before': jq('beforeBlob.blobId', d),
            'change': change
        })
    if diffs is False:
        ptable(
            files, ['file', 'change'], title='changes:', counter=True,
            colorize={'change': ['deleted=red', '.*=green']}
        )
    else:
        _comments = {}
        if comments is True:
            rc = cc('get_comments_for_pull_request', pullRequestId=id)
            pr_comments = []
            if not isinstance(rc, list):
                rc = []  # pragma: no cover
            for cd in rc:
                _comments_data = [{
                    'author': _cd['authorArn'].split('/')[-1],
                    'comment': _cd['content']
                } for _cd in cd['comments']]
                if 'location' not in cd:
                    pr_comments += _comments_data
                elif jq('location.relativeFileVersion', cd) == 'AFTER':
                    _path = jq('location.filePath', cd)
                    loc = jq('location.filePosition', cd)
                    if _path not in _comments:
                        _comments[_path] = {}
                    if loc not in _comments[_path]:
                        _comments[_path][loc] = []
                    _comments[_path][loc] += _comments_data
            if len(pr_comments) > 0:
                ptable(pr_comments, ['author', 'comment'], colorize={
                    'author': '.*=cyan', 'comment': '.*=cyan'
                }, title='PR comments')
        path_matches = 0

        def _get_content(bid):
            if bid is None:
                return ''
            return cc(
                'get_blob', blobId=bid, repositoryName=repo,
                q='content',
                cache_secs=0
            ).decode('utf-8')

        for fd in files:
            _path = fd['file']
            if os.path.splitext(_path)[-1] in BINARY_EXTS:
                console.print('[bold white]%s (binary)[/]' % _path)
                continue
            if file is not None and not re.match('^.*%s.*$' % file, _path):
                continue
            path_matches += 1
            (before, after) = (fd.get('before'), fd.get('after'))
            if not all([before, after]):
                comments_msg = (
                    ' [cyan]%s comment(s)[/]' % len(_comments[_path])
                    if _path in _comments else ''
                )
                console.print('[bold white]%s %s%s[/]' % (
                    _path, '[red]-deleted-[/]'
                    if after is None else '[green]+added+[/]',
                    comments_msg
                ))
            if all([before, after]) or all([file, after]):
                print_diff(
                    _get_content(before), _get_content(after), _path,
                    _comments,
                    print_name=all([before, after]),
                    print_modified=all([before, after])
                )
        if file is not None and path_matches == 0:
            fatal("no files matching pattern '%s' in PR" % file)
    # argh prints function response, but we need to reuse it elsewhere
    caller = inspect.stack()[1][3]
    if caller == '_call':
        return  # pragma: no cover
    return r


@arg('id', help='PR ID')
@aliases('a')
def approve(id):
    'approve PR'
    r = pr(id)
    if r['pullRequestStatus'] == 'CLOSED':
        fatal('PR already closed, unable to approve')
    cc(
        'update_pull_request_approval_state',
        pullRequestId=id,
        revisionId=jq('revisionId', r),
        approvalState='APPROVE'
    )
    get_console().print('[bold green]PR approved[/]')


@arg('id', help='PR ID')
@aliases('x')
def close(id, confirm=False):
    'close PR'
    r = pr(id)
    if r['pullRequestStatus'] == 'CLOSED':
        fatal('PR already closed')
    if (confirm is False
       and Prompt.ask('Confirm?', choices=['yes', 'no'], default='no')
       != 'yes'):
        return  # pragma: no cover
    cc(
        'update_pull_request_status',
        pullRequestId=id,
        pullRequestStatus='CLOSED',
        cache_secs=0
    )
    get_console().print('[cyan]PR closed[/]')


@arg('id', help='PR ID')
@arg(
    '-s', '--strategy', choices=['fast_forward', 'squash', 'three_way'],
    help='merge strategy'
)
@aliases('m')
def merge(id, strategy='squash'):
    'merge PR'
    r = pr(id)
    if r['pullRequestStatus'] == 'CLOSED':
        fatal('PR already closed')
    if jq('evaluation.approved', r) is not True:
        fatal('PR not approved')
    cc(
        'merge_pull_request_by_%s' % strategy,
        pullRequestId=id,
        repositoryName=jq('pullRequestTargets[0].repositoryName', r),
        cache_secs=0
    )
    get_console().print('[cyan]PR merged[/]')


@arg(
    'repo',
    completer=repos_completer,
    nargs='?' if CURRENT_REPO else None,
    default=CURRENT_REPO,
    help='repo name'
)
@arg(
    '-t', '--title',
    help='title of PR, defaults to last commit message on branch'
)
@aliases('c')
def create(repo, title=None, branch=None):
    'create PR'
    branch = branch or current_branch()
    branches = cc('list_branches', repositoryName=repo)
    if branch not in branches:
        fatal('current branch %s not in repo %s' % (branch, repo))
    title = title or Prompt.ask(
        'Enter PR title', default=last_commit_message()
    )
    r = cc(
        'create_pull_request',
        title=title,
        targets=[{
            'repositoryName': repo,
            'sourceReference': branch
        }],
        cache_secs=0
    )
    pr_id = jq('pullRequest.pullRequestId', r)
    get_console().print('[cyan]created PR [bold]%s[/]' % pr_id)
    aws_link('/codecommit/repositories/%s/pull-requests/%s/changes' % (
        repo, pr_id
    ))


@arg('id', help='PR ID')
@arg('content', help='comment content')
@arg('-f', '--file', help='file comment', completer=pr_files_completer)
@arg('-l', '--lineno', help='line number of file', type=int)
@aliases('C')
def comment(id, content, file=None, lineno=None):
    'comment on PR, general if file and lineno not specified'
    if any([file, lineno]) and not all([file, lineno]):
        fatal('--lineno required with --file')
    (repo, files, before, after) = pr_files_completer('', id)
    if file is not None and file not in files:
        fatal("file '%s' not in list of PR files:\n%s" % (
            file, '\n'.join([
                '[white]%s] %s[/]' % (i + 1, files[i])
                for i in range(len(files))
            ])
        ))
    msg = 'general comment added'
    kwargs = {
        'pullRequestId': id,
        'repositoryName': repo,
        'beforeCommitId': before,
        'afterCommitId': after,
        'content': content
    }
    if file is not None:
        msg = 'file comment added'
        kwargs['location'] = {
            'filePath': file,
            'filePosition': lineno,
            'relativeFileVersion': 'AFTER'
        }
    cc('post_comment_for_pull_request', **kwargs, cache_secs=0)
    get_console().print('[cyan]%s[/]' % msg)


@arg('str', help='string to grep')
@arg('path', help='path within repo')
@arg('-b', '--branch', help='defaults to master')
@arg('-R', '--recursive', help='recursive search')
@arg('-r', '--repo', help='comma sep list or current')
@arg('-i', '--insensitive', help='case insensitive', action='store_true')
@arg('-v', '--verbose', help='verbose', action='store_true')
@aliases('g')
def grep(
    str, path, branch=None, repo=None,
    recursive=False, insensitive=False, verbose=False
):
    'grep the remote repo(s)'
    console = get_console(False)
    if path in ['/', '.', '.*']:
        path = '/*'
    if not path.startswith('/'):
        path = '/' + path
    if branch is None:
        branch = 'master'
    (path, fpat) = os.path.split(path)
    if repo is None:  # pragma: no cover
        repo = CURRENT_REPO
    if repo is None:  # pragma: no cover
        fatal('--repo must be specified')

    def _repo_prefix(r):
        return '' if r == repo else '[cyan]%s[/]: ' % r

    def _no_match(r, f):
        if verbose is True:
            console.print(
                '%s[grey58]%s:    no match[/]' % (_repo_prefix(r), f)
            )

    def _file_grep(r, f_bid):
        (f, bid) = f_bid
        if bid is None:  # pragma: no cover
            return _no_match(r, f)
        f = '/' + f
        lines = cc(
            'get_blob', blobId=bid, repositoryName=r,
            q='content',
            cache_secs=120
        )
        if not isinstance(lines, bytes) or lines is None:  # pragma: no cover
            return _no_match(r, f)
        lines = lines.decode('utf-8')
        match = False
        for line in lines.split():
            _str = str
            if insensitive is True:
                _str = _str.lower()
                line = line.lower()
            if _str in line:
                line = line.replace(str, '[green]%s[/]' % str)
                console.print('%s%s:    %s' % (_repo_prefix(r), f, line))
                match = True
        if match is False:
            _no_match(r, f)
        return

    def _grep(r, f):
        kwargs = {
            'repositoryName': r,
            'commitSpecifier': branch,
            'folderPath': f,
            'q': (
                "[subFolders[].absolutePath,"
                + "files[?fileMode=='NORMAL'].[absolutePath,blobId]]"
            )
        }
        (dirs, _files) = cc('get_folder', **kwargs)
        files = []
        for f_bid in _files:
            if fnmatch(f_bid[0], fpat) is False:
                _no_match(r, f_bid[0])
                continue
            files.append(f_bid)
        list(EX.map(lambda _: _file_grep(r, _), files))
        if recursive is True and len(dirs) > 0:
            list(EX.map(lambda _: _grep(r, _), dirs))
        return

    repos = []
    if '?' in repo or '*' in repo or ',' in repo:
        _repos = repo.split(',')
        _all_repos = cc('list_repositories', q='repositories[].repositoryName')
        for rpat in _repos:
            for r in _all_repos:
                if r == rpat or fnmatch(r, rpat):
                    repos.append(r)
    else:
        repos = [repo]

    for r in repos:
        _grep(r, path)


@arg(
    'repo',
    completer=repos_completer,
    nargs='?' if CURRENT_REPO else None,
    default=CURRENT_REPO,
    help='repo name'
)
@arg('-b', '--branch', help='defaults to master')
@arg('-n', '--name', help='pipeline name')
@arg('-m', '--master', help='use master branch', action='store_true')
@arg('-c', '--commits', help='show commit history', action='store_true')
@arg('-a', '--absolute', help='show absolute dates', action='store_true')
@aliases('p')
def pipeline(
    repo, branch=None, name=None, master=False, commits=False, absolute=False
):
    'show codepipeline status'

    if master is True:
        branch = 'master'

    if name is None:
        name = '%s_%s' % (repo, branch or current_branch(True))

    r = cc(
        'get_pipeline_state',
        name=name,
        client='codepipeline',
        q='''stageStates[].{
    stage:   stageName,
    status:  latestExecution.status,
    updated: actionStates[0].latestExecution.lastStatusChange,
    summary: actionStates[0].latestExecution.summary,
    _url:    actionStates[0].latestExecution.externalExecutionUrl,
    _error:  actionStates[0].latestExecution.errorDetails.message,
    _action: actionStates[0].actionName,
    _exec:   actionStates[0].latestExecution,
    _pid:    latestExecution.pipelineExecutionId
}'''
    )

    # get action executions for all pipeline executions in response
    pids = {d['_pid']: {} for d in r}
    # sum flattens list of lists
    _action_executions = sum(EX.map(lambda _: cc(
        'list_action_executions', pipelineName=name,
        filter={'pipelineExecutionId': _},
        client='codepipeline'
    ), pids.keys()), [])

    sources = {}
    builds = {}
    query = '''{
        id: output.executionResult.externalExecutionId,
        url: output.executionResult.externalExecutionUrl,
        summary: output.executionResult.externalExecutionSummary,
        updated: lastUpdateTime
    }'''
    for d in _action_executions:
        pid = d['pipelineExecutionId']
        stage = d['stageName']
        action = d['actionName']
        if stage not in pids[pid]:
            pids[pid][stage] = {}
        _input = jq('input.actionTypeId.[owner, category, provider]', d)
        pids[pid][stage][action] = ' '.join(_input)
        if _input[1] == 'Source':
            sources[pid] = jq(query, d)
        elif _input[1] == 'Build':
            builds[pid] = jq(query, d)

    c1 = re.compile(r'(Approved by arn:aws:\S+)')
    dim = False
    has_error = False
    last_commit = None

    for i in range(len(r)):

        # replace iam arn with user
        summary = (r[i]['summary'] or '').strip()
        for m in c1.findall(summary):
            u = '[green]%s[/]' % m.split('/')[-1]
            summary = summary.replace(m, 'Approved by %s' % u)

        # add error column
        r[i]['error'] = None
        if r[i]['_error'] is not None:
            r[i]['error'] = aws_link(r[i]['_url'], name=r[i]['_error'])
            has_error = True

        # add commit link
        source = sources.get(r[i]['_pid'])
        if source is not None:
            r[i]['commit'] = (
                aws_link(source['url'], name='#' + source['id'][-8:])
            )

        # update summary with action and dim subsequent records
        _status = r[i]['status']
        if _status in ['InProgress', 'Failed']:
            # construct query to lookup the input.actionTypeId from pids
            _summary = jq(
                '.'.join(
                    ['"%s"' % r[i][a] for a in ['_pid', 'stage', '_action']]
                ),
                pids
            )
            if _summary == 'AWS Approval Manual':
                (_color, _summary) = (
                    ('cyan', 'InProgress') if _status == 'InProgress' else
                    ('red', 'Rejected')
                )
                summary += '%s[%s italic]%s%s[/]' % (
                    ' ' if summary != '' else '',
                    _color,
                    _summary,
                    '...' if _status == 'InProgress' else ''
                )

        r[i]['summary'] = summary
        if last_commit is not None and source['id'] != last_commit:
            dim = True
        if dim is True:
            r[i]['_dim'] = True
        last_commit = source['id']

    timeagos = None if absolute is True else ['updated']
    aws_link('/codepipeline/pipelines/%s/view' % name)
    headers = ['stage', 'status', 'updated', 'commit', 'summary']
    if has_error is True:
        headers += ['error']
    ptable(r, headers, colorize={
        'status': ['Succeeded=green', 'InProgress=cyan', 'Failed=red'],
        'error': ['.*=red']
    }, timeagos=timeagos)

    if commits is True:
        data = [{
            'commit': aws_link(
                sources[pid]['url'], name='#' + sources[pid]['id'][-8:]
            ),
            'build': aws_link(
                builds[pid]['url'], name='#' + builds[pid]['id'][-8:]
            ),
            'updated': sources[pid]['updated'],
            'summary': sources[pid]['summary']
        } for pid in sources.keys()]
        get_console().print('commits:')
        ptable(
            data, ['commit', 'updated', 'build', 'summary'], counter=True,
            timeagos=timeagos
        )


@aliases('d')
def diff(file1, file2):
    'diff two local files'
    print_diff(
        open(file1, 'r').read(),
        open(file2, 'r').read()
    )


def cli():
    parser = argh.ArghParser()
    parser.description = 'AWS CodeCommit PR CLI'
    parser.add_commands([
        approve, create, close, comment, diff, grep,
        merge, pipeline, pr, prs, repos
    ])
    argh.completion.autocomplete(parser)
    parser.dispatch()


if __name__ == '__main__':
    cli()  # pragma: no cover
