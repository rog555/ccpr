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
from collections import namedtuple
from datetime import datetime
from io import StringIO
import json
import os
import pytest
from rich.console import Console
from rich.table import Table
import sys
from unittest.mock import patch

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(ROOT_DIR, 'tests', 'data')
sys.path.append(ROOT_DIR)

import ccpr  # noqa: E402
from tests.mock_boto3 import mock_boto3  # noqa: E402
os.environ['CCPR_FATAL_RAISE'] = 'TRUE'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'


def _table(columns, rows, title=None):
    table = Table(title=title, title_justify='left')
    for column in columns:
        table.add_column(column)
    for row in rows:
        table.add_row(*row)
    console = Console(file=StringIO())
    console.print(table)
    return console.file.getvalue()


def get_output():
    output = ccpr.get_console().file.getvalue()
    return '\n'.join(_.rstrip() for _ in output.splitlines()) + '\n'


def get_pr_output(prid, state='OPEN', approvals='Approved', diff=False):

    def _comment(txt):
        return _table(['author', 'comment'], [['foo@bar.com', txt]])

    output = (
        'repo: repo1\n'
        + _table(
            ['id', 'title', 'author', 'activity', 'status', 'approvals'],
            [[
                prid, 'title%s' % prid,
                'foo@bar.com', 'just now', state, approvals
            ]]
        )
    )
    if diff is False:
        output += 'changes:\n' + _table(
            ['#', 'file', 'change'],
            [
                ['1', 'foo/bar.txt', 'modified'],
                ['2', 'foo/bar.zip', 'deleted'],
                ['3', 'foo/foo.txt', 'added']
            ]
        )
    else:
        output += (
            'PR comments\n'
            + _comment('general comment')
            + 'foo/bar.txt +modified+  1 comment(s)\n'
            + '   1    1:   line1\n'
            + _comment('line1 comment')
            + '''   2     : - line2
        2: + liNe2
   3     : - line3
        3: + line4
        4: + line5
foo/bar.zip (binary)
foo/foo.txt +added+
        1: + line1
        2: + line2
''')
    return output


def test_fatal():
    os.environ['CCPR_FATAL_RAISE'] = 'FALSE'
    # ccpr.set_console(None)
    with pytest.raises(SystemExit):
        ccpr.fatal('foo')
    os.environ['CCPR_FATAL_RAISE'] = 'TRUE'


def test_git_files(tmp_path):
    rd = tmp_path / 'somerepo'
    rd.mkdir()
    with patch('os.getcwd') as m:
        m.return_value = str(rd)
        with pytest.raises(Exception) as e:
            ccpr.current_branch()
        assert str(e.value) == 'must be in a repo directory'
    gd = rd / '.git'
    gd.mkdir()
    fd = gd / 'foo'
    fd.mkdir()
    hf = gd / 'HEAD'
    hf.write_text('stuff')
    with patch('os.getcwd') as m:
        m.return_value = str(rd)
        with pytest.raises(Exception) as e:
            ccpr.current_branch()
        assert str(e.value) == 'no branch found in repo somerepo'
    hf = gd / 'HEAD'
    hf.write_text('ref: refs/heads/somebranch')
    with patch('os.getcwd') as m:
        m.return_value = str(fd)
        assert ccpr.current_repo() == 'somerepo'
        assert ccpr.current_branch() == 'somebranch'
    hf.unlink()
    hf.write_text('ref: refs/heads/master')
    with patch('os.getcwd') as m:
        m.return_value = str(fd)
        with pytest.raises(Exception) as e:
            ccpr.current_branch()
        assert str(e.value) == 'branch must not be main or master'
    hf.unlink()
    hf.write_text('ref: refs/heads/somebranch')
    ld = gd / 'logs' / 'refs' / 'heads'
    ld.mkdir(parents=True)
    lf = ld / 'somebranch'
    with patch('os.getcwd') as m:
        m.return_value = str(fd)
        assert ccpr.last_commit_message() is None
        lf.write_text(
            'stuff\n0 1 2 3 commit: 5 foo: bar\n0 1 2 3 4 5 commit: somecommit'
        )
        assert ccpr.last_commit_message() == 'somecommit'


def test_json_serial():
    dt = datetime.now()
    ts = dt.isoformat().split('.')[0]
    assert json.dumps({
        'a': dt,
        'b': 1,
        'c': set([1, 2])
    }, default=ccpr.json_serial) == (
        '{"a": "%s", "b": 1, "c": [1, 2]}' % ts
    )


def test_ptable():
    ccpr.set_console(Console(file=StringIO()))
    ccpr.ptable({'a': 'a1'}, ['a', 'b'], colorize={
        'b': 'red'
    })
    output = get_output()
    print(output)
    assert output == _table(
        ['a', 'b'], [
            ['a1', '']
        ]
    )


@mock_boto3
def test_completers():
    assert ccpr.repos_completer('repo', None) == ['repo0', 'repo1', 'repo2']
    parsed_args = namedtuple('foo', 'id')
    parsed_args.id = '1'
    assert ccpr.pr_files_completer('', parsed_args) == [
        'foo/bar.txt', 'foo/foo.txt'
    ]


@mock_boto3
def test_repos():
    ccpr.set_console(Console(file=StringIO()))
    ccpr.repos(filter='repo')
    assert get_output() == _table(['name'], [['repo0'], ['repo1'], ['repo2']])


