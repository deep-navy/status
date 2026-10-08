# deep.navy status

External checks and incident history powered by [Upptime](https://upptime.js.org/docs/).
Configuration lives in `.upptimerc.yml`. There are no historical measurements until the first successful monitoring run.

## Scope

Website HTTP availability, a body-checked public Connect catalog request, MCP unauthenticated rejection, and OAuth resource metadata. The MCP check expects 401 deliberately and does not measure authenticated tool execution, dataset freshness or billing correctness. These four Upptime checks use no credentials. A [separate hourly semantic MCP check](AUTHENTICATED-CHECK.md) uses a dedicated synthetic account and validates one local catalog tool result; its workflow badge is separate from Upptime incident history.

Every detected incident is retained (`skipDeleteIssues: true`). GitHub Actions schedules are best effort; outages between checks can be missed. Incident maintainers can add impact, investigation and resolution updates using GitHub Issues. Do not put customer identifiers, credentials or request contents in this public repository.

## Deployment

Repository, Actions permissions, Pages and DNS are managed in the platform OpenTofu `github/status.tf` and `aws/status.tf`.
Runtime monitoring can use the built-in repository GITHUB_TOKEN (contents/issues write). Upstream Setup CI and Update Template CI rewrite workflow files; for unattended template updates, the official getting-started guide recommends a GitHub App installed only on this status repository with Actions, Contents, Issues and Workflows read/write, GH_APP_ID set to its Client ID and GH_APP_PRIVATE_KEY stored as a repository secret. Do not reuse an operator's broad gh token. Without that scoped credential, verify runtime jobs individually and keep template updates manual; do not claim setup succeeded if it fails to write workflows. The official Upptime site workflow writes generated output to gh-pages. `deploy-pages.yml` then uses GitHub's official Pages artifact actions to publish it; this avoids relying on a GITHUB_TOKEN push to trigger a Pages build.

Automatic Setup, Updates and Update Template workflows are deliberately removed: they rewrite workflow files and require workflow-write credentials. Runtime workflows are pinned to Upptime v1.44.1. Upgrade manually by reviewing a newer upstream template, regenerating workflows for secrets: [], and committing the reviewed diff with an operator identity. Do not provision a broad personal token for unattended upgrades.

After provisioning, push the prepared configuration, run Uptime CI, Summary CI, Graphs CI and Static Site CI. Verify Deploy status to Pages succeeds, check the latest timestamps and exercise a temporary failing test endpoint before removing it. Never seed healthy measurements or incidents. Upptime owns its generated workflows; put custom deployment in its separate file.

Sources: [configuration](https://upptime.js.org/docs/configuration/), [template](https://github.com/upptime/upptime), [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
