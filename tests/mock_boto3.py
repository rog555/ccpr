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
from datetime import datetime
from functools import wraps
import os
import sys

import botocore
from mock import patch


ORIG_MAKE_API_CALL = botocore.client.BaseClient._make_api_call
THISMODULE = sys.modules[__name__]

MOCK_OPERATIONS = {
    'mock_codecommit': [
        'ListRepositories',
        'ListPullRequests',
        'GetPullRequest',
        'EvaluatePullRequestApprovalRules',
        'GetDifferences',
        'GetBlob',
        'GetCommentsForPullRequest',
        'UpdatePullRequestApprovalState',
        'UpdatePullRequestStatus',
        'MergePullRequestBySquash',
        'ListBranches',
        'CreatePullRequest',
        'PostCommentForPullRequest'
    ]
}


# not using moto.mock_lambda as it requires docker
def mock_boto3(f):

    def _debug(msg):
        if os.environ.get('MOCK_BOTO3_DEBUG') == 'TRUE':
            print('MOCK BOTO3 %s' % msg)

    def _get_mock_func(operation_name):
        disabled_funcs = os.environ.get(
            'MOCK_BOTO3_DISABLED_FUNCS', ''
        ).split(',')
        for func, operations in MOCK_OPERATIONS.items():
            if func in disabled_funcs:
                continue
            if operation_name in operations:
                return getattr(THISMODULE, func)
        return None

    def _mock(self, operation_name, kwargs):
        _debug('request %s %s' % (operation_name, kwargs))
        response = None
        mock_func = _get_mock_func(operation_name)
        if mock_func is not None:
            response = mock_func(operation_name, kwargs)
            if response is None:
                raise Exception('mock_boto3 operation %s not supported' % (
                    operation_name
                ))
        else:
            response = ORIG_MAKE_API_CALL(self, operation_name, kwargs)
        _debug('response %s %s' % (operation_name, response))
        return response

    @wraps(f)
    def decorated(*args, **kwargs):
        _make_api_call = 'botocore.client.BaseClient._make_api_call'
        with patch(_make_api_call, _mock):
            return f(*args, **kwargs)
    return decorated


def mock_codecommit(operation_name, kwargs):

    response = None
    user_arn = 'arn:aws:sts::123456789012:assumed-role/Developer/foo@bar.com'

    if operation_name == 'ListRepositories':
        response = {
            'repositories': [{
                'repositoryName': 'repo%s' % i
            } for i in range(3)],
        }

    elif operation_name == 'ListPullRequests':
        response = {
            "pullRequestIds": ['1', '2']
        }

    elif operation_name == 'GetPullRequest':
        prid = kwargs['pullRequestId']
        response = {
            'pullRequest': {
                'pullRequestId': prid,
                'title': 'title%s' % prid,
                'lastActivityDate': datetime.now(),
                'pullRequestStatus': (
                    'OPEN' if prid in ['1', '3'] else 'CLOSED'
                ),
                'authorArn': user_arn,
                'pullRequestTargets': [{
                    'repositoryName': 'repo1',
                    'sourceCommit': 'a',
                    'destinationCommit': 'b'
                }],
                'revisionId': 'r1',
                'approvalRules': []
            }
        }

    elif operation_name == 'EvaluatePullRequestApprovalRules':
        prid = kwargs['pullRequestId']
        response = {
            'evaluation': {
                'approved': True if prid == '1' else False,
                'overridden': False,
                'approvalRulesSatisfied': ['a', 'b'] if prid == '1' else ['a'],
                'approvalRulesNotSatisfied': [] if prid == '1' else ['b']
            }
        }

    elif operation_name == 'GetDifferences':
        response = {
            'differences': [{
                'beforeBlob': {
                    'blobId': 'b1a',
                    'path': 'foo/bar.txt'
                },
                'afterBlob': {
                    'blobId': 'b1b',
                    'path': 'foo/bar.txt'
                },
                'changeType': 'M'
            }]
        }

    elif operation_name == 'GetBlob':
        bid = kwargs['blobId']
        response = {
            'content': {
                'b1a': 'line1\nline2\nline3',
                'b1b': 'line1\nliNe2\nline4\nline5'
            }[bid].encode('utf-8')
        }

    elif operation_name == 'GetCommentsForPullRequest':
        response = {
            'commentsForPullRequestData': [
                {
                    'pullRequestId': kwargs['pullRequestId'],
                    'beforeBlobId': 'b1a',
                    'afterBlobId': 'b1b',
                    'location': {
                        'filePath': 'foo/bar.txt',
                        'filePosition': 1,
                        'relativeFileVersion': 'AFTER'
                    },
                    'comments': [{
                        'authorArn': user_arn,
                        'content': 'line1 comment'
                    }]
                },
                {
                    'pullRequestId': kwargs['pullRequestId'],
                    'beforeBlobId': 'b1a',
                    'afterBlobId': 'b1b',
                    'comments': [{
                        'authorArn': user_arn,
                        'content': 'general comment'
                    }]
                }
            ]
        }

    elif operation_name == 'UpdatePullRequestApprovalState':
        response = {}

    elif operation_name == 'UpdatePullRequestStatus':
        response = {}

    elif operation_name == 'MergePullRequestBySquash':
        response = {}

    elif operation_name == 'ListBranches':
        response = {
            'branches': ['foo', 'bar']
        }

    elif operation_name == 'CreatePullRequest':
        response = {
            'pullRequest': {
                'pullRequestId': '3'
            }
        }

    elif operation_name == 'PostCommentForPullRequest':
        response = {}

    return response
