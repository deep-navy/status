#!/usr/bin/env python3
"""Operator-only reconciliation of the synthetic account; never rotate its API key."""
import argparse
import secrets
import sys

USERNAME = 'status-monitor@deep.navy'


def reconcile(call, required_tools=()):
    before = call('account.v1.AccountService', 'ListApiKeys', {'pageSize': 200})
    if before.get('nextPageToken') or not before.get('keys'):
        raise RuntimeError('unexpected_key_inventory')
    key_ids = sorted(key['id'] for key in before['keys'])
    rows = call('account.v1.ToolSettingsService', 'ListMyTools', {})['tools']
    names = {row['tool']['name'] for row in rows}
    if 'energy_search' not in names or not set(required_tools).issubset(names):
        raise RuntimeError('expected_tool_migration_not_visible')
    for row in rows:
        name = row['tool']['name']
        enabled = name == 'energy_search'
        if bool(row.get('enabledByMe')) != enabled:
            call('account.v1.ToolSettingsService', 'SetMyToolEnabled', {'tool': name, 'enabled': enabled})
    effective = sorted(row['tool']['name'] for row in call('account.v1.ToolSettingsService', 'ListMyTools', {})['tools'] if row.get('effective'))
    if effective != ['energy_search']:
        raise RuntimeError('effective_scope_mismatch')
    after = call('account.v1.AccountService', 'ListApiKeys', {'pageSize': 200})
    if after.get('nextPageToken') or sorted(key['id'] for key in after.get('keys', [])) != key_ids:
        raise RuntimeError('key_inventory_changed')


def run(args):
    # These imports are operator-only: CI's semantic probe/tests need no AWS SDK.
    import boto3
    from botocore.config import Config
    from bootstrap_status_identity import account_call

    cognito = boto3.Session(profile_name=args.profile, region_name=args.region).client('cognito-idp', config=Config(retries={'total_max_attempts': 1}, connect_timeout=5, read_timeout=15))
    client = cognito.describe_user_pool_client(UserPoolId=args.pool_id, ClientId=args.client_id)['UserPoolClient']
    if client.get('ClientSecret') or 'https://deep.navy/auth/callback' not in client.get('CallbackURLs', []) or 'ALLOW_USER_AUTH' not in client.get('ExplicitAuthFlows', []):
        raise RuntimeError('website_client_mismatch')
    # Fixed synthetic identity only. No creation, human password reset or admin group.
    user = cognito.admin_get_user(UserPoolId=args.pool_id, Username=USERNAME)
    if not user.get('Enabled') or cognito.admin_list_groups_for_user(UserPoolId=args.pool_id, Username=USERNAME).get('Groups'):
        raise RuntimeError('unexpected_synthetic_identity_state')
    password = secrets.token_urlsafe(40) + 'Aa1!'
    cognito.admin_set_user_password(UserPoolId=args.pool_id, Username=USERNAME, Password=password, Permanent=True)
    auth = cognito.initiate_auth(ClientId=args.client_id, AuthFlow='USER_AUTH', AuthParameters={'USERNAME': USERNAME, 'PREFERRED_CHALLENGE': 'PASSWORD', 'PASSWORD': password})
    if 'AuthenticationResult' not in auth:
        if auth.get('ChallengeName') != 'PASSWORD':
            raise RuntimeError('unexpected_auth_challenge')
        auth = cognito.respond_to_auth_challenge(ClientId=args.client_id, ChallengeName='PASSWORD', Session=auth['Session'], ChallengeResponses={'USERNAME': USERNAME, 'PASSWORD': password})
    token = auth['AuthenticationResult']['AccessToken']
    call = lambda service, method, body: account_call(token, service, method, body)
    plan = call('billing.v1.BillingService', 'GetPlan', {})['plan']
    if plan['code'] not in ('free', 'preview') or int(plan.get('amountCents', 0)) != 0:
        raise RuntimeError('unexpected_synthetic_plan')
    reconcile(call, args.require_tool)
    print('PASS energy_search_only existing_keys_preserved')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pool-id', required=True)
    parser.add_argument('--client-id', required=True)
    parser.add_argument('--profile', default='deep-navy')
    parser.add_argument('--region', default='us-east-1')
    parser.add_argument('--require-tool', action='append', default=[], help='Refuse changes until this migrated tool exists; repeat for multiple tools')
    args = parser.parse_args()
    try:
        run(args)
    except Exception as error:
        print('FAIL reconciliation_' + type(error).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
