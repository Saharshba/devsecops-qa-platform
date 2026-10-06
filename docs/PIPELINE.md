# The pipeline

## What runs when

| Trigger | CI | Security |
|---------|----|----------|
| push to `main` | yes | yes |
| pull request | yes | yes |
| weekly schedule (Mon 03:00) | no | yes — dependencies rot without a code change |
| manual dispatch | yes | yes |

Both workflows use a concurrency group keyed on the ref, so pushing again
cancels the previous run instead of queueing behind it.

## CI, stage by stage

```
lint ──┐
       ├──► build ──► e2e
test ──┘
```

### lint
`ruff check backend` and `ruff format --check backend`. Fast, and it fails on
the class of defects that are not worth a human review comment.

### test
Three separate pytest invocations before the combined run, each writing its own
JUnit file. Running them separately is what lets the QA summary report per-layer
results — and it makes the failure legible: a unit failure means a rule changed,
an API failure means the contract did.

Then the full suite with coverage, and then the integration layer once more
against the PostgreSQL service container. The default engine for tests is
SQLite (in-memory, one database per test, no container to wait for); the
PostgreSQL pass exists so nothing engine-specific reaches deployment.

The coverage floor is 85%, enforced with `coverage report --fail-under`. The
number is a floor, not a target: it is there to catch a pull request that adds
a module and no tests.

### build
Both images are built with Buildx and the GitHub Actions layer cache, then
saved as an artifact so later jobs do not rebuild them.

### e2e
`docker compose up`, `scripts/wait-for.sh` on both health endpoints, then
Playwright. On failure the job collects `docker compose logs` alongside the
Playwright trace, screenshot and video — the three artifacts that usually make
a flaky-looking failure explainable.

## Security, gate by gate

```
secrets ─┐
sast ────┤
deps ────┼──► gate  (fails if any of the five failed)
container┤
dast ────┘   (dast runs after container, since it needs the images)
```

### Secrets — gitleaks
Runs with `fetch-depth: 0`: a secret is just as compromised if it was committed
and then "removed" in a later commit.

### SAST — Semgrep and Bandit
Three public rulesets plus `.semgrep.yml`. Semgrep runs with `--error`, so a
finding fails the job, and uploads SARIF to the Security tab for triage.
Bandit runs as a second opinion on the Python code specifically.

### Dependencies — pip-audit and npm audit
`pip-audit --strict` on `requirements.txt` and `npm audit --audit-level=high`
on the frontend. The weekly schedule matters here more than anywhere else.

### Container — Trivy
Both images plus `--scan-type config` on the repository (Dockerfile and compose
misconfiguration). `severity: HIGH,CRITICAL` with `ignore-unfixed: true`:
failing on a CVE that has no patch available blocks delivery without improving
security. When a fix exists, the build fails.

### DAST — OWASP ZAP baseline
Starts the real stack and scans the running API. `.zap/rules.tsv` raises the
header and injection rules to `FAIL` and ignores the cookie/CSRF rules, each
with the reason recorded in the file: this API issues no cookies and
authenticates with bearer tokens, so those rules do not apply.

### gate
A final job that inspects the results of the other five. It exists so branch
protection can require one check instead of five, and so a skipped job cannot
be mistaken for a passing one.

## Adding a check

1. Add the job to the right workflow — quality in `ci.yml`, security in
   `security.yml`.
2. Make it fail the build, or do not add it. An advisory check is noise.
3. If it must not block, say why in a comment next to the exception, the way
   `ignore-unfixed` and each `.zap/rules.tsv` line do.
4. If it produces a report, upload it as an artifact and, if it is per-run
   information a human needs, add it to `scripts/qa_report.py`.

## Local reproduction

```bash
# lint and tests
cd backend && ruff check . && ruff format --check . && pytest --cov=app

# SAST
pip install semgrep && semgrep scan --config p/python --config .semgrep.yml backend

# dependencies
pip install pip-audit && pip-audit -r backend/requirements.txt --strict

# container
docker build -t tracker-backend:scan ./backend
trivy image --severity HIGH,CRITICAL --ignore-unfixed tracker-backend:scan

# DAST
docker compose up -d
docker run --rm --network host -v "$PWD/.zap:/zap/wrk:ro" \
  ghcr.io/zaproxy/zaproxy:stable zap-baseline.py \
  -t http://localhost:8000 -c rules.tsv
```

## Secrets the workflows need

None beyond the automatic `GITHUB_TOKEN`. Every tool used here runs without an
account, which is deliberate: a pipeline that cannot run on a fork is a
pipeline contributors cannot debug.
