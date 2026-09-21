# CLAUDE.md — Healthcare Scheduler

This file is read by Claude Code before it touches the repo. Keep it accurate as the project evolves — it's the source of truth for how this codebase should be built and touched.

## What this is

A Calendly-style booking system for healthcare, where patients describe symptoms in plain text and get matched to a suitable practitioner, then book a slot without any risk of double-booking that practitioner.

## Tech stack

* Backend: Python, FastAPI
* Database: PostgreSQL (with `pgvector` and `btree_gist` extensions)
* Embeddings: Hugging Face sentence-transformers (`all-MiniLM-L6-v2`, 384-dim) for symptom → specialist matching
* Queue: RabbitMQ, for async email delivery
* Containers: Docker + Docker Compose (api, db, rabbitmq, worker services)
* Infra: Terraform, targeting AWS (EC2 + ECR)

## Non-negotiable design rules

* No double-bookings, ever — enforced at the database level with a Postgres `EXCLUDE USING GIST` constraint, not just app-level checks. App-level checks are a nice-to-have for a fast error message; the constraint is what actually guarantees correctness under concurrent requests.
* All times stored in UTC. Convert to local timezone only at the API boundary (request/response), never in business logic.
* Every multi-step write is a transaction. If a step fails, nothing partial should be left in the database.
* Outbox pattern for emails. Write the "send email" event to an `outbox` table in the same transaction as the booking. A separate worker polls the outbox and publishes to RabbitMQ — never publish to the queue from inside a transaction that might roll back.

## Build order (don't skip ahead)

1. Postgres schema + exclusion constraint, with a concurrency test proving it holds
2. Availability API (slot generation + subtraction of existing bookings)
3. Core REST CRUD (patients, practitioners, appointments)
4. Docker Compose for local dev
5. pgvector symptom-matching
6. Outbox + RabbitMQ worker for emails
7. Terraform + AWS deploy

## Conventions

* Type hints everywhere; Pydantic models for all request/response schemas.
* One router per resource (`routers/appointments.py`, `routers/practitioners.py`, etc.).
* No business logic in route handlers — routes call service functions, service functions call the DB layer.
* Every new endpoint needs at least one test that exercises the actual database (not mocked), since so much of this project's correctness lives in the database constraints.

## Commands

```bash
docker compose up -d          # start db, rabbitmq
uvicorn app.main:app --reload # run API locally
pytest                        # run tests
```
