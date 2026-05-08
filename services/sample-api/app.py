from __future__ import annotations

import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


REQUESTS: dict[str, int] = {}
LATENCY_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
LATENCY_COUNTS = {bucket: 0 for bucket in LATENCY_BUCKETS}
LATENCY_INF = 0
LATENCY_SUM = 0.0
LATENCY_TOTAL = 0


def _inc_request(path: str) -> None:
    REQUESTS[path] = REQUESTS.get(path, 0) + 1


def _observe_latency(seconds: float) -> None:
    global LATENCY_INF, LATENCY_SUM, LATENCY_TOTAL
    LATENCY_SUM += seconds
    LATENCY_TOTAL += 1
    matched = False
    for bucket in LATENCY_BUCKETS:
        if seconds <= bucket:
            LATENCY_COUNTS[bucket] += 1
            matched = True
    if not matched:
        LATENCY_INF += 1


def _metrics() -> bytes:
    lines = [
        "# HELP http_requests_total Total HTTP requests handled by sample-api.",
        "# TYPE http_requests_total counter",
    ]
    total = 0
    for path, count in sorted(REQUESTS.items()):
        total += count
        lines.append(f'http_requests_total{{path="{path}"}} {count}')
    lines.append(f"http_requests_total {total}")
    lines.extend(
        [
            "# HELP http_request_duration_seconds HTTP request duration.",
            "# TYPE http_request_duration_seconds histogram",
        ]
    )
    cumulative = 0
    for bucket in LATENCY_BUCKETS:
        cumulative += LATENCY_COUNTS[bucket]
        lines.append(f'http_request_duration_seconds_bucket{{le="{bucket}"}} {cumulative}')
    lines.append(f'http_request_duration_seconds_bucket{{le="+Inf"}} {cumulative + LATENCY_INF}')
    lines.append(f"http_request_duration_seconds_sum {LATENCY_SUM:.6f}")
    lines.append(f"http_request_duration_seconds_count {LATENCY_TOTAL}")
    lines.append("")
    return "\n".join(lines).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "thesis-sample-api/1.0"

    def do_GET(self) -> None:
        start = time.perf_counter()
        if self.path == "/metrics":
            body = _metrics()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        path = self.path.split("?", 1)[0]
        _inc_request(path)
        work_ms = 2 + random.randint(0, 12)
        if path == "/b":
            work_ms += 8
        time.sleep(work_ms / 1000)
        body = f"ok path={path} work_ms={work_ms}\n".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        _observe_latency(time.perf_counter() - start)

    def log_message(self, fmt: str, *args: object) -> None:
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    server.serve_forever()
