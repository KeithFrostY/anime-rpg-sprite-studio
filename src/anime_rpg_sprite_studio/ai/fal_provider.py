"""One real provider. All paid POSTs require an atomically consumed reservation."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
from urllib.parse import urlencode
from uuid import UUID

from PIL import Image

from .contracts import Quote, JobHandle, GenerationResult
from .http import SafeHttp, validate_url
from ..billing.manager import money, utc, utc_now

MODEL = "fal-ai/flux/schnell"
PRICE_URL = "https://api.fal.ai/v1/models/pricing"
QUEUE_URL = "https://queue.fal.run/fal-ai/flux"
BILLING_URL = "https://api.fal.ai/v1/models/billing-events"


def fingerprint(request):
    return sha256(json.dumps(asdict(request), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def key_fingerprint(key):
    return sha256(key.encode()).hexdigest()


def decimal_amount(value):
    if not isinstance(value, (str, int, Decimal)) or isinstance(value, bool):
        raise ValueError("無效官方金額")
    return money(Decimal(value))


def candidate_png(data):
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("候選圖片超過大小限制")
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format != "PNG" or getattr(image, "n_frames", 1) != 1 or not all(0 < size <= 2048 for size in image.size):
                raise ValueError()
            image.load()
            output = BytesIO()
            image.convert("RGBA").save(output, format="PNG")
            return output.getvalue()
    except Exception:
        raise ValueError("候選不是有效單幀 PNG，或尺寸超出限制") from None


class FalProvider:
    def __init__(self, credentials, budget, http=None, clock=utc_now):
        self.credentials = credentials
        self.budget = budget
        self.http = http if http is not None else SafeHttp()
        self.clock = clock

    def capabilities(self):
        return {"provider": "fal", "models": [MODEL], "paid": True}

    def _validate(self, request):
        if request.model != MODEL or (request.width, request.height, request.count) != (256, 256, 1):
            raise ValueError("只支援 FLUX.1 Schnell、256×256、每次一張")
        if not isinstance(request.prompt, str) or not request.prompt.strip() or len(request.prompt) > 4000:
            raise ValueError("提示詞必須為 1–4000 字")
        if type(request.seed) is not int or not 0 <= request.seed <= 2147483647:
            raise ValueError("Seed 超出範圍")

    def test_key(self):
        key = self.credentials.get_key_for_provider("fal")
        # Read-only pricing endpoint; never test a key by running a model.
        data = self.http.json("GET", PRICE_URL + "?" + urlencode({"endpoint_id": MODEL}), key=key)
        if not isinstance(data.get("prices"), list) or not any(p.get("endpoint_id") == MODEL for p in data["prices"] if isinstance(p, dict)):
            raise ValueError("未取得有效價格查詢回應；Key 尚未驗證")
        return "fal.ai 價格查詢驗證成功；未執行生圖，未驗證帳單讀取權限"

    def estimate(self, request):
        self._validate(request)
        key = self.credentials.get_key_for_provider("fal")
        try:
            data = self.http.json("GET", PRICE_URL + "?" + urlencode({"endpoint_id": MODEL}), key=key)
            rows = [p for p in data["prices"] if p["endpoint_id"] == MODEL]
            if len(rows) != 1:
                raise ValueError()
            price = rows[0]
            unit = price["unit"]
            if price["currency"] != "USD" or unit not in {"image", "megapixel", "megapixels"}:
                raise ValueError()
            amount = decimal_amount(price["unit_price"])
            if amount <= 0:
                raise ValueError()
        except Exception:
            raise ValueError("無法確認官方價格／計費單位，禁止付費提交") from None
        # Conservative whole image / whole megapixel, not a historical average.
        quote = Quote("fal", MODEL, fingerprint(request), amount, amount, PRICE_URL,
                      utc(self.clock()) + timedelta(minutes=2),
                      credential_fingerprint=key_fingerprint(key), pricing_unit=unit)
        self.budget.register_quote(quote)
        return quote

    def submit(self, request, authorization):
        self._validate(request)
        key = self.credentials.get_key_for_provider("fal")
        self.budget.claim(authorization, fingerprint(request), key_fingerprint(key))
        try:
            data = self.http.json("POST", QUEUE_URL + "/schnell", key=key, payload={
                "prompt": request.prompt, "image_size": {"width": 256, "height": 256},
                "num_images": 1, "seed": request.seed, "num_inference_steps": 4,
                "enable_safety_checker": True, "output_format": "png", "sync_mode": False,
            })
            remote = str(UUID(data["request_id"]))
            self.budget.mark_submitted(authorization, remote)
            return JobHandle("fal", remote, "IN_QUEUE")
        except Exception:
            self.budget.mark_unknown(authorization, "submission_unknown")
            raise ValueError("提交結果不明；未重試，費用保留。請查看帳本與供應商紀錄。") from None

    def _row(self, handle):
        if handle.provider != "fal":
            raise ValueError("Provider 不符")
        remote = str(UUID(handle.request_id))
        for row in self.budget.list_requests():
            if row["provider_request_id"] == remote:
                return row
        raise ValueError("請求不屬於本機帳本")

    def _url(self, handle, suffix=""):
        self._row(handle)
        return QUEUE_URL + "/requests/" + str(UUID(handle.request_id)) + suffix

    def get_status(self, handle):
        row = self._row(handle)
        data = self.http.json("GET", self._url(handle, "/status"), key=self.credentials.get_key_for_provider("fal"))
        state = data.get("status")
        if state not in {"IN_QUEUE", "IN_PROGRESS", "COMPLETED"}:
            raise ValueError("供應商狀態未知；保留費用")
        if data.get("error"):
            state = "FAILED"
        self.budget.set_state(row["id"], state)
        return JobHandle("fal", handle.request_id, state)

    def cancel(self, handle):
        row = self._row(handle)
        # Persist intent before requesting cancellation; cost never released here.
        self.budget.set_state(row["id"], "CANCEL_REQUESTED")
        self.http.json("PUT", self._url(handle, "/cancel"), key=self.credentials.get_key_for_provider("fal"))
        return JobHandle("fal", handle.request_id, "CANCEL_REQUESTED")

    def fetch_result(self, handle):
        data = self.http.json("GET", self._url(handle), key=self.credentials.get_key_for_provider("fal"))
        try:
            if len(data["images"]) != 1:
                raise ValueError()
            url = data["images"][0]["url"]
            validate_url(url, authenticated=False)
            raw = self.http.request("GET", url, max_bytes=8 * 1024 * 1024)  # NEVER pass key to CDN.
            return GenerationResult(candidate_png(raw), "fal.ai 候選素材；不保證透明、四方向或分層")
        except Exception:
            raise ValueError("無法安全取得候選圖片；保留費用，可再次查詢原請求") from None

    def sync_billing(self, rid):
        row = self.budget.get(rid)
        if not row["provider_request_id"]:
            raise ValueError("尚無供應商 ID，不能推定費用為零")
        start = datetime.fromisoformat(row["created_at"]) - timedelta(days=1)
        end = utc(self.clock()) + timedelta(seconds=1)
        if end - start > timedelta(days=90):
            raise ValueError("超出帳單 API 查詢範圍，保留未決狀態")
        key = self.credentials.get_key_for_provider("fal")
        cursor, matches, seen = None, [], set()
        for _ in range(20):
            query = {"endpoint_id": MODEL, "start": start.isoformat(), "end": end.isoformat(), "limit": 200}
            if cursor:
                query["cursor"] = cursor
            data = self.http.json("GET", BILLING_URL + "?" + urlencode(query), key=key)
            for event in data["billing_events"]:
                if event["request_id"] == row["provider_request_id"] and event["endpoint_id"] == MODEL:
                    matches.append(event)
            if data.get("has_more") is False and not data.get("next_cursor"):
                break
            cursor = data.get("next_cursor")
            if not cursor or cursor in seen:
                raise ValueError("帳單分頁不完整；保留未決額")
            seen.add(cursor)
        else:
            raise ValueError("帳單過多，無法完整核對；保留未決額")
        if not matches:
            return False
        # New matching evidence must be revalidated before a previously settled
        # request may authorize more spending. Keep the prior confirmed amount.
        self.budget.mark_unknown(rid, "billing_under_review")
        try:
            amounts = [decimal_amount(event["cost_total"]) for event in matches]
            timestamps = [utc(datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))) for e in matches]
        except Exception:
            raise ValueError("帳單證據格式無效；保持待重核") from None
        if len({t.strftime("%Y-%m") for t in timestamps}) != 1:
            raise ValueError("跨月帳單調整需人工核對；未釋放保留額")
        self.budget.reconcile(rid, sum(amounts, Decimal("0")), BILLING_URL, timestamps[0])
        if row["state"] in {"SUBMITTED", "IN_QUEUE", "IN_PROGRESS", "COMPLETED", "FAILED", "CANCEL_REQUESTED"}:
            self.budget.set_state(rid, row["state"])
        return True
