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
        'EvaluatePullRequestApprovalRules'
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

    if operation_name == 'ListRepositories':
        response = {
            'repositories': [{
                'repositoryName': 'repo%s' % i
            } for i in range(3)],
        }

    elif operation_name == 'ListPullRequests':
        response = {
            "pullRequestIds": ["1", "2"]
        }

    elif operation_name == 'GetPullRequest':
        prid = kwargs['pullRequestId']
        response = {
            'pullRequest': prid,
            'title': 'title%s' % prid,
            'lastActivityDate': '2021-09-24T11:51:54',
            'pullRequestStatus': 'OPEN' if prid == 1 else 0,
            'authorArn': (
                'arn:aws:sts::123456789012:assumed-role/Developer/foo@bar.com'
            ),
            'pullRequestTargets': [{
                'repositoryName': 'repo1'
            }]
        }

    elif operation_name == 'EvaluatePullRequestApprovalRules':
        response = {}

    return response
