"""Comparación sin / con contexto de página (título + sección) en el análisis.

Envía a /analyze (el sistema real: `python app.py` debe estar corriendo) el
contenido exacto que el navegador manda por cada elemento analizable de las tres
páginas (evaluation/assets/payloads_paginas.json: texto, gráficas ya
rasterizadas, pie, nivel diseñado, textos SVG, título y sección). Para cada
elemento se piden las dos variantes seguidas, alternando el orden, para que la
variación del modelo afecte igual a ambas.

Métricas por variante (todas automáticas):
  - ayudas: elementos con ayuda que se mostraría
  - bloqueadas: término fuera del texto (concept_in_text)
  - repetidas: ayudas de una página cuyo término ya se definió en otra ayuda
    de la misma página
  - termino_del_titulo: ayudas cuyo término está en el título de la página
  - latencia_s: tiempo de análisis promedio (solo llamadas al modelo)
La corrección de cada definición NO se mide aquí: se revisa a mano con el
detalle guardado (evaluation/results/contexto_<fecha>.json).

Variantes (--variantes):
  sin                   sin contexto (como antes del 2026-10-06)
  con                   título + sección, en todo (texto, tablas, imágenes)
  seccion_texto         solo la sección, solo en texto y tablas
  titulo_seccion_texto  título + sección, solo en texto y tablas
Con --solo-texto se omiten las imágenes (en las variantes *_texto son iguales a "sin").

Uso: python evaluation/ab_contexto.py --reps 2
     python evaluation/ab_contexto.py --reps 2 --solo-texto --variantes sin seccion_texto titulo_seccion_texto
"""
import argparse
import csv
import datetime
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PAYLOADS = ROOT / "evaluation" / "assets" / "payloads_paginas.json"
RESULTS = ROOT / "evaluation" / "results"
URL = "http://127.0.0.1:5000/analyze"


def words(value):
    value = unicodedata.normalize("NFKD", (value or "").lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.findall(r"[a-z0-9]+", value)


def in_text(concept, text):
    joined = " " + " ".join(words(text))
    content = [w for w in words(concept) if len(w) >= 4]
    return bool(content) and all(f" {w[:max(4, len(w) - 2)]}" in joined for w in content)


VARIANTS = {
    "sin": {"title": False, "section": False, "only_text": False},
    "con": {"title": True, "section": True, "only_text": False},
    "seccion_texto": {"title": False, "section": True, "only_text": True},
    "titulo_seccion_texto": {"title": True, "section": True, "only_text": True},
}


def analyze(item, variant):
    spec = VARIANTS[variant]
    body = {k: item[k] for k in ("content", "content_type", "context", "design_level", "chart_text")}
    body["dwell_time"] = 1
    applies = not spec["only_text"] or item["content_type"] in ("text", "table")
    if applies and spec["title"]:
        body["page_title"] = item["page_title"]
    if applies and spec["section"]:
        body["section"] = item["section"]
    return requests.post(URL, json=body, timeout=120).json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--variantes", nargs="+", default=["sin", "con"], choices=list(VARIANTS))
    ap.add_argument("--solo-texto", action="store_true")
    args = ap.parse_args()
    items = json.loads(PAYLOADS.read_text(encoding="utf-8"))["items"]
    if args.solo_texto:
        items = [i for i in items if i["content_type"] in ("text", "table")]
    variants = args.variantes

    runs = []
    for rep in range(args.reps):
        for i, item in enumerate(items):
            # Orden rotado entre elementos y corridas: la variación del modelo
            # afecta por igual a todas las variantes.
            shift = (i + rep) % len(variants)
            for variant in variants[shift:] + variants[:shift]:
                res = analyze(item, variant)
                runs.append({"rep": rep, "variante": variant, "pagina": item["page"], "el": item["el"],
                             "seccion": item["section"], "tipo": item["content_type"],
                             "texto": (item["context"] or item["content"])[:160] if item["content_type"] != "image_base64" else item["context"],
                             "nivel": res.get("complexity"), "accion": res.get("action"),
                             "bloqueada": res.get("help_blocked"), "concepto": res.get("concept"),
                             "explicacion": res.get("explanation"), "s": res.get("processing_time") or 0,
                             "titulo": item["page_title"]})
            print(f"  rep {rep + 1} · {i + 1}/{len(items)}", end="\r")
    print()

    now = datetime.datetime.now()
    rows = []
    for variant in variants:
        for rep in range(args.reps):
            sel = [r for r in runs if r["variante"] == variant and r["rep"] == rep]
            helps = [r for r in sel if r["accion"] == "tooltip"]
            seen, repeated = defaultdict(set), 0
            for r in helps:
                key = " ".join(words(r["concepto"]))
                repeated += key in seen[r["pagina"]]
                seen[r["pagina"]].add(key)
            model_calls = [r["s"] for r in sel if r["s"] > 0]
            metrics = {
                "ayudas": len(helps),
                "bloqueadas": sum(bool(r["bloqueada"]) for r in sel),
                "repetidas": repeated,
                "termino_del_titulo": sum(in_text(r["concepto"], r["titulo"]) for r in helps),
                "latencia_s": round(sum(model_calls) / len(model_calls), 2) if model_calls else 0,
            }
            print(f"  [{variant}, corrida {rep + 1}] " + " | ".join(f"{k} {v}" for k, v in metrics.items()))
            for k, v in metrics.items():
                rows.append({"fecha": now.strftime("%Y-%m-%d %H:%M"), "suite": "contexto_pagina",
                             "variante": variant if variant not in ("sin", "con") else f"{variant}_contexto",
                             "metrica": f"{k}_corrida{rep + 1}", "valor": v, "n": len(sel),
                             "notas": "solo texto y tablas" if args.solo_texto else ""})

    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%d_%H%M%S")
    (RESULTS / f"contexto_{stamp}.json").write_text(
        json.dumps({"fecha": now.isoformat(), "reps": args.reps, "filas": rows, "detalle": runs},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    with (RESULTS / "history.csv").open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=["fecha", "suite", "variante", "metrica", "valor", "n", "notas"]).writerows(rows)
    print(f"Guardado: evaluation/results/contexto_{stamp}.json y history.csv ({len(rows)} filas)")


if __name__ == "__main__":
    main()
