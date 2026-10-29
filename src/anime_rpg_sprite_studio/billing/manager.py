"""Persistent local guardrails, not a supplier billing cap. Decimal strings only."""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import secrets
import sqlite3
from uuid import uuid4

from .contracts import MonthSummary, SAFETY_LIMIT


def utc_now():
    return datetime.now(timezone.utc)


def money(value):
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError("金額必須是有限非負 Decimal")
    return value


def utc(value):
    if value.tzinfo is None:
        raise ValueError("時間必須包含 UTC 時區")
    return value.astimezone(timezone.utc)


def quote_json(quote):
    data = asdict(quote)
    data["estimated_cost"] = str(money(quote.estimated_cost))
    data["reservation_cost"] = str(money(quote.reservation_cost))
    data["expires_at"] = utc(quote.expires_at).isoformat()
    return json.dumps(data, sort_keys=True)


class SQLiteBudgetManager:
    def __init__(self, path, clock=utc_now):
        self.path = Path(path)
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS quotes(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS confirmations(token TEXT PRIMARY KEY,quote_id TEXT NOT NULL,used INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS requests(
                  id TEXT PRIMARY KEY, quote_id TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL,
                  month TEXT NOT NULL, model TEXT NOT NULL, fingerprint TEXT NOT NULL,
                  credential TEXT NOT NULL, estimate TEXT NOT NULL,reserved TEXT NOT NULL,
                  actual TEXT, billing_month TEXT,state TEXT NOT NULL,
                  provider_request_id TEXT UNIQUE,evidence TEXT NOT NULL DEFAULT '',billing_unresolved INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,request_id TEXT,at TEXT,action TEXT);
            """)
            if "billing_unresolved" not in {r[1] for r in db.execute("PRAGMA table_info(requests)")}:
                db.execute("ALTER TABLE requests ADD COLUMN billing_unresolved INTEGER NOT NULL DEFAULT 1")
                db.execute("UPDATE requests SET billing_unresolved=0 WHERE actual IS NOT NULL")

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _transaction(self):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise

    def _event(self, db, rid, action):
        db.execute("INSERT INTO events(request_id,at,action) VALUES(?,?,?)", (rid, utc(self.clock()).isoformat(), action))

    def validate_quote(self, q):
        quote_json(q)
        if q.provider != "fal" or q.model != "fal-ai/flux/schnell" or q.currency != "USD" or not q.credential_fingerprint:
            raise ValueError("不支援的 Provider／模型／幣別／憑證")
        if q.source != "https://api.fal.ai/v1/models/pricing" or q.pricing_unit not in {"image", "megapixel", "megapixels"}:
            raise ValueError("缺少可驗證的官方價格或計費單位")
        if q.estimated_cost <= 0 or q.reservation_cost < q.estimated_cost:
            raise ValueError("報價或保留額無效")
        now = utc(self.clock())
        if not now < utc(q.expires_at) <= now + timedelta(minutes=3):
            raise ValueError("報價已過期或有效期無效")

    def register_quote(self, q):
        self.validate_quote(q)
        with self._transaction() as db:
            db.execute("INSERT INTO quotes VALUES(?,?)", (q.id, quote_json(q)))

    def confirm_quote(self, quote_id):
        with self._transaction() as db:
            row = db.execute("SELECT payload FROM quotes WHERE id=?", (quote_id,)).fetchone()
            if row is None or utc(self.clock()) >= datetime.fromisoformat(json.loads(row[0])["expires_at"]):
                raise ValueError("請重新取得有效報價")
            token = secrets.token_urlsafe(32)
            db.execute("INSERT INTO confirmations(token,quote_id) VALUES(?,?)", (sha256(token.encode()).hexdigest(), quote_id))
            return token

    def _summary(self, db, month):
        datetime.strptime(month, "%Y-%m")
        rows = db.execute("SELECT * FROM requests").fetchall()
        confirmed = sum((Decimal(r["actual"]) for r in rows if r["actual"] is not None and r["billing_month"] == month), Decimal("0"))
        pending = sum((max(Decimal(r["reserved"]), Decimal(r["actual"] or "0")) for r in rows
                       if r["billing_unresolved"] and r["state"] != "RELEASED"), Decimal("0"))
        return MonthSummary(month, confirmed, pending, max(Decimal("0"), SAFETY_LIMIT - confirmed - pending))

    def get_month_summary(self, utc_month):
        with self._db() as db:
            return self._summary(db, utc_month)

    def reserve(self, q, confirmation):
        self.validate_quote(q)
        with self._transaction() as db:
            stored = db.execute("SELECT payload FROM quotes WHERE id=?", (q.id,)).fetchone()
            token = sha256(confirmation.encode()).hexdigest()
            auth = db.execute("SELECT * FROM confirmations WHERE token=? AND quote_id=? AND used=0", (token, q.id)).fetchone()
            if stored is None or stored[0] != quote_json(q) or auth is None:
                raise ValueError("需要本次報價的明確、未使用確認")
            if db.execute("SELECT 1 FROM requests WHERE (billing_unresolved=1 AND state!='RELEASED') OR state IN ('RESERVED','SUBMITTING','SUBMITTED','IN_QUEUE','IN_PROGRESS','CANCEL_REQUESTED','UNKNOWN')").fetchone():
                raise ValueError("尚有進行中或費用未決請求；禁止新生成")
            if db.execute("SELECT 1 FROM requests WHERE quote_id=?", (q.id,)).fetchone():
                raise ValueError("此報價已使用；不可重複提交")
            now = utc(self.clock())
            month = now.strftime("%Y-%m")
            if self._summary(db, month).available < q.reservation_cost:
                raise ValueError("超過 US$4.50 安全停止門檻")
            rid = str(uuid4())
            db.execute("""INSERT INTO requests(id,quote_id,created_at,month,model,fingerprint,credential,estimate,reserved,state)
                          VALUES(?,?,?,?,?,?,?,?,?,'RESERVED')""",
                       (rid, q.id, now.isoformat(), month, q.model, q.request_fingerprint, q.credential_fingerprint,
                        str(q.estimated_cost), str(q.reservation_cost)))
            db.execute("UPDATE confirmations SET used=1 WHERE token=?", (token,))
            self._event(db, rid, "reserved")
            return rid

    def get(self, rid):
        with self._db() as db:
            row = db.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone()
            if row is None:
                raise ValueError("未知請求")
            return dict(row)

    def list_requests(self):
        with self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM requests ORDER BY rowid DESC")]

    def claim(self, rid, fingerprint, credential):
        with self._transaction() as db:
            r = db.execute("SELECT r.*,q.payload FROM requests r JOIN quotes q ON q.id=r.quote_id WHERE r.id=?", (rid,)).fetchone()
            now = utc(self.clock())
            if r is None or r["state"] != "RESERVED" or r["fingerprint"] != fingerprint or r["credential"] != credential:
                raise ValueError("確認已使用、參數或 Key 已變更")
            if now >= datetime.fromisoformat(json.loads(r["payload"])["expires_at"]) or now.strftime("%Y-%m") != r["month"]:
                raise ValueError("報價過期或已跨 UTC 月份；請重新確認")
            summary = self._summary(db, now.strftime("%Y-%m"))
            if summary.confirmed + summary.pending_reservations > SAFETY_LIMIT:
                raise ValueError("費用已更新並超過安全門檻，禁止提交")
            if db.execute("SELECT 1 FROM requests WHERE id!=? AND ((billing_unresolved=1 AND state!='RELEASED') OR state IN ('RESERVED','SUBMITTING','SUBMITTED','IN_QUEUE','IN_PROGRESS','CANCEL_REQUESTED','UNKNOWN'))", (rid,)).fetchone():
                raise ValueError("其他請求有新未決費用或仍在執行，禁止提交")
            db.execute("UPDATE requests SET state='SUBMITTING' WHERE id=?", (rid,))
            self._event(db, rid, "submission_started")

    def mark_submitted(self, reservation_id, provider_request_id):
        with self._transaction() as db:
            result = db.execute("UPDATE requests SET state='SUBMITTED',provider_request_id=? WHERE id=? AND state='SUBMITTING'", (provider_request_id, reservation_id))
            if result.rowcount != 1:
                raise ValueError("請求不可再次提交")
            self._event(db, reservation_id, "submitted")

    def mark_unknown(self, rid, reason="unknown"):
        with self._transaction() as db:
            db.execute("UPDATE requests SET state='UNKNOWN',billing_unresolved=1 WHERE id=? AND state!='RELEASED'", (rid,))
            self._event(db, rid, "outcome_unknown")

    def set_state(self, rid, state):
        if state not in {"SUBMITTED", "IN_QUEUE", "IN_PROGRESS", "COMPLETED", "FAILED", "CANCEL_REQUESTED"}:
            raise ValueError("無效狀態")
        with self._transaction() as db:
            db.execute("UPDATE requests SET state=? WHERE id=? AND provider_request_id IS NOT NULL AND state!='RELEASED'", (state, rid))
            self._event(db, rid, state)

    def release_unsubmitted(self, rid):
        with self._transaction() as db:
            result = db.execute("UPDATE requests SET state='RELEASED' WHERE id=? AND state='RESERVED'", (rid,))
            if result.rowcount != 1:
                raise ValueError("只有確定尚未送出的保留額可釋放")
            self._event(db, rid, "released_before_submission")

    def reconcile(self, rid, actual_cost, evidence, billing_at=None):
        amount = money(actual_cost)
        if not evidence:
            raise ValueError("需要逐筆帳單證據")
        with self._transaction() as db:
            row = db.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone()
            if row is None or row["provider_request_id"] is None:
                raise ValueError("沒有可核對的供應商請求")
            month = utc(billing_at or datetime.fromisoformat(row["created_at"])).strftime("%Y-%m")
            db.execute("UPDATE requests SET actual=?,billing_month=?,evidence=?,billing_unresolved=0 WHERE id=?", (str(amount), month, evidence, rid))
            self._event(db, rid, "billing_confirmed")