@mock_boto3
def test_prs():
    os.environ['CCPR_CACHE_SECS'] = '0'
    ccpr.set_console(Console(file=StringIO()))
    ccpr.prs('repo1')
    assert get_output() == _table(
        ['id', 'title', 'author', 'activity', 'status', 'approvals'],
        [
            ['1', 'title1', 'foo@bar.com', 'just now', 'OPEN', 'Approved'],
            ['2', 'title2', 'foo@bar.com', 'just now', 'CLOSED',
             '1 of 2 rules satisfied']
        ]
    )
    with pytest.raises(Exception) as e:
        ccpr.prs('repo1', closed=True)
    assert str(e.value) == 'no PRs with CLOSED state in repo repo1'
    with pytest.raises(Exception) as e:
        ccpr.prs('repo3')
    assert str(e.value).startswith(
        'unable to list_pull_requests: '
        + 'An error occurred (RepositoryDoesNotExistException)'
    )


@mock_boto3
def test_pr_simple():
    os.environ['CCPR_CACHE_SECS'] = '0'
    ccpr.set_console(Console(file=StringIO()))
    ccpr.pr('1')
    assert get_output() == get_pr_output('1')
    with pytest.raises(Exception) as e:
        ccpr.pr('1', file='baz')
    assert str(e.value) == "no files matching pattern 'baz' in PR"


@mock_boto3
def test_pr_diff_comments():
    os.environ['CCPR_CACHE_SECS'] = '0'
    ccpr.set_console(Console(file=StringIO()))
    ccpr.pr('1', comments=True, file='.txt')
    assert get_output() == get_pr_output('1', diff=True)


@mock_boto3
def test_approve():
    os.environ['CCPR_CACHE_SECS'] = '0'
    ccpr.set_console(Console(file=StringIO()))
    ccpr.approve('1')
    assert get_output() == get_pr_output('1') + 'PR approved\n'
    with pytest.raises(Exception) as e:
        ccpr.approve('2')
    assert str(e.value) == 'PR already closed, unable to approve'


@mock_boto3
def test_close():
    os.environ['CCPR_CACHE_SECS'] = '0'
    ccpr.set_console(Console(file=StringIO()))
    ccpr.close('1', confirm=True)
    assert get_output() == get_pr_output('1') + 'PR closed\n'
    with pytest.raises(Exception) as e:
        ccpr.close('2')
    assert str(e.value) == 'PR already closed'


@mock_boto3
def test_merge():
    os.environ['CCPR_CACHE_SECS'] = '0'
    ccpr.set_console(Console(file=StringIO()))
    ccpr.merge('1')
    assert get_output() == get_pr_output('1') + 'PR merged\n'
    with pytest.raises(Exception) as e:
        ccpr.merge('2')
    assert str(e.value) == 'PR already closed'
    with pytest.raises(Exception) as e:
        ccpr.merge('3')
    assert str(e.value) == 'PR not approved'


@mock_boto3
def test_create():
    os.environ['CCPR_CACHE_SECS'] = '0'
    ccpr.set_console(Console(file=StringIO()))
    ccpr.create('repo1', title='foobar', branch='foo')
    region = 'us-east-1'
    assert get_output() == '''created PR 3
link: https://%s.console.aws.amazon.com/codesuite/codecommit/repositories
/repo1/pull-requests/3/changes?region=%s
''' % (region, region)
    with pytest.raises(Exception) as e:
        ccpr.create('repo1', title='foobar', branch='baz')
    assert str(e.value) == 'current branch baz not in repo repo1'


@mock_boto3
def test_comment():
    os.environ['CCPR_CACHE_SECS'] = '0'
    ccpr.set_console(Console(file=StringIO()))
    ccpr.comment('1', content='foo')
    ccpr.comment('1', content='bar', file='foo/bar.txt', lineno=1)
    assert get_output() == 'general comment added\nfile comment added\n'
    with pytest.raises(Exception) as e:
        ccpr.comment('1', content='foo', file='foo.txt')
    assert str(e.value) == '--lineno required with --file'
    with pytest.raises(Exception) as e:
        ccpr.comment('1', content='foo', file='foo.js', lineno=1)
    assert str(e.value) == '''file 'foo.js' not in list of PR files:
[white]1] foo/bar.txt[/]
[white]2] foo/foo.txt[/]'''


@mock_boto3
def test_grep():
    os.environ['CCPR_CACHE_SECS'] = '0'
    ccpr.set_console(Console(file=StringIO()))
    ccpr.grep(
        'liNe2', '*.x', repo='repo?,repox',
        recursive=True, insensitive=False, verbose=False
    )
    ccpr.grep(
        'liNe2', '.', repo='repo1',
        recursive=False, insensitive=True, verbose=True
    )
    output = '\n'.join(sorted(get_output().splitlines()))
    print(output)
    assert output == '''/a.x:    line2
/b.x:    line2
/c.y:    no match
repo0: /b.x:    liNe2
repo1: /b.x:    liNe2
repo2: /b.x:    liNe2'''


def test_diff(tmp_path):
    f1 = tmp_path / 'foo1.txt'
    f1.write_text('line1\nline2')
    f2 = tmp_path / 'foo2.txt'
    f2.write_text('line1\nline3')
    ccpr.set_console(Console(file=StringIO()))
    ccpr.diff(f1, f2)
    assert get_output() == '''   1    1:   line1
   2     : - line2
        2: + line3
'''


@mock_boto3
def test_cli():
    ccpr.set_console(Console(file=StringIO()))
    with patch.object(sys, 'argv', ['ccpr', 'r']):
        ccpr.cli()
    assert get_output() == _table(['name'], [['repo0'], ['repo1'], ['repo2']])
