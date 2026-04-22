"""Servidor local de dev — simula o Vercel.
Serve index.html e roteia /api/* pras funções em api/.
Uso: python3 dev.py (lê .env.local automaticamente)"""

import importlib
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "api"))

env_file = ROOT / ".env.local"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

API_ROUTES = {"/api/ranking": "ranking", "/api/state": "state"}


class DevHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        module_name = API_ROUTES.get(path)
        if module_name:
            try:
                mod = importlib.import_module(module_name)
                importlib.reload(mod)
                h = mod.handler.__new__(mod.handler)
                for attr in ("wfile", "rfile", "path", "command", "headers"):
                    setattr(h, attr, getattr(self, attr))
                for attr in ("send_response", "send_header", "end_headers"):
                    setattr(h, attr, getattr(self, attr))
                mod.handler.do_GET(h)
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(f'{{"error": "{e}"}}'.encode())
            return
        super().do_GET()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Servidor local em http://localhost:{port}")
    print("Ctrl+C pra parar.")
    HTTPServer(("127.0.0.1", port), DevHandler).serve_forever()
