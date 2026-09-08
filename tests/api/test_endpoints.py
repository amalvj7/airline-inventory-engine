from datetime import UTC, datetime, timedelta

BASE = datetime(2026, 11, 1, 6, 0, tzinfo=UTC)
DEV_ORIGIN = "http://localhost:5173"


def _flight(client, number, origin, dest, capacity, factor=0.0, hour=0):
    r = client.post(
        "/flights",
        json={
            "flight_number": number,
            "origin": origin,
            "destination": dest,
            "departure_time": (BASE + timedelta(hours=hour)).isoformat(),
            "arrival_time": (BASE + timedelta(hours=hour + 2)).isoformat(),
            "physical_capacity": capacity,
            "overbooking_factor": str(factor),
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _passenger(client, name="Test", tier="STANDARD"):
    r = client.post("/passengers", json={"name": name, "tier": tier})
    assert r.status_code == 201, r.text
    return r.json()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["database"] == "reachable"


def test_create_flight_computes_booking_limit(client):
    body = _flight(client, "A1", "AAA", "BBB", capacity=4, factor=0.5)
    assert body["inventory"]["booking_limit"] == 6
    assert body["inventory"]["remaining"] == 6
    assert body["inventory"]["is_oversold"] is False


def test_arrival_before_departure_is_400(client):
    r = client.post(
        "/flights",
        json={
            "flight_number": "BAD1",
            "origin": "AAA",
            "destination": "BBB",
            "departure_time": (BASE + timedelta(hours=4)).isoformat(),
            "arrival_time": BASE.isoformat(),
            "physical_capacity": 3,
            "overbooking_factor": "0.0",
        },
    )
    assert r.status_code == 400
    assert r.json()["error"] == "INVALID_FLIGHT_TIMES"


def test_multi_leg_booking_returns_ordered_legs(client):
    f1 = _flight(client, "A1", "AAA", "BBB", capacity=3, hour=0)
    f2 = _flight(client, "A2", "BBB", "CCC", capacity=3, hour=3)
    p = _passenger(client)

    r = client.post(
        "/bookings",
        json={
            "passenger_id": p["id"],
            "legs": [{"flight_id": f1["id"]}, {"flight_id": f2["id"]}],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "CONFIRMED"
    assert [leg["sequence"] for leg in body["legs"]] == [1, 2]


def test_full_leg_returns_409_naming_the_flight(client):
    f = _flight(client, "A1", "AAA", "BBB", capacity=1)
    p1, p2 = _passenger(client, "One"), _passenger(client, "Two")

    client.post("/bookings", json={"passenger_id": p1["id"], "legs": [{"flight_id": f["id"]}]})
    r = client.post("/bookings", json={"passenger_id": p2["id"], "legs": [{"flight_id": f["id"]}]})

    assert r.status_code == 409
    body = r.json()
    assert body["error"] == "LEG_UNAVAILABLE"
    assert body["flight_number"] == "A1"
    assert body["booked_count"] == 1
    assert body["booking_limit"] == 1


def test_empty_leg_list_is_422(client):
    p = _passenger(client)
    r = client.post("/bookings", json={"passenger_id": p["id"], "legs": []})
    assert r.status_code == 422   # schema validation, never reaches the service


def test_unknown_flight_is_404(client):
    p = _passenger(client)
    r = client.post(
        "/bookings",
        json={
            "passenger_id": p["id"],
            "legs": [{"flight_id": "00000000-0000-0000-0000-000000000000"}],
        },
    )
    assert r.status_code == 404
    assert r.json()["error"] == "FLIGHT_NOT_FOUND"


def test_unknown_flight_path_lookup_is_404(client):
    r = client.get("/flights/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    assert r.json()["error"] == "FLIGHT_NOT_FOUND"


def test_unknown_booking_path_lookup_is_404(client):
    r = client.get("/bookings/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    assert r.json()["error"] == "BOOKING_NOT_FOUND"


def test_idempotency_key_returns_the_same_booking(client):
    f = _flight(client, "A1", "AAA", "BBB", capacity=3)
    p = _passenger(client)
    payload = {"passenger_id": p["id"], "legs": [{"flight_id": f["id"]}]}

    first = client.post("/bookings", json=payload, headers={"Idempotency-Key": "abc-123"})
    second = client.post("/bookings", json=payload, headers={"Idempotency-Key": "abc-123"})

    assert first.json()["id"] == second.json()["id"]
    inv = client.get(f"/flights/{f['id']}").json()["inventory"]
    assert inv["booked_count"] == 1   # retry did not consume a second seat


def test_cancel_releases_inventory(client):
    f = _flight(client, "A1", "AAA", "BBB", capacity=3)
    p = _passenger(client)
    b = client.post(
        "/bookings", json={"passenger_id": p["id"], "legs": [{"flight_id": f["id"]}]}
    ).json()

    r = client.post(f"/bookings/{b['id']}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "CANCELLED"
    assert client.get(f"/flights/{f['id']}").json()["inventory"]["booked_count"] == 0


def test_overbooking_patch_changes_the_limit(client):
    f = _flight(client, "A1", "AAA", "BBB", capacity=4, factor=0.0)
    r = client.patch(f"/flights/{f['id']}/overbooking", json={"overbooking_factor": "0.5"})
    assert r.status_code == 200
    assert r.json()["inventory"]["booking_limit"] == 6


def test_negative_overbooking_factor_is_422(client):
    f = _flight(client, "A1", "AAA", "BBB", capacity=4)
    r = client.patch(f"/flights/{f['id']}/overbooking", json={"overbooking_factor": "-0.1"})
    assert r.status_code == 422


def test_rebook_moves_the_leg(client):
    old = _flight(client, "A1", "AAA", "BBB", capacity=3, hour=0)
    new = _flight(client, "A2", "AAA", "BBB", capacity=3, hour=6)
    p = _passenger(client)
    b = client.post(
        "/bookings", json={"passenger_id": p["id"], "legs": [{"flight_id": old["id"]}]}
    ).json()

    r = client.post(
        f"/bookings/{b['id']}/rebook",
        json={"leg_id": b["legs"][0]["id"], "new_flight_id": new["id"]},
    )
    assert r.status_code == 200
    assert client.get(f"/flights/{old['id']}").json()["inventory"]["booked_count"] == 0
    assert client.get(f"/flights/{new['id']}").json()["inventory"]["booked_count"] == 1


def test_bump_endpoint_resolves_oversold_flight(client):
    f = _flight(client, "A1", "AAA", "BBB", capacity=1, factor=1.0)   # limit 2
    p1 = _passenger(client, "Platinum", "PLATINUM")
    p2 = _passenger(client, "Standard", "STANDARD")

    for p in (p1, p2):
        client.post("/bookings", json={"passenger_id": p["id"], "legs": [{"flight_id": f["id"]}]})

    r = client.post(f"/flights/{f['id']}/bump")
    assert r.status_code == 200
    assert r.json()["overage"] == 1
    assert len(r.json()["bumped_leg_ids"]) == 1


def test_preflight_is_allowed_for_the_dev_origin(client):
    r = client.options(
        "/bookings",
        headers={
            "Origin": DEV_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,idempotency-key",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == DEV_ORIGIN
    allowed = r.headers["access-control-allow-headers"].lower()
    assert "content-type" in allowed
    assert "idempotency-key" in allowed   # the retry path must survive CORS


def test_simple_request_carries_the_allow_origin_header(client):
    r = client.get("/flights", headers={"Origin": DEV_ORIGIN})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == DEV_ORIGIN


def test_error_responses_also_carry_cors_headers(client):
    f = _flight(client, "A1", "AAA", "BBB", capacity=1)
    p1, p2 = _passenger(client, "One"), _passenger(client, "Two")
    client.post("/bookings", json={"passenger_id": p1["id"], "legs": [{"flight_id": f["id"]}]})

    r = client.post(
        "/bookings",
        json={"passenger_id": p2["id"], "legs": [{"flight_id": f["id"]}]},
        headers={"Origin": DEV_ORIGIN},
    )
    assert r.status_code == 409
    # without this header the browser hides the body and the UI cannot say "sold out"
    assert r.headers["access-control-allow-origin"] == DEV_ORIGIN


def test_unknown_origin_is_not_granted_access(client):
    r = client.get("/flights", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_reconciliation_endpoint(client):
    f = _flight(client, "A1", "AAA", "BBB", capacity=3)
    p = _passenger(client)
    client.post("/bookings", json={"passenger_id": p["id"], "legs": [{"flight_id": f["id"]}]})

    r = client.get("/reconciliation")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    entry = next(x for x in body["flights"] if x["flight_number"] == "A1")
    assert entry["stored_booked"] == entry["expected_booked"] == 1
    assert entry["drift"] == 0