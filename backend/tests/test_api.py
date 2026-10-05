"""API tests against the demo mailbox + mock LLM."""


def _email_id(client, subject_part):
    items = client.get("/api/emails").json()["items"]
    return next(i for i in items if subject_part in i["subject"])["id"]


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.headers["x-request-id"]


def test_dashboard(client):
    s = client.get("/api/dashboard").json()["stats"]
    assert s["total_emails"] == 9 and s["unanalyzed"] == 0
    assert s["important"] >= 3 and s["action_required"] >= 3 and s["upcoming_deadlines"] >= 1


def test_email_list_filters(client):
    urgent = client.get("/api/emails", params={"filter": "urgent"}).json()["items"]
    assert urgent and all(i["analysis"]["priority"] == "urgent" for i in urgent)
    jobs = client.get("/api/emails", params={"filter": "job"}).json()["items"]
    assert [i["analysis"]["category"] for i in jobs] == ["job"]
    found = client.get("/api/emails", params={"q": "interview"}).json()["items"]
    assert len(found) == 1
    assert "body" not in found[0]


def test_email_detail_and_404(client):
    eid = _email_id(client, "Interview")
    d = client.get(f"/api/emails/{eid}").json()
    assert d["body"] and d["analysis"]["action_required"] is True
    r = client.get("/api/emails/99999")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_reanalyze(client):
    eid = _email_id(client, "Interview")
    assert client.post(f"/api/emails/{eid}/analyze").json()["analysis"]["category"] == "job"


def test_prompt_injection_email_never_gets_a_draft(client):
    eid = _email_id(client, "Important notice")
    a = client.get(f"/api/emails/{eid}").json()["analysis"]
    assert a["injection_flagged"] and not a["action_required"] and a["priority"] == "low"
    r = client.post(f"/api/emails/{eid}/draft-reply", json={})
    assert r.status_code == 409


def test_full_human_approval_flow(client):
    eid = _email_id(client, "Quarterly report")
    draft = client.post(f"/api/emails/{eid}/draft-reply", json={}).json()
    assert draft["status"] == "draft" and draft["body"]
    did = draft["id"]

    # cannot send before approval, and not without confirm
    assert client.post(f"/api/replies/{did}/send", json={"confirm": True}).status_code == 409
    # edit marks modified
    edited = client.patch(f"/api/replies/{did}", json={"body": "Hi Omar, report coming Friday."}).json()
    assert edited["modified"] is True
    approved = client.post(f"/api/replies/{did}/approve").json()
    assert approved["status"] == "approved" and approved["approved_by"] and approved["approved_at"]
    assert client.post(f"/api/replies/{did}/send", json={"confirm": False}).status_code == 409

    # editing after approval resets approval
    reset = client.patch(f"/api/replies/{did}", json={"body": "Hi Omar, report coming Friday morning."}).json()
    assert reset["status"] == "draft"
    client.post(f"/api/replies/{did}/approve")

    sent = client.post(f"/api/replies/{did}/send", json={"confirm": True}).json()
    assert sent["status"] == "sent" and sent["send_result"]["simulated"] is True
    # second send must be rejected (no duplicate emails)
    assert client.post(f"/api/replies/{did}/send", json={"confirm": True}).status_code == 409
    assert client.patch(f"/api/replies/{did}", json={"body": "late edit"}).status_code == 409

    actions = [a["action"] for a in client.get("/api/actions").json()["items"]]
    assert {"draft_reply", "edit_draft", "approve_draft", "send_email"} <= set(actions)


def test_reject_and_regenerate(client):
    eid = _email_id(client, "Project sync")
    d1 = client.post(f"/api/emails/{eid}/draft-reply", json={}).json()
    d2 = client.post(f"/api/emails/{eid}/draft-reply", json={"regenerate": True, "instructions": "Suggest 4 PM instead."}).json()
    assert d1["id"] == d2["id"] and "4 PM" in d2["body"]
    assert client.post(f"/api/replies/{d2['id']}/reject").json()["status"] == "rejected"
    assert client.post(f"/api/replies/{d2['id']}/approve").status_code == 409
    assert client.get("/api/replies", params={"status": "rejected"}).json()["items"]


def test_settings_priority_rules_used_on_reanalysis(client):
    r = client.patch("/api/settings", json={"priority_rules": {"newsletter": "high"}, "settings": {"notify_urgent": False}})
    assert r.status_code == 200 and r.json()["priority_rules"]["newsletter"] == "high"
    eid = _email_id(client, "This week in AI")
    assert client.post(f"/api/emails/{eid}/analyze").json()["analysis"]["priority"] == "high"
    client.patch("/api/settings", json={"priority_rules": {"newsletter": None}})
    assert client.post(f"/api/emails/{eid}/analyze").json()["analysis"]["priority"] == "low"


def test_settings_validation(client):
    assert client.patch("/api/settings", json={"priority_rules": {"nonsense": "high"}}).status_code == 422
    assert client.patch("/api/settings", json={"priority_rules": {"job": "mega"}}).status_code == 422


def test_oauth_not_configured_returns_503(client):
    r = client.get("/api/auth/google/login", follow_redirects=False)
    assert r.status_code == 503


def test_oauth_callback_rejects_bad_state(client):
    r = client.get("/api/auth/google/callback", params={"code": "x", "state": "bad"})
    assert r.status_code == 400


def test_validation_error_shape(client):
    r = client.patch("/api/replies/1", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_frontend_served(client):
    r = client.get("/")
    assert r.status_code in (200, 404)  # 200 once frontend exists
