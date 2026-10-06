# Secure Issue Tracker + Automated QA Pipeline

A project and issue tracker — and, more to the point, the pipeline that proves
it works and is safe to ship. The application is real (roles, a workflow state
machine, an audit trail); the focus of the repository is the automated quality
and security gate it passes on every push.

```
 developer push / pull request
            │
   ┌────────┴─────────┐
   ▼                  ▼
 CI (ci.yml)      Security (security.yml)
   │                  │
   ├ lint             ├ secret scan      gitleaks
   ├ unit             ├ SAST             Semgrep + Bandit
   ├ integration      ├ dependencies     pip-audit + npm audit
   ├ API              ├ container image  Trivy (image + config)
   ├ coverage gate    └ DAST             OWASP ZAP baseline
   ├ build images            │
   ├ end-to-end   Playwright │
   └ QA summary  ────────────┴──────► both must pass to merge
```

## Contents

- [Quick start](#quick-start)
- [The application](#the-application)
- [Test strategy](#test-strategy)
- [The pipeline](#the-pipeline)
- [QA reporting](#qa-reporting)
- [Application security](#application-security)
- [API](#api)
- [Measured results](#measured-results)
- [Project layout](#project-layout)

## Quick start

```bash
cp .env.example .env        # set SECRET_KEY and the admin password
docker compose up --build
```

| Service | URL |
|---------|-----|
| Web app | http://localhost:5173 |
| API docs | http://localhost:8000/docs |
| Health | http://localhost:8000/health |

Run the checks the pipeline runs:

```bash
cd backend
pip install -r requirements-dev.txt
pytest                                   # 111 tests
pytest --cov=app --cov-report=term       # coverage
ruff check . && ruff format --check .    # lint + format

cd ../e2e
npm install && npx playwright install --with-deps chromium
npm test                                 # end-to-end, against the running stack
```

## The application

A team tracks work in projects; each project has members, and each issue moves
through a workflow.

**Two authorisation layers.** A global role (`ADMIN`, `MANAGER`, `DEVELOPER`,
`VIEWER`) and a role inside each project. The stronger of the two applies, so a
developer can be made manager of one project without gaining powers elsewhere —
and a global manager keeps their powers in a project where they are only a
viewer. That resolution lives in `app/services/permissions.py` and has its own
test matrix.

**A workflow, not a status field.**

```
OPEN ──► IN_PROGRESS ──► IN_REVIEW ──► DONE ──► CLOSED
 │  ▲         │  ▲            │                   │
 │  └─────────┘  └────────────┘                   │
 └───────────────────────────────────────► CLOSED │
                                                  │
 OPEN ◄───────────────────────────────────────────┘  (reopen)
```

Enforced by a state machine, with rules a status dropdown cannot express:

- work cannot jump from `OPEN` to `DONE` — review is not optional;
- only a manager or admin may `CLOSE` an issue;
- an issue cannot start without an assignee;
- **the assignee cannot mark their own issue `DONE`** — someone else reviews it;
- a `VIEWER` cannot move anything at all.

Issue keys (`PAY-14`) come from a per-project counter, so numbering is gapless
and independent per project.

Everything that happens is appended to an activity feed, and the people
involved — reporter, assignee, previous commenters — are notified, while the
person who took the action never is.

## Test strategy

Four layers, each answering a different question. The split is what makes a
failure diagnostic: a unit failure means a rule changed, an E2E failure means
the assembled system changed.

| Layer | Question | Count | Where |
|-------|----------|-------|-------|
| **Unit** | Do the rules hold? | 54 | `backend/tests/unit` |
| **Integration** | Do the API and the database agree? | 12 | `backend/tests/integration` |
| **API** | Is the contract honoured and the surface hardened? | 45 | `backend/tests/api` |
| **End-to-end** | Does the journey work in a browser? | 7 | `e2e/tests` |

**Unit** — the workflow state machine, the permission matrix and notification
fan-out, as pure functions: no database, no HTTP. Every transition in the table
is checked, in both directions, for every role.

**Integration** — the API against a real database: an issue is created,
assigned, moved through the workflow and commented on, and the test asserts the
activity feed, the notifications, the `closed_at` stamp and the per-project key
sequence all came out right.

**API** — the contract and the hardening: the authorisation matrix by role, the
IDOR check (a valid issue key, a user with no business seeing it), input
validation bounds, error shapes, security headers, rate limiting.

**End-to-end** — Playwright against the compose stack: sign in, create a
project, create an issue, assign it, walk the workflow, comment, and verify the
history. A second spec checks access control through both the UI and the API,
because a hidden button is not an access control.

```
 login ─► create project ─► create issue ─► assign developer
       ─► IN_PROGRESS ─► IN_REVIEW ─► DONE ─► comment ─► verify history
```

Fixtures for E2E are created through the API rather than by clicking, so a test
fails on the journey it is testing, not on unrelated setup.

## The pipeline

### `ci.yml` — the quality gate

| Job | What it does | Fails the build when |
|-----|--------------|----------------------|
| `lint` | `ruff check` + `ruff format --check` | style or an obvious defect |
| `test` | unit → integration → API, then the full suite with coverage, then the integration layer again against real PostgreSQL | any test fails, or coverage drops below 85% |
| `build` | builds both images with Buildx and layer caching | the image does not build |
| `e2e` | brings up `docker compose`, waits for health, runs Playwright | a user journey breaks |

The suite runs on SQLite by default — fast and isolated per test — and the CI
job re-runs the integration layer against PostgreSQL so anything
engine-specific is caught before deployment. Traces, screenshots and videos are
kept for failed E2E runs; the QA summary and all reports are uploaded as
artifacts.

### `security.yml` — the security gate

| Job | Tool | Blocks on |
|-----|------|-----------|
| `secrets` | gitleaks (full history) | a committed credential |
| `sast` | Semgrep (`p/python`, `p/security-audit`, `p/owasp-top-ten`, plus project rules) and Bandit | a SAST finding; results also upload as SARIF |
| `dependencies` | `pip-audit --strict`, `npm audit --audit-level=high` | a known vulnerable dependency |
| `container` | Trivy on both images and on the repo config | HIGH/CRITICAL with a fix available, or a container misconfiguration |
| `dast` | OWASP ZAP baseline against the running API | a missing security header, XSS, SQL injection or error disclosure |
| `gate` | aggregates the five | any of them failed |

Nothing in this workflow is advisory-only: a warning nobody must act on is not
a gate. Two deliberate exceptions are written down rather than hidden —
`ignore-unfixed` on Trivy, because failing on a CVE with no patch just blocks
delivery, and the ZAP rules in `.zap/rules.tsv`, where each ignored rule states
why it does not apply to a cookie-less bearer-token API.

`.semgrep.yml` adds five project-specific rules on top of the public rulesets:
no string-formatted SQL, no route without an auth dependency (health and login
excepted), no hard-coded credential outside `config.py`, no forced debug mode,
and no `dangerouslySetInnerHTML` in the frontend — issue titles and comments
are user-controlled.

Dependency scanning also runs weekly on a schedule: dependencies rot without
any code change.

## QA reporting

`scripts/qa_report.py` turns the raw JUnit and coverage XML into one summary
that lands in the GitHub step summary:

```
## QA summary

**PASS** — 111 tests, 0 failing, 1.7s, 91.9% line coverage

| Layer       | Tests | Passed | Failed | Skipped | Time | Result |
|-------------|------:|-------:|-------:|--------:|-----:|--------|
| Unit        |    54 |     54 |      0 |       0 | 0.0s | pass   |
| Integration |    12 |     12 |      0 |       0 | 0.6s | pass   |
| API         |    45 |     45 |      0 |       0 | 1.1s | pass   |
| End-to-end  |     7 |      7 |      0 |       0 | 9.4s | pass   |

### Coverage

1001 of 1089 statements covered — **91.9%** (floor 85%): pass
```

It renders even when an earlier job failed — a missing report is shown as
"not run" rather than crashing the step that is supposed to explain the
failure.

## Application security

The application is worth securing on its own terms, not only scanning:

- bcrypt password hashing (cost 12) and a password policy enforced by the schema;
- short-lived JWT access tokens plus refresh tokens, with typed claims so a
  refresh token cannot be replayed as an access token;
- deactivating a user cuts their access off on the next request;
- two-layer RBAC enforced by route dependencies, never by the UI;
- ownership checks that return **404 rather than 403** where a 403 would
  confirm that someone else's record exists;
- Pydantic validation on every body and query parameter, with an error handler
  that returns field names and messages without echoing submitted values;
- parameterised queries throughout — a search for `' OR 1=1 --` matches nothing,
  and there is a test that says so;
- security headers (`nosniff`, `DENY`, a `default-src 'none'` CSP, no-referrer)
  and per-IP rate limiting with a tighter budget on login;
- an audit log of logins, user administration and project changes;
- containers that run as an unprivileged user, built in two stages so the
  runtime image carries no build tooling.

## API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/auth/login` · `/refresh` | authentication |
| GET | `/api/auth/me` · `/users` | profile, user lookup for assignment |
| POST | `/api/auth/users` | create a user (ADMIN) |
| PATCH | `/api/auth/users/{username}/deactivate` | disable an account (ADMIN) |
| GET · POST | `/api/projects` | list / create (MANAGER) |
| GET · PATCH | `/api/projects/{key}` | detail / edit |
| POST · DELETE | `/api/projects/{key}/members[/{username}]` | membership |
| GET · POST | `/api/projects/{key}/issues` | list (filter, paginate) / create |
| GET · PATCH · DELETE | `/api/issues/{key}` | detail / update / delete (ADMIN) |
| GET · POST | `/api/issues/{key}/comments` | conversation |
| PATCH | `/api/comments/{id}` | edit your own comment |
| GET | `/api/issues/{key}/activity` · `/api/projects/{key}/activity` | history |
| GET · POST | `/api/notifications[...]` | inbox, mark read |
| GET | `/api/dashboard` | aggregate, scoped to your projects |
| GET | `/api/audit` | audit trail (ADMIN) |

## Measured results

| Measurement | Value |
|-------------|-------|
| Automated tests | 111 backend (54 unit · 12 integration · 45 API) + 7 end-to-end |
| Statement coverage (`app/`) | 92%, with 100% on the workflow, permission and notification services |
| Coverage gate | build fails below 85% |
| Security checks in the pipeline | 5 gates: secrets, SAST, dependencies, container, DAST |
| Project-specific SAST rules | 5 |
| Pipeline jobs | 4 in CI, 6 in Security |
| Lint | `ruff check` and `ruff format --check` clean |

Reproduce the first three rows with `pytest --cov=app` in `backend/` and
`python scripts/qa_report.py --reports backend/reports`.

## Project layout

```
backend/
  app/
    core/        config, database, security, rate limiting, audit, middleware
    services/    workflow state machine · permissions · notifications (pure logic)
    routers/     auth, projects, issues + comments + activity, notifications
    models.py    users, projects, members, issues, comments, activities,
                 notifications, audit logs
  tests/
    unit/        rules, no I/O
    integration/ API + database
    api/         contract and hardening
frontend/        React: dashboard, projects, board, issue detail, notifications
e2e/             Playwright: the journeys, plus access control through the UI
scripts/         qa_report.py · wait-for.sh
.github/workflows/  ci.yml · security.yml
.semgrep.yml     project-specific SAST rules
.zap/rules.tsv   DAST rule configuration, each exception justified
docs/            PIPELINE.md · TESTING.md
```

## Licence

MIT.
