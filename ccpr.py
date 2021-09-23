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
from boto3.dynamodb.types import Decimal
from botocore.exceptions import ClientError
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import difflib
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

__version__ = '0.0.1'

EX = ThreadPoolExecutor(max_workers=5)
BINARY_EXTS = ['.zip', '.docx', '.pptx']


def fatal(msg):
    Console().print('[red bold]ERROR: %s[/]' % msg)
    sys.exit(1)


def git_repo(path=None):
    'get current get repo and path to .git'
    path_parts = (path or os.getcwd()).split(os.sep)
    (repo, git_path) = (None, None)
    for i in range(1, len(path_parts)):
        _path = os.path.join(os.sep, *list(path_parts[0:i+1]))
        _git_path = os.path.join(_path, '.git')
        if os.path.isdir(_git_path):
            repo = path_parts[i]
            git_path = _git_path
            break
    return (repo, git_path)


def current_repo():
    'get current git repo'
    repo = os.environ.get('CCC_REPO')
    if repo is not None:
        return repo
    return git_repo()[0]


def current_branch():
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
    if branch in ['main', 'master']:
        fatal('branch must not be main or master')
    return branch


def last_commit_message():
    'get last commit message in current git repo and branch'
    (repo, git_path) = git_repo()
    message = None
    branch = current_branch()
    log_file = os.path.join(git_path, 'logs', 'refs', 'heads', branch)
    if log_file is None:
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
    data, headers, title=None, colorize=None, counter=None, timeagos=[]
):
    'print table using rich'
    if not isinstance(data, list):
        data = [data]
    console = Console()
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
                val = val.isoformat().split('.')[0]
            elif val is None:
                val = ''
            val = str(val)
            if label in timeagos and val is not None:
                val = timeago.format(val.replace('T', ' '), now)
            if label in colorize:
                for pattern, color in colorize[label].items():
                    if re.match(pattern, val):
                        val = '[%s]%s' % (color, val)
                        break
            row.append(val)
        table.add_row(*row)
    console.print(table)


def json_serial(obj):
    if isinstance(obj, datetime):
        return obj.isoformat().split('.')[0]
    if isinstance(obj, Decimal):
        if obj % 1 > 0:
            return float(obj)
        else:
            return int(obj)
    if isinstance(obj, set):
        return list(obj)
    raise TypeError('type not serializable')


def jq(query, data):
    'jmespath search'
    return jmespath.search(query, data)


def ccapi(method, **kwargs):
    'call boto3 codecommit and cache responses'
    kwargs = dict(kwargs)
    nc = kwargs.pop('nc', None)  # no cache
    join_key = kwargs.pop('_join_key', None)
    cache_secs = int(os.environ.get('CCC_CACHE_SECS', 10))
    cache_dir = os.path.join(
        tempfile.gettempdir(), 'codecommit-cli'
    )
    if not os.path.isdir(cache_dir):
        os.makedirs(cache_dir)
    now = time.time()
    for f in os.listdir(cache_dir):
        fp = os.path.join(cache_dir, f)
        if not os.path.isfile(fp) or not fp.endswith('.cache'):
            continue
        if os.stat(fp).st_mtime < now - cache_secs:
            # print('removing %s' % fp)
            os.remove(fp)
    cache_file = os.path.join(cache_dir, '%s-%s.cache' % (
        method,
        hashlib.sha256(json.dumps(dict(kwargs)).encode('UTF-8')).hexdigest()
    ))
    r = None
    if nc is not True and os.path.isfile(cache_file):
        r = json.loads(open(cache_file, 'r').read())
        # print('read %s' % cache_file)
    else:
        r = None
        try:
            r = getattr(boto3.client('codecommit'), method)(**kwargs)
        except ClientError as e:
            fatal('unable to %s: %s' % (method, e))
        r.pop('ResponseMetadata', None)
        if nc is not True:
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


