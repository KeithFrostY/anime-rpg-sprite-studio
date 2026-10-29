from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor

import pytest

NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)


def quote(amount="0.01", **overrides):
    from anime_rpg_sprite_studio.ai.contracts import Quote
    q = Quote("fal", "fal-ai/flux/schnell", "fingerprint", Decimal(amount), Decimal(amount),
              "https://api.fal.ai/v1/models/pricing", NOW + timedelta(minutes=2),
              credential_fingerprint="key-hash", pricing_unit="image")
    return replace(q, **overrides)


def manager(tmp_path, clock=lambda: NOW):
    from anime_rpg_sprite_studio.billing.manager import SQLiteBudgetManager
    return SQLiteBudgetManager(tmp_path / "budget.sqlite3", clock=clock)


def reserve(m, q):
    m.register_quote(q)
    return m.reserve(q, m.confirm_quote(q.id))


def test_single_use_confirmation_unknown_restart_cross_month(tmp_path):
    m = manager(tmp_path)
    q = quote()
    m.register_quote(q)
    token = m.confirm_quote(q.id)
    rid = m.reserve(q, token)
    m.claim(rid, "fingerprint", "key-hash")
    m.mark_unknown(rid, "submission_unknown")
    assert m.get_month_summary("2026-10").pending_reservations == Decimal("0.01")
    m2 = manager(tmp_path)
    assert m2.get(rid)["actual"] is None
    assert m2.get_month_summary("2026-11").pending_reservations == Decimal("0.01")
    with pytest.raises(ValueError):
        m2.reserve(q, token)
    with pytest.raises(ValueError):
        reserve(m2, quote())
    with pytest.raises(ValueError):
        m2.release_unsubmitted(rid)


def test_threshold_and_actual_reconciliation(tmp_path):
    m = manager(tmp_path)
    rid = reserve(m, quote("4.49"))
    m.claim(rid, "fingerprint", "key-hash")
    m.mark_submitted(rid, "remote-request")
    m.set_state(rid, "COMPLETED")
    m.reconcile(rid, Decimal("4.49"), "official-billing-event", NOW)
    with pytest.raises(ValueError):
        reserve(m, quote("0.02"))
    r2 = reserve(m, quote("0.01"))
    assert m.get_month_summary("2026-10").available == Decimal("0.00")
    m.release_unsubmitted(r2)
    assert m.get_month_summary("2026-10").confirmed == Decimal("4.49")
    m.reconcile(rid, Decimal("5.25"), "corrected-official-event", NOW)
    assert m.get_month_summary("2026-10").available == Decimal("0")


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-1"), 0.01])
def test_rejects_invalid_money(tmp_path, value):
    with pytest.raises(ValueError):
        reserve(manager(tmp_path), quote(estimated_cost=value, reservation_cost=value))


def test_expired_changed_quote_and_credentials_rejected(tmp_path):
    m = manager(tmp_path)
    q = quote()
    m.register_quote(q)
    token = m.confirm_quote(q.id)
    with pytest.raises(ValueError):
        m.reserve(replace(q, estimated_cost=Decimal("0.001")), token)
    rid = m.reserve(q, token)
    with pytest.raises(ValueError):
        m.claim(rid, "changed-prompt", "key-hash")
    with pytest.raises(ValueError):
        m.claim(rid, "fingerprint", "different-key")
    m.release_unsubmitted(rid)
    with pytest.raises(ValueError):
        reserve(m, quote(expires_at=NOW - timedelta(seconds=1)))


def test_concurrent_managers_allow_only_one_reservation(tmp_path):
    m = manager(tmp_path)
    items = []
    for _ in range(2):
        q = quote()
        m.register_quote(q)
        items.append((q, m.confirm_quote(q.id)))
    def attempt(item):
        try:
            return manager(tmp_path).reserve(*item)
        except ValueError:
            return None
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(attempt, items))
    assert sum(result is not None for result in results) == 1


def test_expiry_after_reservation_prevents_submission(tmp_path):
    clock = [NOW]
    m = manager(tmp_path, lambda: clock[0])
    rid = reserve(m, quote())
    clock[0] += timedelta(minutes=3)
    with pytest.raises(ValueError):
        m.claim(rid, "fingerprint", "key-hash")
    assert m.get(rid)["state"] == "RESERVED"


def test_confirmed_but_still_running_blocks_new_request(tmp_path):
    m = manager(tmp_path)
    rid = reserve(m, quote())
    m.claim(rid, "fingerprint", "key-hash")
    m.mark_submitted(rid, "remote")
    m.reconcile(rid, Decimal("0.01"), "event", NOW)
    with pytest.raises(ValueError):
        reserve(m, quote())


def test_cost_correction_after_reserve_rechecked_before_submit(tmp_path):
    m = manager(tmp_path)
    r1 = reserve(m, quote())
    m.claim(r1, "fingerprint", "key-hash")
    m.mark_submitted(r1, "remote")
    m.set_state(r1, "COMPLETED")
    m.reconcile(r1, Decimal("0.01"), "event", NOW)
    r2 = reserve(m, quote())
    m.reconcile(r1, Decimal("4.50"), "correction", NOW)
    with pytest.raises(ValueError):
        m.claim(r2, "fingerprint", "key-hash")
