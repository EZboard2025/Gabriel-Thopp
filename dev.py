"""Servidor local de dev — roda o Flask app (api/index.py) que já lida com static files.
Uso: python3 dev.py (lê .env.local automaticamente)"""

import os
import sys
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

from index import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Servidor local em http://localhost:{port}")
    print("Ctrl+C pra parar.")
    app.run(host="127.0.0.1", port=port, debug=False)