def print_diff(from_txt, to_txt, name=None, comments=None):
    'print color diff of two strings'
    if comments is None:
        comments = {}
    console = Console(highlight=False)
    if name is not None:
        console.print('[bold white]%s[/]' % name)
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
                _leading += line[i]
            else:
                break
        return _leading

    def print_line(code, from_lc, to_lc, line):
        colors = {
            '-': 'red',
            '+': 'green',
            ' ': 'white'
        }
        for x in '^+-':
            line = line.replace('\x00' + x, '[bold]')
            line = line.replace('\x01', '[/]')
        console.print(
            '[%s]%4s %4s: %s %s[/]' % (
                colors[code], from_lc, to_lc, code, line
            ),
            highlight=False
        )

    for (_from, _to, changed) in diff:
        if not all([_from, _to]):
            console.print(Rule(style=Style(color='white')))
            continue
        (from_lc, from_line, to_lc, to_line) = (*_from, *_to)
        if str(from_lc) != '':
            from_line = leading(from_lines[from_lc - 1]) + from_line
        if str(to_lc) != '':
            to_line = leading(to_lines[to_lc - 1]) + to_line
        if str(from_lc) == '':
            print_line('+', from_lc, to_lc, to_line)
        elif str(to_lc) == '':
            print_line('-', from_lc, to_lc, from_line)
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
@arg('-o', '--open', help='show PRs with OPEN state')
@aliases('ls')
def prs(repo, any=False, closed=False, open=False):
    'list PRs for repo'
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
@arg('-p', '--path', help='filter diffs on matching path')
@aliases('id')
def pr(id, diffs=False, comments=False, path=None):
    'show details for specific PR (colorized diffs with comments etc)'
    if any([comments, path]):
        diffs = True
    'PR details'
    r = cc(
        'get_pull_request', pullRequestId=id, q='pullRequest',
        j=(
            'evaluate_pull_request_approval_rules',
            'pullRequestId|revisionId', {'store_root': True}
        )
    )
    repo = jq('pullRequestTargets[0].repositoryName', r)
    if repo != CURRENT_REPO:
        Console().print('repo: [bold red]%s[/]' % repo)
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
            if not isinstance(rc, list):
                rc = []
            for cd in rc:
                if jq('location.relativeFileVersion', cd) == 'BEFORE':
                    continue
                _path = jq('location.filePath', cd)
                loc = jq('location.filePosition', cd)
                if _path not in _comments:
                    _comments[_path] = {}
                print(cd)
                _comments[_path][loc] = [{
                    'author': _cd['authorArn'].split('/')[-1],
                    'comment': _cd['content']
                } for _cd in cd['comments']]
        path_matches = 0
        for fd in files:
            _path = fd['file']
            if os.path.splitext(_path)[-1] in BINARY_EXTS:
                Console().print('[bold white]%s (binary)[/]' % _path)
                continue
            if path is not None and not re.match('^.*%s.*$' % path, _path):
                continue
            path_matches += 1
            if not all([fd['after'], fd['before']]):
                Console().print('[bold white]%s %s[/]' % (
                    _path, '[red]-deleted-[/]'
                    if fd['after'] is None else '[green]+added+[/]'
                ))
                continue
            (c1, c2) = [
                cc(
                    'get_blob', blobId=bid, repositoryName=repo,
                    nc=True,
                    q='content'
                ).decode('utf-8')
                for bid in [fd['before'], fd['after']]
            ]
            print_diff(c1, c2, _path, _comments)
        if path is not None and path_matches == 0:
            fatal('no paths matching pattern %s in PR' % path)
    # argh prints function response, but we need to reuse it elsewhere
    caller = inspect.stack()[1][3]
    if caller == '_call':
        return
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
    Console().print('[bold green]PR approved[/]')


@arg('id', help='PR ID')
@aliases('x')
def close(id):
    'close PR'
    r = pr(id)
    if r['pullRequestStatus'] == 'CLOSED':
        fatal('PR already closed')
    if Prompt.ask('Confirm?', choices=['yes', 'no'], default='no') != 'yes':
        return
    cc(
        'update_pull_request_status',
        pullRequestId=id,
        pullRequestStatus='CLOSED'
    )
    Console().print('[cyan]PR closed[/]')


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
        repositoryName=jq('pullRequestTargets[0].repositoryName', r)
    )
    Console().print('[cyan]PR merged[/]')


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
def create(repo, title=None):
    'create PR'
    branch = current_branch()
    branches = cc('list_branches', repositoryName=repo)
    if branch not in branches:
        fatal('current branch %s not in repo %s' % (branch, repo))
    if title is None:
        title = Prompt.ask('Enter PR title', default=last_commit_message())
    r = cc(
        'create_pull_request',
        title=title,
        targets=[{
            'repositoryName': repo,
            'sourceReference': branch
        }]
    )
    Console().print('created PR [bold]%s[/]' % jq(
        'pullRequest.pullRequestId', r
    ))


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
        approve, close, create, diff, merge, pr, prs, repos
    ])
    argh.completion.autocomplete(parser)
    parser.dispatch()


if __name__ == '__main__':
    cli()