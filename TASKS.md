# TASKS.md — Healthcare Scheduler

Work top to bottom. Each phase should be a separate set of commits / Claude Code sessions.

## Phase 1 — Schema & concurrency guarantee
- [x] Set up Postgres with `btree_gist` and `vector` extensions enabled
- [x] Create `practitioners`, `patients`, `appointments` tables
- [x] Add `EXCLUDE USING GIST` constraint on `appointments`
- [x] Write a test that fires two concurrent overlapping booking attempts and asserts exactly one succeeds

## Phase 2 — Availability API
- [x] Model recurring working hours per practitioner
- [x] Slot generator (working hours → 30-min slots) in UTC
- [x] Subtract existing pending/accepted appointments from generated slots
- [x] `GET /practitioners/{id}/availability?date=` endpoint
- [x] Timezone conversion at the API boundary — write a test with a practitioner and patient in different timezones

## Phase 3 — Booking CRUD
- [ ] `POST /appointments` (wrapped in a transaction; catches the exclusion-constraint violation and returns a clean 409)
- [ ] `GET /appointments/{id}`, `PATCH /appointments/{id}` (cancel/reschedule)
- [ ] Outbox table + write-on-booking logic

## Phase 4 — Local dev environment
- [ ] Dockerfile for the API
- [ ] docker-compose.yml: api, postgres (with pgvector image), rabbitmq
- [ ] `.env.example` with all required variables

## Phase 5 — Symptom matching
- [ ] Embed practitioner specialty text on create/update, store in `specialty_embedding`
- [ ] `POST /match` endpoint: symptom text → embedding → top-N practitioners by cosine distance
- [ ] Add an index (IVFFlat or HNSW) once there's a realistic amount of seed data

## Phase 6 — Async email
- [ ] Outbox-polling worker process
- [ ] RabbitMQ publisher in the worker
- [ ] Email consumer service
- [ ] Retry/backoff on publish failure

## Phase 7 — Infra
- [ ] Terraform: ECR repo, EC2 instance, security group
- [ ] CI step to build + push image to ECR
- [ ] Deploy script / manual deploy steps documented in README

## Phase 8 — Stretch goals (pick based on time)
- [ ] Practitioner-side cancellation/no-show tracking
- [ ] Google Calendar sync for practitioners
- [ ] SMS reminders (Twilio) alongside email
- [ ] Basic auth + role-based access (patient vs practitioner vs admin)
- [ ] Rate limiting on the booking endpoint
- [ ] Structured logging + a simple health/metrics endpoint
