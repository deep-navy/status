# Authenticated MCP check

The existing Upptime checks keep their own history/incident semantics. Upptime v1.44.1
has literal `String.includes` body checks, not JSON/SSE parsing or custom-script checks.
The separate `Authenticated MCP check` workflow therefore performs a semantic check
using Python's standard library, without a proxy, HTTP server or extra cloud resources.

Its public GitHub workflow result is separate from Upptime incident history. The status site links the workflow and its branch-specific scheduled-run badge. Never label this as
an Upptime component with measured history that does not exist.

## What it measures

Once an hour (GitHub schedules are best effort), initialize authenticated MCP, discover
exactly `energy_search`, then call it with `query: electricity`. Require a successful JSON-RPC
response, no tool `isError`, structured dataset `electricity/retail-sales` with its title,
`available: true`, and source attribution. Catalog discovery is local and needs no external
EIA request. The call is still metered normally. This does not prove every tool, provider
freshness, source ingestion, hosted OAuth login, webhook delivery or invoicing.

There is one tool call per successful run, at most 744 scheduled calls per 31-day month,
plus explicit manual runs (budget at most 100 manual runs/month, leaving 156 calls for setup and investigation on the 1,000-call Free plan). Pull requests run offline tests only; pushes do not invoke the paid/metered path. No application retry occurs. The 15-second shared deadline
is checked between requests and read chunks; any blocked socket read has a maximum
five-second timeout. Response bodies are limited to 128 KiB. The workflow has a two-minute
job timeout. TLS verification is enabled; redirects are refused. Only locally defined
PASS/FAIL reason codes are printed, never response bodies, headers, customer IDs or secrets.

## Dedicated identity

Do not use an existing customer's key, the gateway development key or an admin credential.
Provision an operator-owned synthetic customer through Cognito and the normal AccountService
path. The website client supports choice-based `USER_AUTH` with PASSWORD. Use the clearly labelled `status-monitor@deep.navy` internal synthetic identity; this is not a mailbox-delivery or human-access claim. Use the existing
supported Cognito admin APIs to create a suppressed-invitation machine identity, set a random
password and authenticate; do not insert database rows or add admin group membership.

Using that website session:

1. Call `AccountService/GetMe` to create the ordinary customer/billing profile.
2. Call `ToolSettingsService/ListMyTools`; turn every tool off except `energy_search` using
   `SetMyToolEnabled`. Verify effective access is exactly that tool before issuing a key.
3. Create an ordinary tool key via `AccountService/CreateApiKey`, with a rate cap and an
   monthly spend cap of USD 5 (5000000 microdollars) and rate cap of 2 calls/minute. This is a conservative reservation cap, not permission to change to a paid plan; the ordinary Free/Preview plan remains zero-priced.
   Do not grant management privilege. Verify actual pricing/quota before enabling schedules.
4. Put only the shown-once tool key in the `status-monitor` GitHub environment secret
   `DEEPNAVY_STATUS_KEY`, using stdin or an SDK, not command arguments or a committed file.
   Restrict environment deployment to the `master` branch. Delete transient password/session
   material; operator Cognito AdminSetUserPassword is the recovery mechanism, so no reusable password or session is retained.
5. Run the probe once and verify a known forbidden tool fails, then verify the workflow and
   public result before updating site wording. Record sanitized identity/key IDs for rotation.

Current platform limitation: tool switches are account-level and new tools default to enabled.
They are not an immutable per-key allowlist. The probe fails before execution if `tools/list`
contains anything other than `energy_search`; monitor that drift and disable newly introduced
tools for this synthetic account. Do not claim an immutable single-tool scope.

Rotate using the same account: issue a replacement limited key, update the environment secret,
verify one run, then revoke the old key. Disable the synthetic identity/key to retire the check.
The checked-in operator bootstrap script requires an existing IaC-created environment and sends the shown-once key directly to GitHub encrypted-secret storage, never to stdout or a file. It refuses unexpected account plans, existing keys and wider effective tool access. `--resume-bootstrap` may reset only a known incomplete synthetic identity after an interrupted first setup; normal reruns refuse an existing identity. The operator script requires boto3; the scheduled probe and offline tests use only the Python standard library.

## Official references

- [Upptime configuration](https://upptime.js.org/docs/configuration/): secret allowlists,
  request headers/body and literal response-body checks.
- [Pinned status classification](https://github.com/upptime/uptime-monitor/blob/v1.44.1/src/update.ts)
  and [pinned request timeouts](https://github.com/upptime/uptime-monitor/blob/v1.44.1/src/helpers/request.ts).
- [GitHub workflow badges](https://docs.github.com/en/actions/monitoring-and-troubleshooting-workflows/monitoring-workflows/adding-a-workflow-status-badge).
- [GitHub environment protection](https://docs.github.com/en/actions/deployment/targeting-different-environments/managing-environments-for-deployment).
- [AWS Secrets Manager in GitHub jobs](https://docs.aws.amazon.com/secretsmanager/latest/userguide/retrieving-secrets_github.html)
  explains job-wide environment exposure. This runtime needs no AWS credentials; the isolated
  GitHub environment injects only the probe key into its one consuming step.

## Cadence decision and current plan evidence

On 2026-10-08 the public `BillingService/ListPlans` returned `preview: true` and a
Free allowance of 1,000 calls/month with a hard cap. The synthetic account must remain
on ordinary zero-priced Free/Preview, never an internal billing exemption. The hourly
probe fits Free after preview ends. An authenticated Upptime row was deliberately not
added: its global five-minute schedule plus up to three confirmation attempts would
exceed Free even with request-level retries disabled. Existing public checks remain
at five minutes. No new capacity, paid plan, AWS runtime role or secret-store charge is needed.

The hourly workflow has no automatic retry. A failed run stays failed and the next
scheduled check is the next attempt. Manual reruns consume the same real allowance;
operators must check monthly usage before bulk reruns. A Free quota failure is an
actual monitoring-identity limitation, not evidence every customer is down.

## Operator activation

1. Review/apply only `github_repository_environment.status_monitor` and
   `github_repository_environment_deployment_policy.status_monitor` in the platform
   GitHub IaC stack; inspect dependencies for unrelated drift before applying.
2. Run `python3 scripts/bootstrap_status_identity.py --username OWNED_ALIAS --pool-id POOL --client-id WEBSITE_CLIENT`.
   This requires the operator's normal AWS profile and `gh` authorization; it is never a CI job.
3. Review and publish this change, run `Authenticated MCP check` manually once, then
   rebuild Upptime's static site to publish its workflow link. Verify the first scheduled
   result before treating the schedule-specific badge as measured.
4. Record sanitized customer/key identifiers and the plan check in private operations
   evidence. Never put identifying account metadata or credential material in this public repo.

Cognito flow reference: [InitiateAuth USER_AUTH and PASSWORD challenge](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_InitiateAuth.html).

## Activation evidence

The `status-monitor` environment and master-only branch policy were applied from the
reviewed two-add/zero-change/zero-destroy IaC plan. The dedicated ordinary synthetic
account was created with invitation suppression and no admin group. Normal account
APIs confirmed Preview, zero monthly price, a 1,000,000-call hard cap and effective
tools exactly `energy_search`. Its key has a two-call/minute rate cap and USD 5
conservative reservation cap. Live MCP initialize, tools/list and catalog execution
passed; the shown-once key went directly to the GitHub environment secret. No password
or session was persisted. The chosen hourly cadence still fits Free when preview ends.

The Cognito [password choice flow](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-authentication-flow-methods.html) passes PASSWORD together with PREFERRED_CHALLENGE=PASSWORD; authentication may return tokens immediately.
