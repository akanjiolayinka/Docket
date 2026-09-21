# Docket — Healthcare Scheduler

See `CLAUDE.md` for design rules and conventions, `PLANNING.md` for the data model, and `TASKS.md` for phase-by-phase progress.

## Local setup (pre-Docker, Phase 1)

Docker Compose lands in Phase 4. Until then, run against a local Postgres 16 with the `btree_gist` and `vector` extensions available:

```bash
sudo apt-get install postgresql-16-pgvector

sudo -u postgres psql -c "CREATE ROLE docket LOGIN PASSWORD 'docket';"
sudo -u postgres psql -c "CREATE DATABASE docket OWNER docket;"
sudo -u postgres psql -c "CREATE DATABASE docket_test OWNER docket;"

# Extension creation requires superuser; the app role only needs USAGE.
sudo -u postgres psql -d docket -c "CREATE EXTENSION IF NOT EXISTS btree_gist; CREATE EXTENSION IF NOT EXISTS vector;"
sudo -u postgres psql -d docket_test -c "CREATE EXTENSION IF NOT EXISTS btree_gist; CREATE EXTENSION IF NOT EXISTS vector;"

cp .env.example .env
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

alembic upgrade head
pytest
```
