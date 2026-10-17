"""新版接口客户端。网络重试复用同一个 request_id。"""
import json
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class RuntimeClient:
    def __init__(self, url="http://127.0.0.1:18767/v2/rpc", *, timeout=5, retries=2):
        self.url, self.timeout, self.retries = url, timeout, retries

    def call(self, operation, *, request_id=None, **fields):
        payload = {"operation": operation, "request_id": request_id or uuid.uuid4().hex, **fields}
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        last = None
        for _ in range(self.retries + 1):
            try:
                req = Request(self.url, data=raw, headers={"Content-Type": "application/json"})
                try:
                    with urlopen(req, timeout=self.timeout) as response:
                        result = json.load(response)
                except HTTPError as exc:
                    result = json.load(exc)
                if result.get("status") != "ok":
                    raise ValueError(result.get("error", "runtime request failed"))
                return result
            except (URLError, TimeoutError, ConnectionError) as exc:
                last = exc
        raise ConnectionError(f"runtime unavailable; request_id={payload['request_id']}: {last}")
