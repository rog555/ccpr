
from io import StringIO
import os
from rich.console import Console
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(ROOT_DIR, 'tests', 'data')
sys.path.append(ROOT_DIR)

import ccpr  # noqa: E402
from tests.mock_boto3 import mock_boto3  # noqa: E402


@mock_boto3
def test_repos():
    ccpr.set_console(Console(file=StringIO()))
    ccpr.repos(filter='repo')
    output = ccpr.get_console().file.getvalue()
    assert output == '''┏━━━━━━━┓
┃ name  ┃
┡━━━━━━━┩
│ repo0 │
│ repo1 │
│ repo2 │
└───────┘
'''


@mock_boto3
def todo_test_prs():
    ccpr.set_console(Console(file=StringIO()))
    ccpr.prs('repo1', open=True)
    output = ccpr.get_console().file.getvalue()
    assert output == '''┏━━━━━━━┓'''
