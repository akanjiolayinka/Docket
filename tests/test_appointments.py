import uuid


async def _count(db_conn, table, **where):
    clause = " AND ".join(f"{k} = %s" for k in where) or "TRUE"
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {clause}", tuple(where.values()))
        return cur.fetchone()[0]


async def test_book_appointment_writes_appointment_and_outbox_in_same_transaction(
    client, practitioner_id, patient_ids, db_conn
):
    patient_a, _ = patient_ids
    resp = await client.post(
        "/appointments",
        json={
            "patient_id": str(patient_a),
            "practitioner_id": str(practitioner_id),
            "start": "2030-01-07T09:00:00+00:00",
            "end": "2030-01-07T09:30:00+00:00",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["start_utc"] == "2030-01-07T09:00:00Z"

    appointment_id = body["id"]
    assert await _count(db_conn, "appointments", id=appointment_id) == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT payload->>'appointment_id' FROM outbox WHERE event_type = 'email_confirmation'"
        )
        rows = cur.fetchall()
    assert [r[0] for r in rows] == [appointment_id]


async def test_book_appointment_conflict_returns_409_and_writes_nothing(
    client, practitioner_id, patient_ids, db_conn
):
    patient_a, patient_b = patient_ids
    payload = {
        "patient_id": str(patient_a),
        "practitioner_id": str(practitioner_id),
        "start": "2030-01-07T09:00:00+00:00",
        "end": "2030-01-07T09:30:00+00:00",
    }
    first = await client.post("/appointments", json=payload)
    assert first.status_code == 201

    conflicting = dict(payload, patient_id=str(patient_b))
    second = await client.post("/appointments", json=conflicting)
    assert second.status_code == 409

    assert await _count(db_conn, "appointments", practitioner_id=practitioner_id) == 1
    assert await _count(db_conn, "outbox") == 1  # only the successful booking's event


async def test_book_appointment_unknown_patient_or_practitioner_is_404(client, practitioner_id, patient_ids):
    patient_a, _ = patient_ids
    resp = await client.post(
        "/appointments",
        json={
            "patient_id": str(uuid.uuid4()),
            "practitioner_id": str(practitioner_id),
            "start": "2030-01-07T09:00:00+00:00",
            "end": "2030-01-07T09:30:00+00:00",
        },
    )
    assert resp.status_code == 404

    resp = await client.post(
        "/appointments",
        json={
            "patient_id": str(patient_a),
            "practitioner_id": str(uuid.uuid4()),
            "start": "2030-01-07T09:00:00+00:00",
            "end": "2030-01-07T09:30:00+00:00",
        },
    )
    assert resp.status_code == 404


async def test_get_appointment_roundtrip_and_404(client, practitioner_id, patient_ids):
    patient_a, _ = patient_ids
    created = await client.post(
        "/appointments",
        json={
            "patient_id": str(patient_a),
            "practitioner_id": str(practitioner_id),
            "start": "2030-01-07T09:00:00+00:00",
            "end": "2030-01-07T09:30:00+00:00",
        },
    )
    appointment_id = created.json()["id"]

    resp = await client.get(f"/appointments/{appointment_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == appointment_id

    resp = await client.get(f"/appointments/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_cancel_appointment_frees_the_slot(client, practitioner_id, patient_ids):
    patient_a, patient_b = patient_ids
    payload = {
        "patient_id": str(patient_a),
        "practitioner_id": str(practitioner_id),
        "start": "2030-01-07T09:00:00+00:00",
        "end": "2030-01-07T09:30:00+00:00",
    }
    created = await client.post("/appointments", json=payload)
    appointment_id = created.json()["id"]

    # Slot is taken -- a second patient booking the same slot is rejected.
    conflicting = dict(payload, patient_id=str(patient_b))
    assert (await client.post("/appointments", json=conflicting)).status_code == 409

    cancel = await client.patch(f"/appointments/{appointment_id}", json={"status": "cancelled"})
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"

    # Now that it's cancelled, the same slot is bookable again.
    second = await client.post("/appointments", json=conflicting)
    assert second.status_code == 201


async def test_reschedule_appointment_moves_the_slot(client, practitioner_id, patient_ids):
    patient_a, _ = patient_ids
    created = await client.post(
        "/appointments",
        json={
            "patient_id": str(patient_a),
            "practitioner_id": str(practitioner_id),
            "start": "2030-01-07T09:00:00+00:00",
            "end": "2030-01-07T09:30:00+00:00",
        },
    )
    appointment_id = created.json()["id"]

    resp = await client.patch(
        f"/appointments/{appointment_id}",
        json={"start": "2030-01-07T10:00:00+00:00", "end": "2030-01-07T10:30:00+00:00"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["start_utc"] == "2030-01-07T10:00:00Z"
    assert body["status"] == "pending"


async def test_reschedule_into_a_taken_slot_returns_409(client, practitioner_id, patient_ids):
    patient_a, patient_b = patient_ids
    slot_a = {
        "patient_id": str(patient_a),
        "practitioner_id": str(practitioner_id),
        "start": "2030-01-07T09:00:00+00:00",
        "end": "2030-01-07T09:30:00+00:00",
    }
    slot_b = dict(slot_a, patient_id=str(patient_b), start="2030-01-07T10:00:00+00:00", end="2030-01-07T10:30:00+00:00")
    await client.post("/appointments", json=slot_a)
    appointment_b = (await client.post("/appointments", json=slot_b)).json()

    resp = await client.patch(
        f"/appointments/{appointment_b['id']}",
        json={"start": slot_a["start"], "end": slot_a["end"]},
    )
    assert resp.status_code == 409


async def test_cannot_modify_a_cancelled_appointment(client, practitioner_id, patient_ids):
    patient_a, _ = patient_ids
    created = await client.post(
        "/appointments",
        json={
            "patient_id": str(patient_a),
            "practitioner_id": str(practitioner_id),
            "start": "2030-01-07T09:00:00+00:00",
            "end": "2030-01-07T09:30:00+00:00",
        },
    )
    appointment_id = created.json()["id"]
    await client.patch(f"/appointments/{appointment_id}", json={"status": "cancelled"})

    resp = await client.patch(
        f"/appointments/{appointment_id}",
        json={"start": "2030-01-07T11:00:00+00:00", "end": "2030-01-07T11:30:00+00:00"},
    )
    assert resp.status_code == 409
