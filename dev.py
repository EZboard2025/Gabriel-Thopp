"""Servidor local de dev — roda o Flask app (api/index.py) + serve arquivos estáticos.
Em produção, a Vercel serve os estáticos direto; aqui a gente precisa de uma rota extra."""

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

from flask import send_from_directory
from index import app


@app.route("/")
def _dev_home():
    return send_from_directory(str(ROOT), "index.html")


@app.route("/<path:filename>")
def _dev_static(filename):
    if filename.startswith("api/"):
        return "", 404
    return send_from_directory(str(ROOT), filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Servidor local em http://localhost:{port}")
    print("Ctrl+C pra parar.")
    app.run(host="127.0.0.1", port=port, debug=False)
