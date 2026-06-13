# Pixel Agent

Trainable AI "Display Specialist" that analyzes display-solution emails, extracts specs, drafts replies, and learns from human corrections via RAG/pgvector.

## What this is

A FastAPI backend plus a Streamlit UI for triaging display/electronics sales email. It ingests Outlook PST files, runs AI analysis (summary, intent, priority, specs, recommended parts, draft reply), and stores human corrections as training examples that are embedded and retrieved at inference time (RAG) to improve future output. Agent identity is "Pixel" / "Display Specialist".

## Stack

- Backend: FastAPI on Python 3.11 (uvicorn), port 8000
- Frontend: Streamlit, port 8501
- Database: PostgreSQL 16 + pgvector (image `pgvector/pgvector:pg16`), port 5432
- Cache: Redis 7 (`redis:7-alpine`), port 6379
- AI: OpenAI (chat model `gpt-4o-mini`, embeddings `text-embedding-ada-002`, vector dim 1536) — defaults set in `backend/config.py`
- ORM/DB access: SQLAlchemy (sync engine)
- PST parsing: `pypff` / `libpff` (built from source in the backend image)

## Where it runs

LOCAL ONLY. This project runs via `docker compose` on a dev machine. There is no VPS, no CI, and no remote deployment. (It does NOT run on the fleet's Hetzner VPS.)

The database is SELF-HOSTED Postgres running as a Docker container in this compose stack. It is NOT Supabase.

## Run locally

From the repo root (`pixel-agent/`):

```bash
# 1. Create your env file from the template, then fill in OPENAI_API_KEY
cp .env.example .env

# 2. Build and start all services (postgres -> redis -> backend -> frontend)
docker compose up -d --build

# 3. Watch logs
docker compose logs -f
```

Service startup order is enforced by compose: `postgres` and `redis` must pass healthchecks before `backend` starts; `frontend` starts after `backend`. The schema in `backend/db/init.sql` is auto-applied on first Postgres init (mounted as `/docker-entrypoint-initdb.d/01-schema.sql`).

URLs once up:
- Frontend (Streamlit): http://localhost:8501
- Backend API root: http://localhost:8000/
- Backend health: http://localhost:8000/health

Note: the backend Dockerfile builds `libpff`/`pypff` from source, so the first `--build` can take several minutes.

## Deploy

None documented. Local-only project; there is no deploy pipeline, no VPS target, and no CI configuration in the repo.

## Database

- Engine: self-hosted PostgreSQL 16 with the `pgvector` extension (and `uuid-ossp`).
- Schema: `backend/db/init.sql`, applied automatically on first container init. Data persists in the `./postgres_data` host directory (bind mount).
- Connection from the backend is built in `backend/config.py` (`database_url` property) from the `POSTGRES_*` settings; the host inside compose is `postgres`.

Key tables (see `backend/db/init.sql` for full definitions):
- `imports` — PST upload sessions and status
- `companies`, `contacts`, `email_threads` — entity/relationship data
- `emails` — parsed email records (dedupe via `dedupe_hash`)
- `email_insights` — AI analysis output per email
- `parts_recommended`, `tasks`, `opportunities`, `suppliers`, `part_ledger` — domain/CRM data
- `training_examples` — human-corrected examples used for learning
- `email_embeddings` — `vector(1536)` embeddings with an `ivfflat` cosine index for RAG
- `feedback_ratings`, `chat_sessions`

The supplier table is seeded with a known-supplier list at init time.

## Environment & secrets

Set these in `.env` (template: `.env.example`). Names only below — never commit real values.

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `OPENAI_API_KEY`
- `RAG_TOP_K`
- `CONFIDENCE_THRESHOLD`

`POSTGRES_HOST`, `POSTGRES_PORT`, `REDIS_HOST`, `REDIS_PORT`, and `BACKEND_URL` are set by `docker-compose.yml` for the in-cluster services and normally do not need to go in `.env`. Additional tunables (`OPENAI_MODEL`, `OPENAI_EMBEDDING_MODEL`, `AGENT_NAME`, `AGENT_ROLE`, `UPLOAD_DIR`) have defaults in `backend/config.py`.

`.env` is gitignored — keep secrets out of version control.

## Cron

None. No scheduled jobs are defined in this project.

## Day-to-day cheat sheet

```bash
# Start / rebuild
docker compose up -d --build

# Tail logs (all services, or one)
docker compose logs -f
docker compose logs -f backend

# Health check
curl http://localhost:8000/health

# Open a psql shell (uses values from your .env)
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"

# Stop (keeps data)
docker compose down

# Stop and wipe DB volume data (deletes ./postgres_data — destructive)
docker compose down && rm -rf ./postgres_data
```

Both `backend` and `frontend` bind-mount their source into the container and run with reload, so code edits are picked up live.

## Key files

- `docker-compose.yml` — the whole stack (services, ports, healthchecks, init.sql mount)
- `backend/main.py` — FastAPI app, routers, `/` and `/health` endpoints
- `backend/config.py` — settings, env var names, DB URL builder
- `backend/db/init.sql` — full Postgres + pgvector schema and seed data
- `backend/db/connection.py` — SQLAlchemy engine and query helpers
- `backend/Dockerfile` — backend image; builds `libpff`/`pypff` from source
- `frontend/app.py` — Streamlit entry point and navigation
- `.env.example` — environment template

## Gotchas

- `pypff`/`libpff` is built from source in `backend/Dockerfile` (cloned from GitHub, autotools + `make install`). The first build is slow, and a build failure there breaks PST import.
- The database is self-hosted Postgres in a container — NOT Supabase. Don't reach for Supabase tooling or env vars.
- This project is NOT deployed anywhere (no VPS, no CI). It runs only via local `docker compose`.
- Schema (`init.sql`) only runs on a fresh Postgres data dir. If you change the schema, you must drop/recreate the volume (`docker compose down && rm -rf ./postgres_data`) to re-apply it.
- An `OPENAI_API_KEY` is required for AI analysis and embeddings to work; without it those features fail.
