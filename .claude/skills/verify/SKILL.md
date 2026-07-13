---
name: verify
description: Build, launch, and drive jobwatch to verify a change end-to-end.
---

# Verifying jobwatch changes

Server-rendered FastAPI app; the surface is HTTP + HTML. Drive it with curl.

## Launch against a scratch database

`config.toml` is gitignored and may be absent; point `JOBWATCH_CONFIG` at a
minimal config with its own sqlite file:

```bash
cat > /tmp/verify-config.toml <<'EOF'
database_url = "sqlite:////tmp/verify.db"
EOF
export JOBWATCH_CONFIG=/tmp/verify-config.toml
uv run jobwatch init                 # create_all + alembic stamp
uv run fastapi dev --port 8391 &     # app path comes from pyproject [tool.fastapi]
```

## Seed a job

There's no fixture command; insert via the ORM:

```bash
uv run python -c "
from jobwatch.db import session_maker
from jobwatch.models import Job
with session_maker() as s:
    s.add(Job(site='linkedin', external_id='v1', search_name='swe-dk',
              title='Backend Engineer', company='Acme', location='Copenhagen',
              url='https://example.com/v1', description='Python things', raw='{}'))
    s.commit()
"
```

## Gotchas

- `uv run pytest` works bare (conftest.py points `JOBWATCH_CONFIG` at
  config.test.toml), but `uv run ty check` still needs the env var set.
- Form POSTs answer 303; don't use `curl -L -X POST` — it re-POSTs the
  redirect target and 405s. Use `-d` (implies POST) or follow the Location
  header with a plain GET.
- Assessment flows need an LLM; avoid them in verification (or use the
  `FakeLLM` pattern from `web/app_test.py`).
- No `sqlite3` CLI in the sandbox; inspect the DB via `uv run python`.
