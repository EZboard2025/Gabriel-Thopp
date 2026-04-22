"""Storage compartilhado.
- Vercel: Upstash Redis via REST (KV_REST_API_URL + KV_REST_API_TOKEN).
- Dev local: arquivos em /tmp/thopp-ranking-state/ (fallback quando envs ausentes)."""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

KV_URL = os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
KV_TOKEN = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN")
LOCAL_DIR = Path("/tmp/thopp-ranking-state")


def _kv(path: str, method: str = "GET", body: Optional[bytes] = None):
    req = urllib.request.Request(
        f"{KV_URL}{path}",
        headers={"Authorization": f"Bearer {KV_TOKEN}"},
        data=body,
        method=method,
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _local_path(key: str) -> Path:
    return LOCAL_DIR / f"{key}.json"


def get(key: str):
    if KV_URL and KV_TOKEN:
        try:
            result = _kv(f"/get/{urllib.parse.quote(key)}")
            raw = result.get("result")
            if raw is None:
                return None
            try:
                return json.loads(raw)
            except (ValueError, TypeError):
                return raw
        except Exception as e:
            print(f"KV get falhou: {e}")
            return None
    p = _local_path(key)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def set(key: str, value, ttl_seconds: Optional[int] = None):
    data = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    if KV_URL and KV_TOKEN:
        try:
            path = f"/set/{urllib.parse.quote(key)}"
            if ttl_seconds:
                path += f"?EX={ttl_seconds}"
            _kv(path, method="POST", body=data.encode("utf-8"))
            return
        except Exception as e:
            print(f"KV set falhou: {e}")
            return
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    _local_path(key).write_text(data)


def incr(key: str, ttl_seconds: Optional[int] = None) -> int:
    if KV_URL and KV_TOKEN:
        try:
            result = _kv(f"/incr/{urllib.parse.quote(key)}", method="POST")
            value = int(result.get("result") or 0)
            if ttl_seconds and value == 1:
                _kv(f"/expire/{urllib.parse.quote(key)}/{ttl_seconds}", method="POST")
            return value
        except Exception as e:
            print(f"KV incr falhou: {e}")
            return 0
    current = get(key)
    current = int(current) if isinstance(current, (int, str)) and str(current).lstrip("-").isdigit() else 0
    current += 1
    set(key, current)
    return current


def now_keys():
    t = time.gmtime()
    return (
        f"count-d-{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}",
        f"count-m-{t.tm_year:04d}-{t.tm_mon:02d}",
    )
