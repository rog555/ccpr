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
from argh import arg
import boto3
from boto3.dynamodb.types import Decimal
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import jmespath
import json
import os
import re
from rich.console import Console
from rich.table import Table
import tempfile
import time

__version__ = '0.0.1'

EX = ThreadPoolExecutor(max_workers=5)


def ptable(data, headers, title=None, colorize=None, counter=None):
    console = Console()
    table = Table(title=title)
    if colorize is not None:
        for attr in colorize.keys():
            val = colorize[attr]
            (color, pattern) = val.split('=', 1) if '=' in val else (val, None)
            if pattern is not None:
                pattern = re.compile(pattern)
            colorize[attr] = [color, pattern]
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
    for rd in data:
        rc += 1
        row = []
        if counter is not None:
            row.append(
                str(rc) if counter is True else '[%s]%s' % (counter, rc)
            )
        for attr, label in _headers.items():
            val = str(rd.get(attr, ''))
            if label in colorize:
                (color, pattern) = colorize[label]
                if pattern is None or re.match(pattern, val):
                    val = '[%s]%s' % (color, val)
            row.append(val)
        table.add_row(*row)
    console.print(table)


# http://stackoverflow.com/questions/11875770/
# how-to-overcome-datetime-datetime-not-json-serializable-in-python
# see https://github.com/Alonreznik/dynamodb-json/blob/
# master/dynamodb_json/json_util.py
def json_serial(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        if obj % 1 > 0:
            return float(obj)
        else:
            return int(obj)
        return float(obj)
    if isinstance(obj, set):
        return list(obj)
    raise TypeError('type not serializable')


def cccall(method, **kwargs):
    'call boto3 codecommit and cache responses'
    kwargs = dict(kwargs)
    nc = kwargs.pop('nc', None)  # no cache
    cache_secs = int(os.environ.get('CODECOMMIT_CLI_CACHE_SECS', 10))
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
        r = getattr(boto3.client('codecommit'), method)(**kwargs)
        if nc is not True:
            open(cache_file, 'w').write(json.dumps(r, default=json_serial))
            # print('written %s' % cache_file)
    return r


def get(method, **kwargs):
    kwargs = dict(kwargs)
    q = kwargs.pop('q', None)
    j = kwargs.pop('j', None)
    f = kwargs.pop('f', None)

    # get boto3 method
    r = cccall(method, **kwargs)
    data = []

    # apply jmespath transform/query
    if q is not None:
        data = jmespath.search(q, r)

    # automatically get list from first list value attr
    else:
        for k, v in r.items():
            if isinstance(v, list):
                data = r[k]
                break

    # filter attribute
    if f is not None:
        (filter_attr, filter_pattern) = f.split('=', 1)
        _data = []
        for i in range(len(data)):
            v = data[i].get(filter_attr)
            if v is not None and re.match('.*%s.*' % filter_pattern, v):
                _data.append(data[i])
        data = _data

    # join dataset to other boto3 calls
    if j is not None:
        # codecommit boto3 method and attribute to query on
        (join_method, join_attr) = j[0:2]
        # get any other kwargs specified for the boto3 method
        join_kwargs = j[2] if len(j) >= 3 else {}
        # concurrently query boto3 join method
        join_data = list(EX.map(lambda _: cccall(
            join_method,
            **dict(**join_kwargs, **{join_attr: _})
        ), [d[join_attr] for d in data]))
        # join datasets
        lookup_data = {}
        for d in join_data:
            cd = list(d.values())[0]
            lookup_data[cd[join_attr]] = cd
        for i in range(len(data)):
            data[i].update(lookup_data.get(data[i][join_attr], {}))
    return data


def get_repos(prefix, parsed_args, **kwargs):
    return [
        v for v in get('list_repositories', q='repositories[].repositoryName')
        if v.startswith(prefix)
    ]


@arg('pattern', nargs='?', default='')
def repos(pattern):
    'list repos'
    ptable(
        get('list_repositories', p='repositoryName=' + pattern),
        ['repositoryName']
    )


@arg('repo', completer=get_repos)
@arg('-s', '--state', choices=['OPEN', 'CLOSED', 'ALL'])
def prs(repo, state='OPEN'):
    'list PRs for repo'
    kwargs = dict(
        q='pullRequestIds[].{pullRequestId: @}',
        j=('get_pull_request', 'pullRequestId', {}),
        repositoryName=repo
    )
    if state != 'ALL':
        kwargs['pullRequestStatus'] = state
    ptable(
        get('list_pull_requests', **kwargs),
        ['pullRequestId', 'title', 'pullRequestStatus']
    )


def cli():
    parser = argh.ArghParser()
    parser.add_commands([repos, prs])
    argh.completion.autocomplete(parser)
    parser.dispatch()


if __name__ == '__main__':
    cli()
