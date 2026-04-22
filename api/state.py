from http.server import BaseHTTPRequestHandler
import json

import _store
from ranking import read_counters, build_counter


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        day_used, month_used = read_counters()
        last = _store.get("last-ranking")
        payload = {
            "counter": build_counter(day_used, month_used),
            "last_ranking": last,
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
