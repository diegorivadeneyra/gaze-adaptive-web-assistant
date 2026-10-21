"""Mide el segundo nivel de ayuda (POST /expand) sobre los párrafos reales.

Para cada párrafo de texto Medium/High de las tres páginas
(evaluation/assets/payloads_paginas.json): pide la primera ayuda (/analyze,
para saber qué término ya se definió) y luego la ampliada (/expand), como hace
el navegador. Recorre cada página en orden y envía los términos ya
explicados en ella (defined_terms), como el navegador desde el 2026-10-11.
Omite las notas al pie (en el navegador no reciben ayuda). Requiere
`python app.py` corriendo y la GPU libre.

Métricas: respuestas válidas, términos válidos por respuesta, términos
descartados por no estar en el texto, repetición del término del primer
nivel, palabras de la explicación y latencia. El detalle (textos) queda en
evaluation/results/ayuda_ampliada_<fecha>.json para revisarlo a mano.

Uso: python evaluation/medir_ayuda_ampliada.py --reps 2
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

BASE = "http://127.0.0.1:5000"
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

    runs = []
    for rep in range(args.reps):
        defined = {}                                    # página -> términos ya explicados
        for i, item in enumerate(paragraphs):
            page_terms = defined.setdefault(item["page"], [])
            first = requests.post(f"{BASE}/analyze", json={"content": item["content"], "content_type": "text",
                                                            "dwell_time": 1, "section": item["section"],
                                                            "defined_terms": page_terms}, timeout=120).json()
            concept = first.get("concept", "") if first.get("action") == "tooltip" else ""
            if concept:
                page_terms.append(concept)
            reply = requests.post(f"{BASE}/expand", json={"content": item["content"], "section": item["section"],
                                                          "already_defined": concept,
                                                          "defined_terms": page_terms}, timeout=120)
            try:
                second = reply.json()
            except ValueError:
                second = {"error": f"HTTP {reply.status_code} sin JSON"}
            terms = [t["term"] for t in second.get("terms", [])]
            page_terms.extend(t for t in terms if t not in page_terms)
            runs.append({"rep": rep, "pagina": item["page"], "el": item["el"], "texto": item["content"][:200],
                         "nivel1_concepto": concept, "terminos": terms,
                         "descartados": second.get("discarded_terms", []), "simple": second.get("simple", ""),
                         "explicacion": second.get("explanation", ""), "error": second.get("error"),
                         "s": second.get("processing_time"), "s_nivel1": first.get("processing_time")})
            print(f"  rep {rep + 1} · {i + 1}/{len(paragraphs)}", end="\r")
    print()

    ok = [r for r in runs if not r["error"] and r["explicacion"]]
    n = len(runs)
    metrics = {
        "respuestas": n,
        "validas": len(ok),
        "con_2_o_mas_terminos": sum(len(r["terminos"]) >= 2 for r in ok),
        "terminos_prom": round(sum(len(r["terminos"]) for r in ok) / max(len(ok), 1), 2),
        "terminos_descartados": sum(len(r["descartados"]) for r in runs),
        "repite_termino_nivel1": sum(any(t.lower() == r["nivel1_concepto"].lower() for t in r["terminos"]) for r in ok),
        "con_frase_simple": sum(bool(r["simple"]) for r in ok),
        "palabras_prom": round(sum(len(r["explicacion"].split()) for r in ok) / max(len(ok), 1), 1),
        "latencia_s_prom": round(sum(r["s"] or 0 for r in ok) / max(len(ok), 1), 2),
        "latencia_s_max": max((r["s"] or 0 for r in ok), default=0),
        # Si /expand y /analyze usan distinto num_ctx, Ollama recarga phi3 en cada cambio.
        "latencia_nivel1_s_prom": round(sum(r["s_nivel1"] or 0 for r in runs) / max(n, 1), 2),
    }
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    out = ROOT / "evaluation/results" / f"ayuda_ampliada_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps({"metricas": metrics, "detalle": runs}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Guardado: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
