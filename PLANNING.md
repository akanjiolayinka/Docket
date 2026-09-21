# PLANNING.md — Healthcare Scheduler

## Core entities

**Patient** — id, name, contact info, symptom history (optional)

**Practitioner** — id, name, specialty text, specialty_embedding (vector), working_hours (recurring rule: days, start_time, end_time, timezone)

**Appointment** — id, patient_id, practitioner_id, time_range (tstzrange), status (`pending` / `accepted` / `cancelled` / `completed`)

**Outbox** — id, event_type, payload, created_at, published_at (nullable)

## Data flow: booking a slot

1. Patient requests available slots for a practitioner + date → API generates working-hour slots, subtracts existing pending/accepted appointments, returns free ones.
2. Patient picks a slot → API attempts insert. The exclusion constraint is the actual guarantee here; an app-level pre-check just gives a friendlier error message before hitting the DB.
3. On success, inside the same transaction: write appointment row + outbox row (`email_confirmation` event).
4. Background worker polls outbox, publishes to RabbitMQ, marks `published_at`.
5. Email worker consumes from RabbitMQ, sends the email.

## Data flow: symptom matching

1. Patient submits free-text symptom description.
2. Text → embedding (Hugging Face model, done at request time).
3. Query practitioners ordered by cosine distance between symptom embedding and each practitioner's specialty_embedding.
4. Return top N candidates, then patient picks one and proceeds to the booking flow above.

## Why an exclusion constraint over just app-level locking

App-level "check then insert" has a race window: two requests can both pass the check before either inserts. Options to close that gap are (a) a `SELECT ... FOR UPDATE` lock, or (b) a database constraint. The exclusion constraint is preferred here because it holds regardless of which code path writes to the table — including a future admin panel, a data migration script, or a bug — rather than relying on every write path remembering to lock correctly.

## Open design decisions to make before coding

- Does a practitioner *approve* pending bookings, or are they auto-accepted? (Affects whether `pending` blocks other bookings the same way `accepted` does — current plan: yes, both block, to avoid double-booking during the approval window.)
- Recurring working hours vs. per-day overrides (holidays, half-days) — recommend building the override table from day one, it's much more painful to bolt on later.
- Cancellation policy — does cancelling free the slot immediately, or is there a notice window?

## Phase roadmap

| Phase | Goal |
|---|---|
| 1 | Schema + exclusion constraint + concurrency test |
| 2 | Availability API |
| 3 | Booking CRUD + transactions |
| 4 | Docker Compose local environment |
| 5 | pgvector matching |
| 6 | Outbox + RabbitMQ + email worker |
| 7 | Terraform + AWS deploy |
| 8 | Stretch goals (see improvements below) |
