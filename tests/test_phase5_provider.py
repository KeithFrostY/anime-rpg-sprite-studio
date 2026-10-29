from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image


class Credentials:
    def get_key_for_provider(self, provider):
        assert provider == "fal"
        return "FAKE-FAL-KEY"


class FakeHttp:
    def __init__(self):
        self.calls = []
        self.remote = str(uuid4())
        self.timeout = False
        self.unit = "image"
        self.events = []
    def json(self, method, url, *, key, payload=None):
        self.calls.append((method, url, key, payload))
        if "/pricing?" in url:
            return {"prices": [{"endpoint_id": "fal-ai/flux/schnell", "unit_price": Decimal("0.012"), "unit": self.unit, "currency": "USD"}]}
        if "billing-events?" in url:
            return {"billing_events": self.events, "has_more": False, "next_cursor": None}
        if method == "POST":
            if self.timeout:
                raise ValueError("simulated timeout")
            return {"request_id": self.remote}
        if method == "PUT":
            return {"status": "CANCELLATION_REQUESTED"}
        if url.endswith("/status"):
            return {"status": "COMPLETED"}
        return {"images": [{"url": "https://v3.fal.media/files/fake.png"}]}
    def request(self, method, url, *, key=None, **kwargs):
        self.calls.append((method, url, key, None))
        assert key is None
        stream = BytesIO()
        Image.new("RGBA", (256, 256)).save(stream, format="PNG")
        return stream.getvalue()


def setup(tmp_path):
    from anime_rpg_sprite_studio.ai.fal_provider import FalProvider
    from anime_rpg_sprite_studio.ai.contracts import GenerationRequest
    from anime_rpg_sprite_studio.billing.manager import SQLiteBudgetManager
    clock = lambda: datetime(2026, 10, 29, tzinfo=timezone.utc)
    budget = SQLiteBudgetManager(tmp_path / "budget.sqlite3", clock=clock)
    http = FakeHttp()
    provider = FalProvider(Credentials(), budget, http=http, clock=clock)
    request = GenerationRequest("hero", model="fal-ai/flux/schnell")
    return provider, budget, http, request


def test_quote_submit_once_download_and_billing(tmp_path):
    p, b, h, request = setup(tmp_path)
    q = p.estimate(request)
    assert q.estimated_cost == Decimal("0.012")
    rid = b.reserve(q, b.confirm_quote(q.id))
    handle = p.submit(request, rid)
    with pytest.raises(ValueError):
        p.submit(request, rid)
    assert len([c for c in h.calls if c[0] == "POST"]) == 1
    assert p.get_status(handle).state == "COMPLETED"
    result = p.fetch_result(handle)
    assert result.png.startswith(b"\x89PNG") and "fal.ai" in result.label
    assert b.get(rid)["actual"] is None
    assert p.sync_billing(rid) is False  # Missing event is NOT zero.
    h.events = [{"request_id": h.remote, "endpoint_id": request.model,
                 "timestamp": "2026-10-29T00:00:00Z", "cost_total": Decimal("0.010")}]
    assert p.sync_billing(rid)
    assert b.get(rid)["actual"] == "0.010"
    assert all(key is None for method, url, key, payload in h.calls if "fal.media" in url)


def test_timeout_keeps_reservation_and_never_retries(tmp_path):
    p, b, h, request = setup(tmp_path)
    q = p.estimate(request)
    rid = b.reserve(q, b.confirm_quote(q.id))
    h.timeout = True
    with pytest.raises(ValueError):
        p.submit(request, rid)
    assert b.get(rid)["state"] == "UNKNOWN" and b.get(rid)["actual"] is None
    with pytest.raises(ValueError):
        p.submit(request, rid)
    assert len([c for c in h.calls if c[0] == "POST"]) == 1


def test_cancel_does_not_release_cost(tmp_path):
    p, b, h, request = setup(tmp_path)
    q = p.estimate(request)
    rid = b.reserve(q, b.confirm_quote(q.id))
    handle = p.submit(request, rid)
    assert p.cancel(handle).state == "CANCEL_REQUESTED"
    assert b.get(rid)["actual"] is None
    with pytest.raises(ValueError):
        b.release_unsubmitted(rid)


def test_unknown_price_unit_blocks_before_submission(tmp_path):
    p, b, h, request = setup(tmp_path)
    h.unit = "gpu_second"
    with pytest.raises(ValueError):
        p.estimate(request)
    assert not any(c[0] == "POST" for c in h.calls)


def test_request_change_prevents_paid_post(tmp_path):
    from dataclasses import replace
    p, b, h, request = setup(tmp_path)
    q = p.estimate(request)
    rid = b.reserve(q, b.confirm_quote(q.id))
    with pytest.raises(ValueError):
        p.submit(replace(request, prompt="different"), rid)
    assert not any(c[0] == "POST" for c in h.calls)


def test_later_cross_month_adjustment_blocks_new_and_reserved_submissions(tmp_path):
    p, b, h, request = setup(tmp_path)
    q = p.estimate(request)
    rid = b.reserve(q, b.confirm_quote(q.id))
    handle = p.submit(request, rid)
    p.get_status(handle)
    event = {"request_id": h.remote, "endpoint_id": request.model,
             "timestamp": "2026-10-29T00:00:00Z", "cost_total": Decimal("0.01")}
    h.events = [event]
    assert p.sync_billing(rid)
    next_quote = p.estimate(request)
    next_rid = b.reserve(next_quote, b.confirm_quote(next_quote.id))
    h.events.append(dict(event, timestamp="2026-11-01T00:00:00Z", cost_total=Decimal("0.50")))
    with pytest.raises(ValueError):
        p.sync_billing(rid)
    with pytest.raises(ValueError):
        p.submit(request, next_rid)
    assert b.get(rid)["state"] == "UNKNOWN"
    assert b.get(rid)["actual"] == "0.01"
    p.get_status(handle)
    assert b.get(rid)["billing_unresolved"] == 1
    with pytest.raises(ValueError):
        p.submit(request, next_rid)
    assert len([c for c in h.calls if c[0] == "POST"]) == 1


def test_zero_is_confirmed_only_by_matching_billing_event(tmp_path):
    p, b, h, request = setup(tmp_path)
    q = p.estimate(request)
    rid = b.reserve(q, b.confirm_quote(q.id))
    handle = p.submit(request, rid)
    p.get_status(handle)
    assert not p.sync_billing(rid) and b.get(rid)["actual"] is None
    h.events = [{"request_id": h.remote, "endpoint_id": request.model,
                 "timestamp": "2026-10-29T00:00:00Z", "cost_total": Decimal("0")}]
    assert p.sync_billing(rid)
    assert b.get(rid)["actual"] == "0" and not b.get(rid)["billing_unresolved"]
