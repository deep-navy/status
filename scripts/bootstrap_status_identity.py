#!/usr/bin/env python3
"""Operator-only, normal Cognito/account API bootstrap. Never print credential material."""
import argparse
import json
import secrets
import subprocess
import sys
import urllib.error
import urllib.request

import boto3
from botocore.config import Config
from mcp_probe import NoRedirect, probe

API = 'https://api.deep.navy/'
REPO = 'deep-navy/status'
ENVIRONMENT = 'status-monitor'


def github(*args, input=None):
    process = subprocess.run(['gh', *args], input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if process.returncode:
        raise RuntimeError('github_operation_failed')
    return json.loads(process.stdout) if process.stdout else None


def account_call(token, service, method, body):
    request = urllib.request.Request(API + 'deepnavy.' + service + '/' + method,
        json.dumps(body).encode(), {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}, method='POST')
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
        return json.load(response)


def run(args):
    # Preflight the IaC environment so credentials cannot land in an unrestricted secret scope.
    environment = github('api', f'repos/{REPO}/environments/{ENVIRONMENT}')
    if environment.get('deployment_branch_policy') != {'protected_branches': False, 'custom_branch_policies': True}:
        raise RuntimeError('environment_policy_mismatch')
    policies = github('api', f'repos/{REPO}/environments/{ENVIRONMENT}/deployment-branch-policies')
    if [(p['name'], p.get('type', 'branch')) for p in policies['branch_policies']] != [('master', 'branch')]:
        raise RuntimeError('environment_branch_mismatch')
    cognito = boto3.Session(profile_name=args.profile, region_name=args.region).client('cognito-idp', config=Config(retries={'total_max_attempts': 1}, connect_timeout=5, read_timeout=15))
    client = cognito.describe_user_pool_client(UserPoolId=args.pool_id, ClientId=args.client_id)['UserPoolClient']
    if client.get('ClientSecret') or 'https://deep.navy/auth/callback' not in client.get('CallbackURLs', []) or 'ALLOW_USER_AUTH' not in client.get('ExplicitAuthFlows', []):
        raise RuntimeError('website_client_mismatch')
    # Resume only an explicitly selected, incomplete synthetic bootstrap; normal reruns refuse it.
    exists = False
    try:
        cognito.admin_get_user(UserPoolId=args.pool_id, Username=args.username)
    except cognito.exceptions.UserNotFoundException:
        pass
    else:
        exists = True
        if not args.resume_bootstrap:
            raise RuntimeError('identity_already_exists_use_rotation')
        if cognito.admin_list_groups_for_user(UserPoolId=args.pool_id, Username=args.username).get('Groups'):
            raise RuntimeError('existing_identity_has_groups')
    password = secrets.token_urlsafe(40) + 'Aa1!'
    if not exists:
        cognito.admin_create_user(UserPoolId=args.pool_id, Username=args.username, MessageAction='SUPPRESS', UserAttributes=[{'Name': 'email', 'Value': args.username}, {'Name': 'email_verified', 'Value': 'true'}])
    cognito.admin_set_user_password(UserPoolId=args.pool_id, Username=args.username, Password=password, Permanent=True)
    auth = cognito.initiate_auth(ClientId=args.client_id, AuthFlow='USER_AUTH', AuthParameters={'USERNAME': args.username, 'PREFERRED_CHALLENGE': 'PASSWORD', 'PASSWORD': password})
    if 'AuthenticationResult' not in auth:
        if auth.get('ChallengeName') != 'PASSWORD':
            raise RuntimeError('unexpected_auth_challenge')
        auth = cognito.respond_to_auth_challenge(ClientId=args.client_id, ChallengeName='PASSWORD', Session=auth['Session'], ChallengeResponses={'USERNAME': args.username, 'PASSWORD': password})
    token = auth['AuthenticationResult']['AccessToken']
    call = lambda service, method, body={}: account_call(token, service, method, body)
    customer = call('account.v1.AccountService', 'GetMe')['customer']
    plan = call('billing.v1.BillingService', 'GetPlan')['plan']
    if plan['code'] not in ('free', 'preview') or int(plan.get('amountCents', 0)) != 0 or int(plan['calls']['included']) < 1000 or not plan['calls'].get('hardCap'):
        raise RuntimeError('plan_not_zero_priced_with_sufficient_hard_cap')
    tools = call('account.v1.ToolSettingsService', 'ListMyTools')['tools']
    for tool in tools:
        name = tool['tool']['name']
        call('account.v1.ToolSettingsService', 'SetMyToolEnabled', {'tool': name, 'enabled': name == 'energy_search'})
    effective = [t['tool']['name'] for t in call('account.v1.ToolSettingsService', 'ListMyTools')['tools'] if t.get('effective')]
    if effective != ['energy_search']:
        raise RuntimeError('effective_scope_mismatch')
    if call('account.v1.AccountService', 'ListApiKeys').get('keys'):
        raise RuntimeError('unexpected_existing_keys')
    issued = call('account.v1.AccountService', 'CreateApiKey', {'name': 'Hourly status catalog probe', 'rateLimitPerMinute': '2', 'monthlySpendLimitUsdMicros': '5000000'})
    try:
        probe(issued['secret'])
        github('secret', 'set', 'DEEPNAVY_STATUS_KEY', '--repo', REPO, '--env', ENVIRONMENT, input=issued['secret'].encode())
    except Exception:
        call('account.v1.AccountService', 'RevokeApiKey', {'id': issued['key']['id']})
        raise
    # Safe IDs and plan evidence only; keep this output in private operator records.
    print(json.dumps({'status': 'PASS', 'customerId': customer['id'], 'keyId': issued['key']['id'], 'plan': plan['code'], 'includedCalls': plan['calls']['included'], 'effectiveTools': effective, 'secretStored': True}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--username', required=True, help='Existing operator-owned alias approved for the synthetic identity; no email is sent')
    parser.add_argument('--resume-bootstrap', action='store_true', help='Reset only this operator-owned incomplete synthetic identity after a failed first setup; never a human account')
    parser.add_argument('--pool-id', required=True)
    parser.add_argument('--client-id', required=True)
    parser.add_argument('--profile', default='deep-navy')
    parser.add_argument('--region', default='us-east-1')
    args = parser.parse_args()
    try:
        run(args)
    except Exception as error:
        # SDK/HTTP exceptions can include sensitive fields; never stringify them.
        print('FAIL bootstrap_' + type(error).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
