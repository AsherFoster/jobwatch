---
name: verify
description: Build, launch, and drive jobwatch to verify a change end-to-end.
---

# Verifying jobwatch changes

Server-rendered FastAPI app; the surface is HTTP + HTML. Drive it with curl.

## Launch against a scratch database

Use the test environment — `config.test.toml` points at a separate
`jobwatch_test` database. There's no init command; a pytest run creates and
resets the test schema (via conftest.py), and running the tests first is due
diligence anyway:

```bash
docker compose up -d                 # Postgres on :5432
export ENVIRONMENT=test
uv run pytest                        # also creates/resets the jobwatch_test schema
uv run fastapi dev --port 8391 &     # app path comes from pyproject [tool.fastapi]
```

## Seed a job

There's no fixture command; insert via the ORM (with `ENVIRONMENT` still
exported):

```bash
uv run python -c "
from jobwatch.db import session_maker
from jobwatch.models import Job
with session_maker() as s:
    s.add(Job(site='linkedin', external_id='v1',
              title='Backend Engineer', company='Acme', location='Copenhagen',
              url='https://example.com/v1', description='Python things', raw='{}'))
    s.commit()
"
```

## Gotchas

- Everything except `pytest` needs `ENVIRONMENT` exported —
  `jobwatch.config` asserts it at import time; conftest.py forces it to
  `test` for pytest.
- Form POSTs answer 303; don't use `curl -L -X POST` — it re-POSTs the
  redirect target and 405s. Use `-d` (implies POST) or follow the Location
  header with a plain GET.
- Assessment flows need an LLM; avoid them in verification (or use the
  `FakeLLM` pattern from `web/app_test.py`).
- Inspect the DB with
  `docker compose exec postgres psql -U jobwatch jobwatch_test`.
