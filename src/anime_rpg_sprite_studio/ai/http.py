"""Bounded HTTPS only. No redirects, retries, environment proxies or raw errors."""
from decimal import Decimal
import json
import ssl
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPSHandler, HTTPRedirectHandler
from urllib.error import HTTPError


def validate_url(url, authenticated):
    try:
        p = urlsplit(url)
        host = p.hostname or ""
        valid = host in {"api.fal.ai", "queue.fal.run"} if authenticated else host == "fal.media" or host.endswith(".fal.media")
        if p.scheme != "https" or p.username or p.password or p.fragment or p.port not in (None, 443) or not valid:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("拒絕非指定 HTTPS 主機") from None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SafeHttp:
    def request(self, method, url, *, key=None, payload=None, max_bytes=2 * 1024 * 1024):
        validate_url(url, authenticated=key is not None)
        headers = {"Accept": "application/json"}
        if key is not None:
            headers["Authorization"] = "Key " + key
        data = None
        if payload is not None:
            data = json.dumps(payload, allow_nan=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))
            with opener.open(Request(url, data=data, headers=headers, method=method), timeout=25) as response:
                body = response.read(max_bytes + 1)
                if len(body) > max_bytes:
                    raise ValueError("回應超出大小限制")
                return body
        except HTTPError as exc:
            raise ValueError(f"fal.ai HTTP {exc.code}；未自動重試") from None
        except Exception:
            raise ValueError("HTTPS 請求失敗或逾時；未自動重試") from None

    def json(self, method, url, *, key, payload=None):
        body = self.request(method, url, key=key, payload=payload)
        try:
            result = json.loads(body, parse_float=Decimal)
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except Exception:
            raise ValueError("fal.ai JSON 回應格式無效") from None
