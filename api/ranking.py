from http.server import BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor
import json
import os
import statistics
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import urlopen

import _store

SEARCH_QUERIES = [
    # Queries genéricas
    "empresas de elevadores Belo Horizonte",
    "manutenção de elevadores Belo Horizonte",
    "instalação de elevadores Belo Horizonte",
    "modernização de elevadores Belo Horizonte",
    "assistência técnica elevadores Belo Horizonte",
    "conserto de elevadores Belo Horizonte",
    "reparo de elevadores BH",
    "fabricante de elevadores MG",
    # Queries de marca (capturam multinacionais e legacy que não vêm nas genéricas)
    "Atlas Schindler Belo Horizonte",
    "Otis Elevadores Belo Horizonte",
    "TKE Thyssenkrupp Belo Horizonte",
    "KONE Elevadores Belo Horizonte",
    "Orona Elevadores Belo Horizonte",
    "Villarta Elevadores Belo Horizonte",
    "Milenio Elevadores Belo Horizonte",
    "elevadores condomínio Belo Horizonte",
]
TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"

LIMIT_DAY = 30
LIMIT_MONTH = 900
DAY_TTL = 60 * 60 * 36         # 36h
MONTH_TTL = 60 * 60 * 24 * 40  # 40d


def text_search(query: str, api_key: str) -> list:
    """Text Search uma página (até 20 resultados). Sem pagination pra caber em timeout serverless."""
    params = {"query": query, "key": api_key, "region": "br", "language": "pt-BR"}
    try:
        with urlopen(f"{TEXT_SEARCH_URL}?{urlencode(params)}", timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"query falhou '{query}': {e}")
        return []
    if data.get("status") not in ("OK", "ZERO_RESULTS"):
        print(f"query '{query}' retornou {data.get('status')}")
        return []
    return data.get("results", [])


REGIAO_BH = (
    "Belo Horizonte", "Contagem", "Nova Lima", "Betim",
    "Ribeirão das Neves", "Ribeirao das Neves", "Santa Luzia",
    "Ibirité", "Ibirite", "Sabará", "Sabara", "Vespasiano", "Lagoa Santa",
)


def na_regiao_bh(endereco: str) -> bool:
    if not endereco:
        return False
    return any(cidade in endereco for cidade in REGIAO_BH)


def fetch_all_companies(api_key: str) -> list:
    """Dispara todas as queries em paralelo e deduplica por place_id."""
    by_id: dict = {}
    with ThreadPoolExecutor(max_workers=len(SEARCH_QUERIES)) as pool:
        results = list(pool.map(lambda q: text_search(q, api_key), SEARCH_QUERIES))
    for places in results:
        for place in places:
            pid = place.get("place_id")
            if not pid or not na_regiao_bh(place.get("formatted_address") or ""):
                continue
            prev = by_id.get(pid)
            if prev is None or (place.get("user_ratings_total") or 0) > (prev.get("user_ratings_total") or 0):
                by_id[pid] = place
    return list(by_id.values())


def compute_ranking(companies: list) -> dict:
    """Ranking por Média Bayesiana:
        NP = (v / (v + m)) * R + (m / (v + m)) * C
       onde C = média geral ponderada pelo volume; m = mediana de avaliações."""
    rated = [c for c in companies if c.get("rating") is not None and c.get("user_ratings_total")]
    if not rated:
        return {"ranking": [], "C": 0.0, "m": 0.0, "total_avaliacoes": 0}

    total_reviews = sum(c["user_ratings_total"] for c in rated)
    C = sum(c["rating"] * c["user_ratings_total"] for c in rated) / total_reviews
    m = statistics.median([c["user_ratings_total"] for c in rated])

    out = []
    for c in rated:
        v = c["user_ratings_total"]
        R = c["rating"]
        score = (v / (v + m)) * R + (m / (v + m)) * C
        out.append({
            "place_id": c["place_id"],
            "nome": c.get("name"),
            "endereco": c.get("formatted_address"),
            "nota": round(R, 2),
            "total_avaliacoes": v,
            "score_ponderado": round(score, 3),
            "maps_url": f"https://www.google.com/maps/place/?q=place_id:{c['place_id']}",
        })
    out.sort(key=lambda x: x["score_ponderado"], reverse=True)
    for i, row in enumerate(out, start=1):
        row["posicao"] = i
    return {"ranking": out, "C": round(C, 2), "m": m, "total_avaliacoes": total_reviews}


def read_counters() -> tuple[int, int]:
    day_key, month_key = _store.now_keys()
    d = _store.get(day_key)
    m = _store.get(month_key)
    return (int(d) if d else 0), (int(m) if m else 0)


def build_counter(day_used: int, month_used: int) -> dict:
    return {
        "day_used": day_used,
        "day_limit": LIMIT_DAY,
        "day_remaining": max(0, LIMIT_DAY - day_used),
        "month_used": month_used,
        "month_limit": LIMIT_MONTH,
        "month_remaining": max(0, LIMIT_MONTH - month_used),
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
        if not api_key:
            self._json(500, {"error": "GOOGLE_MAPS_API_KEY não configurado"})
            return

        day_used, month_used = read_counters()

        if day_used >= LIMIT_DAY:
            self._json(429, {
                "error": f"Limite diário de {LIMIT_DAY} atualizações atingido. Tenta amanhã.",
                "counter": build_counter(day_used, month_used),
            })
            return
        if month_used >= LIMIT_MONTH:
            self._json(429, {
                "error": f"Limite mensal de {LIMIT_MONTH} atualizações atingido. Reseta no dia 1.",
                "counter": build_counter(day_used, month_used),
            })
            return

        try:
            companies = fetch_all_companies(api_key)
            result = compute_ranking(companies)
        except Exception as e:
            self._json(500, {"error": str(e)})
            return

        day_key, month_key = _store.now_keys()
        new_day = _store.incr(day_key, ttl_seconds=DAY_TTL)
        new_month = _store.incr(month_key, ttl_seconds=MONTH_TTL)

        payload = {
            "atualizado_em": datetime.now(timezone.utc).isoformat(),
            "total_empresas": len(result["ranking"]),
            "total_avaliacoes": result["total_avaliacoes"],
            "ranking": result["ranking"],
            "parametros": {
                "fonte": "Google Places API (Text Search)",
                "formula": "NP = (v/(v+m))·R + (m/(v+m))·C",
                "C_media_geral": result["C"],
                "m_mediana_avaliacoes": result["m"],
                "queries": SEARCH_QUERIES,
            },
        }
        _store.set("last-ranking", payload)

        self._json(200, {**payload, "counter": build_counter(new_day, new_month)})

    def _json(self, status: int, body: dict) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))
