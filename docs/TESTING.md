# Testing

## The layers, and what each is for

```
        few, slow, realistic
        ┌──────────────┐
        │  end-to-end  │  7   browser journeys through the compose stack
        ├──────────────┤
        │     API      │  45  contract, authorisation, hardening
        ├──────────────┤
        │ integration  │  12  API + database together
        ├──────────────┤
        │     unit     │  54  rules, no I/O
        └──────────────┘
        many, fast, isolated
```

A test belongs at the lowest layer that can answer its question. "May a viewer
close an issue?" is a unit test. "Does closing an issue write the activity
row?" is an integration test. "Can a viewer bypass the UI and close it over
HTTP?" is an API test. "Can a person do this in a browser?" is E2E.

## Running them

```bash
cd backend
pytest                       # everything (111)
pytest tests/unit            # the rules
pytest tests/integration     # API + database
pytest tests/api             # contract and hardening
pytest --cov=app --cov-report=html:reports/htmlcov
pytest -k transition -v      # one topic

cd ../e2e
npm install
npx playwright install --with-deps chromium
npm test                     # needs the stack: docker compose up -d
npx playwright test --ui     # interactive
npm run report               # last HTML report
```

## Fixtures

`backend/tests/conftest.py` provides:

| Fixture | What it gives you |
|---------|-------------------|
| `db_engine` / `session_factory` / `db` | a fresh in-memory SQLite database per test |
| `client` | a `TestClient` wired to that database, with one user per role seeded |
| `auth_header("dev")` | bearer headers for any seeded user |
| `project` | the `PAY` project with the cast as members — `outsider` deliberately excluded |
| `issue` | `PAY-1`, reported by `dev` |

The cast is: `admin`, `manager`, `dev`, `dev2`, `viewer`, `outsider`. Two
developers exist because the rule "the assignee cannot mark their own issue
done" needs a second one to be testable, and `outsider` exists so every
authorisation test has a user who legitimately belongs nowhere.

Each test gets its own database, so tests never depend on ordering and can be
run individually or with `-p no:randomly` equivalence.

## Conventions

**Name the behaviour, not the function.**
`test_the_assignee_cannot_mark_their_own_work_done`, not `test_transition_3`.

**Assert the reason, not just the status code.** A 403 with the wrong reason is
a bug that passes a status-code assertion.

**Every rule gets a negative test.** A detector or a permission that has only
been shown to fire has not been shown to be useful; `test_permission_matrix`
parameterises both directions for every role.

**Fixtures through the API, not the ORM, in E2E.** If setup goes through the UI,
a broken button fails ten tests and hides which journey actually regressed.

**Nothing depends on the clock or the calendar.** Where behaviour is
time-dependent, the timestamp is passed in explicitly.

## What is deliberately not tested

- **The React components in isolation.** The journeys they exist for are
  covered end-to-end, and component tests of this UI would mostly assert that
  React renders props.
- **Third-party behaviour.** No test asserts that SQLAlchemy writes rows or
  that FastAPI parses JSON.
- **Scanner output.** The security jobs are the test; there is no test of the
  test.

## Adding a test

1. Pick the lowest layer that can answer the question.
2. If you are adding a rule, add the positive *and* the negative case.
3. If you are fixing a bug, write the failing test first and leave a one-line
   comment saying what the regression was — several tests here carry one.
4. Keep the suite fast: the backend suite runs in under two seconds, which is
   why people actually run it before pushing.
