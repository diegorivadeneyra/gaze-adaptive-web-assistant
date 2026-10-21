"""Comparación de cómo se elige el término que define la primera ayuda.

Variantes (text_analyzer.TERM_SELECTION):
  modelo      el modelo elige UN término y lo define (versión anterior)
  candidatos  propone hasta 3 términos con definición; el código descarta
              símbolos/fórmulas, términos fuera del texto y términos ya
              explicados en la página, y se queda con el primero del modelo
  silabas     igual, pero elige el término con la palabra de más sílabas

Recorre los párrafos de texto Medium/High de cada página EN ORDEN (como quien
lee de arriba abajo) y le pasa a cada variante los términos que ella misma ya
explicó en esa página (defined_terms), como hace el navegador. Las variantes
se piden seguidas sobre cada párrafo, rotando el orden. Requiere
`python app.py` corriendo y la GPU libre.

Métricas automáticas: ayudas, bloqueadas, términos repetidos en la página,
términos que son símbolos, sílabas del término, latencia. El juicio
(¿término relevante?, ¿definición correcta?) se hace a mano con el detalle
guardado en evaluation/results/terminos_<fecha>.json.

Uso: python evaluation/ab_terminos.py --reps 2
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from analyzers.readability import compute_readability  # noqa: E402
from analyzers.text_analyzer import is_symbol_term, same_term, term_syllables  # noqa: E402

BASE = "http://127.0.0.1:5000"
VARIANTS = ("modelo", "candidatos", "silabas")
# Notas al pie (.footnote): en el navegador nunca reciben ayuda (NO_HELP_SELECTOR).
FOOTNOTES = {
    ("intermedio", "main[0]>div[0]>div[0]>article[1]>p[0]"),
    ("intermedio", "main[0]>div[0]>div[1]>p[0]"),
    ("avanzado", "main[0]>div[1]>div[0]>p[0]"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=2)
    args = ap.parse_args()
    items = json.loads((ROOT / "evaluation/assets/payloads_paginas.json").read_text(encoding="utf-8"))["items"]
    paragraphs = [i for i in items if i["content_type"] == "text" and (i["page"], i["el"]) not in FOOTNOTES
                  and (compute_readability(i["content"]) or {}).get("level") in ("Medium", "High")]

    runs, k = [], 0
    for rep in range(args.reps):
        defined = {v: {} for v in VARIANTS}          # variante -> página -> [términos]
        for i, item in enumerate(paragraphs):
            order = VARIANTS[k % 3:] + VARIANTS[:k % 3]
            k += 1
            for variant in order:
                page_terms = defined[variant].setdefault(item["page"], [])
                r = requests.post(f"{BASE}/analyze", json={
                    "content": item["content"], "content_type": "text", "dwell_time": 1,
                    "section": item["section"], "defined_terms": page_terms, "term_selection": variant,
                }, timeout=120).json()
                shown = r.get("action") == "tooltip" and bool(r.get("explanation"))
                concept = r.get("concept", "") if shown else ""
                runs.append({
                    "rep": rep, "variante": variant, "pagina": item["page"], "el": item["el"],
                    "texto": item["content"][:160], "nivel": r.get("complexity"), "ayuda": shown,
                    "termino": concept, "explicacion": r.get("explanation", "") if shown else "",
                    "bloqueo": r.get("help_blocked"), "candidatos": r.get("term_candidates"),
                    "descartados": r.get("term_discarded"),
                    "repetido": shown and any(same_term(concept, t) for t in page_terms),
                    "simbolo": shown and is_symbol_term(concept),
                    "silabas": term_syllables(concept) if shown else None,
                    "s": r.get("processing_time"),
                })
                if shown:
                    page_terms.append(concept)
            print(f"  rep {rep + 1} · {i + 1}/{len(paragraphs)}", end="\r")
    print()

    metrics = {}
    for v in VARIANTS:
        rs = [r for r in runs if r["variante"] == v]
        shown = [r for r in rs if r["ayuda"]]
        metrics[v] = {
            "parrafos": len(rs),
            "ayudas": len(shown),
            "bloqueadas": sum(bool(r["bloqueo"]) for r in rs),
            "repetidas_en_la_pagina": sum(r["repetido"] for r in shown),
            "simbolos": sum(r["simbolo"] for r in shown),
            "silabas_prom": round(sum(r["silabas"] for r in shown) / max(len(shown), 1), 2),
            "latencia_s_prom": round(sum(r["s"] or 0 for r in rs) / max(len(rs), 1), 2),
        }
        print(f"  {v}: {metrics[v]}")
    out = ROOT / "evaluation/results" / f"terminos_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps({"metricas": metrics, "detalle": runs}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Guardado: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
