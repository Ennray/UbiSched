"""本地 HTTP JSON 接口。部署到其他主机前应由认证网关保护。"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json

MAX_BODY = 1_000_000


class RuntimeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, coordinator):
        self.coordinator = coordinator
        super().__init__(address, RuntimeHandler)


class RuntimeHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        if self.path != "/v2/rpc":
            self.send_error(404); return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                raise ValueError("invalid request size")
            request = json.loads(self.rfile.read(length))
            result = self.server.coordinator.handle(request)
        except (ValueError, UnicodeError, RecursionError) as exc:
            result = {"status": "error", "error": str(exc)[:200]}
        raw = json.dumps(result, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(200 if result["status"] == "ok" else 400)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers(); self.wfile.write(raw)

    def setup(self):
        super().setup()
        self.connection.settimeout(10)
