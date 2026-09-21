# codex-glab

Containerized GitLab workflows powered by Codex CLI and a ChatGPT access token.
The image includes Codex, GitLab CLI (`glab`), Git, Python, Bash and jq, and runs
as the non-root `node` user.

Inspired by [metbosch/opencode-glab](https://github.com/metbosch/opencode-glab).
This implementation uses Codex directly and does not require an OpenCode plugin.

## Image and commands

After the first successful publication:

```bash
docker pull ghcr.io/joanbosch/codex-glab:main
docker run --rm ghcr.io/joanbosch/codex-glab:main --list
docker run --rm ghcr.io/joanbosch/codex-glab:main codex --version
docker run --rm ghcr.io/joanbosch/codex-glab:main glab --version
```

The default flow is `mr-review`. Other flows can be added without changing the
container entrypoint. Only `mr-review` is currently implemented.

## Start with a dry run

Export the required variables in your environment or inject them through your
runner's secret store. Do not put tokens in the image, source files or command
history.

```bash
export GITLAB_HOST=gitlab.example.com
export PROJECT_URL=https://gitlab.example.com/group/project
export MERGE_REQUEST_IID=123

# CODEX_ACCESS_TOKEN and GITLAB_TOKEN must already be set securely.
docker run --rm \
  -e CODEX_ACCESS_TOKEN \
  -e GITLAB_TOKEN \
  -e GITLAB_HOST \
  -e PROJECT_URL \
  -e MERGE_REQUEST_IID \
  -e ADDITIONAL_INSTRUCTIONS \
  -e DRY_RUN=true \
  ghcr.io/joanbosch/codex-glab:main mr-review
```

`DRY_RUN=true` calls Codex and consumes account usage, but performs no GitLab
writes. It logs proposed discussions, the summary and approval blockers.

**Live mode is the default when `DRY_RUN` is omitted.** Set it explicitly to
`false` only when you intend to publish feedback and apply approval changes.
Feedback is written in English unless additional instructions request otherwise.

## Configuration

| Variable | Required | Meaning |
| --- | --- | --- |
| `CODEX_ACCESS_TOKEN` | Yes | ChatGPT access token supported by the installed Codex CLI. |
| `GITLAB_TOKEN` | Yes, or its alias | GitLab API credential with repository access and permission to approve the MR. |
| `GITLAB_AUTH_TOKEN` | Alternative | Alias for `GITLAB_TOKEN`; the latter takes precedence. |
| `GITLAB_HOST` | No | GitLab hostname, default `gitlab.com`. |
| `GITLAB_INSTANCE_URL` | No | HTTPS instance URL; takes precedence over `GITLAB_HOST`. |
| `PROJECT_URL` | Yes | Project URL (HTTPS, HTTP or SSH), SCP-style Git address, or `group/project` path; optional `.git` suffix. Only the project path is used: API calls and HTTPS cloning use the configured GitLab host, even if the supplied URL names another host. |
| `MERGE_REQUEST_IID` | For `mr-review` | Positive project-local merge request number. |
| `ADDITIONAL_INSTRUCTIONS` | No | Additional review focus or project-specific promotion criteria. |
| `ADDITIONAL_COMMENTS` | Alternative | Used if `ADDITIONAL_INSTRUCTIONS` is unset. |
| `CODEX_MODEL` | No | Model available to the authenticated account; otherwise Codex's default. |
| `CODEX_REASONING_EFFORT` | No | Explicit reasoning effort supported by the chosen model, such as `medium`; otherwise Codex's default. |
| `DRY_RUN` | No | `true` or `false`; defaults to `false`. |

To select GPT-5.6 Terra with medium reasoning, export both variables and pass
them to the container:

```bash
export CODEX_MODEL=gpt-5.6-terra
export CODEX_REASONING_EFFORT=medium
# Add these arguments to docker run:
# -e CODEX_MODEL -e CODEX_REASONING_EFFORT
```

The runner passes these as `--model gpt-5.6-terra` and
`--config 'model_reasoning_effort="medium"'`. Model availability is determined by
the authenticated account. Environment-variable support requires an image built
from a revision containing this feature.

Use a dedicated GitLab bot account where possible. Unapproval removes the
approval of the account represented by the token: using your personal token can
therefore remove an approval you previously added manually. The account must be
eligible under the project's approval rules. Password-based reauthentication or
other GitLab approval restrictions can prevent automation from approving.

ChatGPT authentication is ephemeral through `CODEX_ACCESS_TOKEN`; no persistent
login volume is required. Renew the token before it expires. The CLI is pinned
to `0.144.4`; update `CODEX_VERSION` if token creation specifies a newer minimum.

## Review workflow

1. Collect MR metadata, issues GitLab reports as closed by the MR, notes,
   discussions, diffs and head-pipeline job metadata with pagination.
2. Clone the target project, fetch the MR reference and check out its captured
   head commit. Full history supports review against the merge base and fork MRs.
3. Run Codex with full access (`danger-full-access`), no approval prompts
   (`approval_policy="never"`), and a structured JSON response schema.
   The Codex process is not given GitLab credentials. Its instructions prohibit
   running repository scripts/tests, installing dependencies and remote actions.
4. Validate all findings against added or removed diff lines, including renamed
   files. Publish inline discussions with severity and optional one-line code
   suggestions.
5. Evaluate approval, verify the result through GitLab and publish a summary.

The model recommends `approve`, `unapprove` or `abstain` and explains why. An
empty findings list alone is not sufficient for approval. Missing quality or CI
evidence should result in abstention.

### Approval gates

An approval requires all of the following:

- An explicit Codex approval recommendation and no actionable findings.
- An open, non-draft MR at the reviewed commit, with no reported conflicts.
- GitLab `detailed_merge_status` of `mergeable` or `not_approved`.
- Resolved discussions, including any resolvable threads inspected by the runner.
- A successful head pipeline whose SHA exactly matches the reviewed commit.
- Available pipeline job evidence, with every non-optional job successful.

The runner refreshes evidence and sends the reviewed SHA with the approval
request. GitLab rejects that request if the source head has changed. If gates do
not pass, it withholds approval and removes any existing approval belonging to
the authenticated account. Other users' approvals are not reset. Removing an
approval is not the same as requesting changes.

This workflow never assigns reviewers, pushes code, merges or deploys. Its
approval does not replace other required approvers or certify production readiness.

## Operational limits to check before enabling live mode

- **Downstream CI is not traversed.** The current implementation fetches jobs
  from the head pipeline only. It does not query trigger/bridge jobs, recursively
  inspect child pipelines, download test artifacts or independently query external
  status-check services. Do not rely on this version to enforce promotion gates
  located there; extend the gate collector before enabling live approvals for
  those projects. Jobs with `allow_failure=true` are not hard blockers.
- **Merged-results pipelines use a different SHA.** They are conservatively
  withheld by the exact-source-SHA check rather than treated as proof of coverage.
- **CI is not awaited.** Running, missing or failed pipelines prevent approval
  and can remove an existing approval. Trigger a new review after CI completes;
  there is no built-in polling or scheduled retry.
- **Serialize reviews for each MR.** There is no distributed lock. Unapproval
  has no atomic SHA precondition, and publishing multiple comments is not a
  transaction. A failed run can leave partial comments or an approval change.
- **Retries are only partially deduplicated.** Markers suppress identical inline
  findings for the same commit and identical summaries. Semantic deduplication
  relies on the model reading existing discussions.
- **GitLab diff limits apply.** Explicitly collapsed or oversized diffs abort
  the review. Binary changes cannot receive inline findings.
- **MR reviews run with full access.** `mr-review` uses `danger-full-access`
  and `approval_policy="never"`. Codex can access files and the network within
  the container's permissions, without its own filesystem sandbox or approval
  prompts. This flow does not invoke the Bubblewrap preflight and does not
  require unprivileged user namespaces. Container-level restrictions still apply.
  Other flows using `read-only` or `workspace-write` retain the Bubblewrap
  prerequisite check before calling the model.
- **Logs contain private code and feedback.** Restrict runner logs accordingly.
  Configure a job timeout and resource limits in the container runner.

## Build and publish

```bash
docker build -t codex-glab:local .
docker run --rm codex-glab:local --list
docker run --rm codex-glab:local codex --version
docker run --rm codex-glab:local glab --version
```

The base is Node 22 on Debian Trixie, which provides the `glab` package for both
target architectures. Do not switch to Bookworm while keeping the same apt
installation command: its main package index does not contain `glab`.

The included GitHub Actions workflow:

- Validates shell/Python syntax and lists installed flows.
- Builds `linux/amd64` and `linux/arm64` images.
- Builds pull requests without publishing them.
- Publishes pushes to `main` using the automatic `GITHUB_TOKEN`.
- Tags images as `main` and `sha-<full-source-commit>`.

Push the repository to `https://github.com/joanbosch/codex-glab` and inspect the
**Docker** workflow in Actions. No ChatGPT or GitLab credentials are needed for
the build. New GHCR packages are private by default: make the package public for
anonymous pulls, or configure the worker with a GitHub classic PAT with
`read:packages`.

Use an image digest for reproducible deployments. `main` is mutable, and even a
source-commit tag can be overwritten by rerunning its workflow because the base
image and Debian packages are not digest/version-pinned.

## Validation status

Python tests were run externally before publication; this repository intentionally
contains no test or runner-specific support directories. GitHub Actions performs
source checks and builds, not end-to-end GitLab/Codex tests. Docker build and live
authentication, review, approval and sandbox behavior still need verification in
the deployment environment. Start with a disposable MR and `DRY_RUN=true`.

## Add another flow

Add a package under `app/flows/<python_identifier>/` containing:

```text
__init__.py
flow.json
runner.py
prompt.md
output.schema.json
```

`flow.json` declares a unique command name, description, `required_env` list and
`sandbox` (`read-only`, `workspace-write` or `danger-full-access`). The runner exports `main(spec)` and
uses `spec.directory` for assets and `spec.sandbox` when calling
`shared.codex.execute`. Common GitLab transport, configuration, repository and
Codex helpers live in `app/shared/`.

Flow code is trusted application code shipped in the image, never loaded from
the reviewed repository. Rebuild to publish a new flow. Future issue implementation
flows should own their branch, validation and publication logic; they must not
change the review flow's permissions. `issue-implement` is not currently available.

## References and license

- [ChatGPT access tokens](https://learn.chatgpt.com/docs/enterprise/access-tokens)
- [GitLab approval API](https://docs.gitlab.com/api/merge_request_approvals/)
- [GitLab jobs and pipeline bridges](https://docs.gitlab.com/api/jobs/)
- [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [MIT license](LICENSE)
