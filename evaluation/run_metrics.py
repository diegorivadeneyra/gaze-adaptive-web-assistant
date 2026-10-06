"""Mediciones reproducibles de las mejoras del sistema (para el README y para
graficar antes/después).

Cada suite compara una variante "antes" (una versión anterior del sistema,
reconstruida aquí como línea base) contra la actual, sobre el MISMO contenido
(el texto real de las tres páginas). Resultados:
  - evaluation/results/metrics_<fecha>.json : detalle de cada corrida
  - evaluation/results/history.csv          : filas (fecha, suite, variante,
                                              métrica, valor, n) para graficar

Uso (con Ollama corriendo; desde la raíz del proyecto):
    python evaluation/run_metrics.py --suite all
    python evaluation/run_metrics.py --suite text --reps 3
Suites: language, readability (sin modelo), text (phi3), vision (qwen2.5vl).
"""
import argparse
import base64
import csv
import datetime
import io
import json
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from analyzers import image_analyzer as IA          # noqa: E402
from analyzers import readability as R              # noqa: E402
from analyzers import text_analyzer as TA           # noqa: E402
from analyzers.llm_utils import (                   # noqa: E402
    OLLAMA_BASE_URL, OLLAMA_KEEP_ALIVE, TEXT_MODEL, VISION_MODEL,
    extract_json, extract_partial_analysis, normalize_analysis,
)

FRONTEND = ROOT / "frontend"
RESULTS = ROOT / "evaluation" / "results"
ASSETS = ROOT / "evaluation" / "assets"
NOW = datetime.datetime.now()
ROWS = []


def add(suite, variant, metric, value, n, notes=""):
    ROWS.append({"fecha": NOW.strftime("%Y-%m-%d %H:%M"), "suite": suite, "variante": variant,
                 "metrica": metric, "valor": round(value, 4) if isinstance(value, float) else value,
                 "n": n, "notas": notes})


# ─── Contenido real de las páginas ─────────────────────────────────────────
class BlockParser(HTMLParser):
    """Extrae <p>/<li> y las tablas (título + celdas separadas por tabulador)."""

    def __init__(self):
        super().__init__()
        self.stack, self.buf = [], []
        self.blocks, self.tables = [], []
        self._table = None

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "li"):
            self.stack.append(tag); self.buf = []
        elif tag == "table":
            self._table = {"caption": "", "rows": [], "row": None, "cell": None, "in_caption": False}
        elif self._table is not None:
            if tag == "caption": self._table["in_caption"] = True
            elif tag == "tr": self._table["row"] = []
            elif tag in ("td", "th"): self._table["cell"] = []

    def handle_endtag(self, tag):
        if self.stack and tag == self.stack[-1]:
            text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
            self.blocks.append(text); self.stack.pop()
        t = self._table
        if t is not None:
            if tag == "caption": t["in_caption"] = False
            elif tag in ("td", "th") and t["cell"] is not None:
                t["row"].append("".join(t["cell"]).strip()); t["cell"] = None
            elif tag == "tr" and t["row"] is not None:
                t["rows"].append("\t".join(t["row"])); t["row"] = None
            elif tag == "table":
                self.tables.append(t); self._table = None

    def handle_data(self, data):
        if self.stack: self.buf.append(data)
        t = self._table
        if t is not None:
            if t["in_caption"]: t["caption"] += data
            elif t["cell"] is not None: t["cell"].append(data)


def load_page(name):
    p = BlockParser()
    p.feed((FRONTEND / f"{name}.html").read_text(encoding="utf-8"))
    return p


def body_paragraphs():
    out = []
    for page in ("intermedio", "avanzado"):
        out += [(page, t) for t in load_page(page).blocks if len(t) >= 200]
    return out


def table_texts():
    """Tablas de las páginas: con título (como están ahora) y sin título."""
    out = []
    for page in ("intermedio", "avanzado"):
        for t in load_page(page).tables:
            cap = re.sub(r"\s+", " ", t["caption"]).strip()
            body = "\n".join(t["rows"])
            out.append((f"tabla {page} (con título)", f"{cap}\n{body}"))
            out.append((f"tabla {page} (sin título)", body))
    return out


def trigrams(s):
    w = re.findall(r"\w+", s.lower())
    return {tuple(w[i:i + 3]) for i in range(len(w) - 2)}


# ─── Suite 1: detección de idioma (determinista) ──────────────────────────
def detect_language_v0(text):
    """Versión anterior: caía a inglés cuando no encontraba marcadores de español."""
    markers = (" el ", " la ", " los ", " las ", " que ", " de ", " y ", " una ", " para ", " con ",
               "ción", "ñ", "¿", "¡", " energía", " sistema", " ecuación", " texto", " usuario")
    lowered = text.lower()
    return "Spanish" if sum(m in f" {lowered} " for m in markers) >= 1 else "English"


def suite_language():
    cases = [(t, "Spanish", "tabla") for _, t in table_texts()]
    cases += [(t, "Spanish", "párrafo") for _, t in body_paragraphs()]
    cases += [("Equilibrium climate sensitivity is estimated through a multivariate regression model applied to "
               "global surface temperature and net radiative forcing time series, and the CO2 coefficient was "
               "statistically significant.", "English", "inglés"),
              ("Greenhouse gases trap heat in the atmosphere, and the planet is warming as a result of the "
               "burning of fossil fuels.", "English", "inglés")]
    for variant, fn in (("v0_cae_a_inglés", detect_language_v0), ("actual_cae_a_español", TA.detect_language)):
        ok = [fn(t) == truth for t, truth, _ in cases]
        tabs = [fn(t) == truth for t, truth, kind in cases if kind == "tabla"]
        add("language", variant, "aciertos_total", sum(ok) / len(ok), len(ok))
        add("language", variant, "aciertos_tablas", sum(tabs) / len(tabs), len(tabs))
        print(f"  idioma [{variant}] total {sum(ok)}/{len(ok)} | tablas {sum(tabs)}/{len(tabs)}")


# ─── Suite 2: legibilidad (determinista) ───────────────────────────────────
def suite_readability():
    for min_words in (15, 8):
        R.MIN_WORDS = min_words
        for page in ("facil", "intermedio", "avanzado"):
            blocks = [t for t in load_page(page).blocks if len(re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", t)) >= 8]
            res = [R.compute_readability(t) for t in blocks]
            measured = [r for r in res if r]
            lv = {k: sum(1 for r in measured if r["level"] == k) for k in ("Low", "Medium", "High")}
            variant = f"min_{min_words}_palabras"
            add("readability", f"{variant}/{page}", "bloques", len(blocks), len(blocks))
            add("readability", f"{variant}/{page}", "resueltos_por_legibilidad", len(measured) / len(blocks), len(blocks))
            add("readability", f"{variant}/{page}", "proporcion_Low_sin_llamar_al_modelo", lv["Low"] / len(blocks), len(blocks))
            print(f"  legibilidad [mín {min_words}] {page}: {len(measured)}/{len(blocks)} por fórmula | Low {lv['Low']} Medium {lv['Medium']} High {lv['High']}")
    R.MIN_WORDS = 8


# ─── Suite 3: explicaciones de texto con phi3 ──────────────────────────────
SCHEMA = TA.ANALYSIS_SCHEMA
V0_ANALOGIA = """Eres un asistente de lectura. El usuario necesita ayuda con este texto, que está en español.

Devuelve SOLO este objeto JSON, sin markdown ni texto adicional:
{{
"concept": "tema en 3 palabras",
"complexity": "Low, Medium o High",
"explanation": "máximo 30 palabras, en español, que ayuden a ENTENDER lo más difícil del texto. Nunca vacía."
}}

Reglas:
- Responde siempre en español, en el mismo idioma del texto. Nunca traduzcas ni respondas en otro idioma.
- High: términos técnicos o especializados.
- Medium: requiere conocimientos previos.
- Low: es simple y claro.
- explanation: PROHIBIDO repetir, resumir o reformular el texto. En vez de eso, explica el término o idea más difícil con palabras simples, como si se lo explicaras a alguien que nunca lo ha escuchado (usa una analogía o un ejemplo cotidiano).

Texto: {truncated}"""

V1_DOS_PARTES = """Eres un asistente de lectura. El usuario necesita ayuda con este texto, que está en español.

Devuelve SOLO este objeto JSON, sin markdown ni texto adicional:
{{
"concept": "tema en 3 palabras",
"complexity": "Low, Medium o High",
"explanation": "máximo 40 palabras, en español, en un solo párrafo (nunca una lista). Nunca vacía."
}}

Reglas:
- Responde siempre en español, en el mismo idioma del texto. Nunca traduzcas ni respondas en otro idioma.
- High: términos técnicos o especializados.
- Medium: requiere conocimientos previos.
- Low: es simple y claro.
- explanation: en dos partes seguidas. (1) Qué significa, en palabras simples, el término o idea más difícil. (2) Qué dice el texto con eso. Usa SOLO información del texto: no inventes datos, nombres, fechas ni ejemplos. NO uses analogías ni comparaciones. NO empieces con "Imagina". NO copies el texto tal cual.

Texto: {truncated}"""

TEXT_COMBOS = [  # (variante, plantilla de prompt o None = actual, format de Ollama)
    ("v0_analogia/sin_formato", V0_ANALOGIA, None),
    ("v1_dos_partes/format_json", V1_DOS_PARTES, "json"),
    ("v1_dos_partes/esquema", V1_DOS_PARTES, SCHEMA),
    ("actual_termino_sin_recap/format_json", None, "json"),
    ("actual_termino_sin_recap/esquema", None, SCHEMA),
]


def run_text(prompt_template, fmt, text):
    truncated = text.strip()[:TA.TEXT_CHAR_LIMIT]
    prompt = TA.build_prompt("Spanish", truncated) if prompt_template is None else prompt_template.format(truncated=truncated)
    payload = {"model": TEXT_MODEL, "prompt": prompt, "stream": False, "keep_alive": OLLAMA_KEEP_ALIVE,
               "options": {"temperature": 0.1, "top_p": 0.9, "num_predict": 200, "num_ctx": 1024}}
    if fmt is not None:
        payload["format"] = fmt
    t0 = time.time()
    raw = requests.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload, timeout=90).json()["response"]
    latency = time.time() - t0
    parsed = extract_json(raw)
    valid_json = parsed is not None
    parsed = parsed or extract_partial_analysis(raw)
    n = normalize_analysis(parsed, "") if parsed else {"concept": "", "explanation": ""}
    return raw, valid_json, n, latency


def suite_text(reps):
    items = [(f"párrafo {p}", t) for p, t in body_paragraphs()] + table_texts()
    detail = []
    for variant, template, fmt in TEXT_COMBOS:
        runs = []
        for label, text in items:
            for _ in range(reps):
                raw, valid, n, lat = run_text(template, fmt, text)
                exp, concept = n["explanation"], n["concept"]
                eg = trigrams(exp)
                first = exp.lower().lstrip("¡¿\"' ")
                runs.append({
                    "item": label, "vacia": not exp, "json_valido": valid,
                    "imagina": first.startswith("imagina") or bool(re.match(r"^[^:]{1,60}:\s*imagina", first)),
                    "copia": len(eg & trigrams(text)) / len(eg) if eg else 0.0,
                    "palabras": len(exp.split()), "latencia": lat,
                    "termino_en_texto": bool(concept) and concept.lower().strip() in text.lower(),
                    "explicacion": exp, "concepto": concept})
        detail.append({"variante": variant, "runs": runs})
        n = len(runs)
        non_empty = [r for r in runs if not r["vacia"]]
        k = len(non_empty) or 1
        add("text", variant, "explicaciones_vacias", sum(r["vacia"] for r in runs) / n, n)
        add("text", variant, "json_valido_sin_rescate", sum(r["json_valido"] for r in runs) / n, n)
        add("text", variant, "empiezan_con_imagina", sum(r["imagina"] for r in non_empty) / k, len(non_empty))
        add("text", variant, "copia_del_texto_trigramas_prom", sum(r["copia"] for r in non_empty) / k, len(non_empty))
        add("text", variant, "palabras_prom", sum(r["palabras"] for r in non_empty) / k, len(non_empty))
        add("text", variant, "palabras_max", max((r["palabras"] for r in non_empty), default=0), len(non_empty))
        add("text", variant, "termino_elegido_aparece_en_texto", sum(r["termino_en_texto"] for r in non_empty) / k, len(non_empty))
        add("text", variant, "latencia_s_prom", sum(r["latencia"] for r in runs) / n, n)
        print(f"  texto [{variant}] n={n} vacías {sum(r['vacia'] for r in runs)} | 'Imagina' {sum(r['imagina'] for r in non_empty)}/{len(non_empty)} | "
              f"copia {sum(r['copia'] for r in non_empty)/k:.0%} | palabras prom {sum(r['palabras'] for r in non_empty)/k:.0f} | "
              f"término∈texto {sum(r['termino_en_texto'] for r in non_empty)/k:.0%} | {sum(r['latencia'] for r in runs)/n:.1f}s")
    return detail


# ─── Suite 4: visión (Qwen en Ollama) ──────────────────────────────────────
V_EN_ORIGINAL = """Analyze this image and return ONLY a valid JSON object:
{
    "concept": "main concept in 3-5 words",
    "complexity": "Low, Medium or High",
    "explanation": "1-2 sentences that help the reader UNDERSTAND the hardest concept, term, or data shown"
}
Detect the language of any readable text in the image (Spanish or English).
Write BOTH "concept" and "explanation" in that detected language.
If the image has no readable text, write them in Spanish.
Do not use English just because this instruction is in English.
For "explanation": do NOT just describe or summarize what is visible in the image
(e.g. do not say "this is a bar chart showing sectors"). Instead, explain the hardest
term, concept, or data pattern shown, in plain words, as if explaining it to someone
seeing it for the first time — use a simple analogy or everyday comparison when useful.
Empty string if complexity is Low.
No markdown. No extra text. Only JSON."""


def vision_images():
    imgs = [("gráfica intermedio", Image.open(ASSETS / "chart_intermedio.png"),
             "Fig. 1. Variación de la temperatura promedio global por década respecto a 1900 (°C). Datos de la Tabla 1."),
            ("gráfica avanzado", Image.open(ASSETS / "chart_avanzado.png"),
             "Fig. 1. Contribución sectorial a emisiones de GEI equivalentes, 2023 (Gt CO₂-eq). Valores ilustrativos.")]
    try:
        r = requests.get("https://upload.wikimedia.org/wikipedia/commons/thumb/1/1c/McCarty_Glacier.jpg/500px-McCarty_Glacier.jpg",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.raise_for_status()
        imgs.append(("foto glaciar", Image.open(io.BytesIO(r.content)),
                     "Glaciar McCarty, Alaska. Muchos glaciares como este han perdido gran parte de su tamaño."))
    except requests.RequestException:
        print("  (sin internet: se omite la foto del glaciar)")
    return imgs


def run_vision(prompt, image):
    img = image.convert("RGB").copy()
    img.thumbnail((IA.MAX_IMAGE_SIDE, IA.MAX_IMAGE_SIDE), Image.LANCZOS)
    buf = io.BytesIO(); img.save(buf, format="PNG")
    payload = {"model": VISION_MODEL, "prompt": prompt, "images": [base64.b64encode(buf.getvalue()).decode()],
               "stream": False, "keep_alive": OLLAMA_KEEP_ALIVE,
               "options": {"temperature": 0, "num_predict": IA.MAX_NEW_TOKENS, "num_ctx": 2048}}
    t0 = time.time()
    raw = requests.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload, timeout=120).json()["response"]
    return raw, time.time() - t0


# Nivel diseñado de cada gráfica (data-design-level en el HTML de su página).
DESIGN_LEVELS = {"gráfica intermedio": "Medium", "gráfica avanzado": "High"}


def suite_vision(reps):
    images = vision_images()
    # El tercer elemento indica si se aplica el nivel diseñado (data-design-level),
    # como hace el backend: prompt con explicación obligatoria y nivel fijado.
    variants = [("en_prompt_original_sin_pie", lambda ctx: V_EN_ORIGINAL, False),
                ("es_prompt_sin_pie", lambda ctx: IA._build_prompt("", "Spanish"), False),
                ("es_prompt_con_pie", lambda ctx: IA._build_prompt(ctx, "Spanish"), False),
                ("es_con_pie_nivel_diseno_actual", lambda ctx: IA._build_prompt(ctx, "Spanish"), True)]
    run_vision(IA._build_prompt("", "Spanish"), images[0][1])  # calentamiento (carga del modelo)
    detail = []
    for variant, make, use_design in variants:
        runs = []
        for name, img, ctx in images:
            design = DESIGN_LEVELS.get(name) if use_design else None
            for _ in range(reps):
                raw, lat = run_vision(make(ctx), img)
                parsed = extract_json(raw) or extract_partial_analysis(raw)
                n = normalize_analysis(parsed, "") if parsed else {"concept": "", "explanation": "", "complexity": "?"}
                english = IA._is_english(n["explanation"]) or IA._is_english(n["concept"])
                llm_level = n["complexity"]
                if design and parsed:
                    n = IA.apply_design_level(n, design)
                runs.append({"imagen": name, "json_ok": parsed is not None, "ingles": english, "latencia": lat,
                             "nivel": n["complexity"], "nivel_modelo": llm_level,
                             "explicacion": n["explanation"], "concepto": n["concept"]})
        detail.append({"variante": variant, "runs": runs})
        n = len(runs)
        add("vision", variant, "responde_en_espanol", 1 - sum(r["ingles"] for r in runs) / n, n)
        add("vision", variant, "json_valido", sum(r["json_ok"] for r in runs) / n, n)
        add("vision", variant, "latencia_s_prom", sum(r["latencia"] for r in runs) / n, n)
        add("vision", variant, "latencia_s_max", max(r["latencia"] for r in runs), n)
        for lvl in ("Low", "Medium", "High"):
            add("vision", variant, f"nivel_{lvl}", sum(r["nivel"] == lvl for r in runs) / n, n)
        # Por gráfica: ¿el nivel final coincide con el diseñado y hay ayuda
        # (explicación no vacía) que mostrar? Y qué dijo el modelo.
        for chart, designed in DESIGN_LEVELS.items():
            cr = [r for r in runs if r["imagen"] == chart]
            tag = chart.split()[-1]
            add("vision", variant, f"{tag}_nivel_final_es_{designed}", sum(r["nivel"] == designed for r in cr) / len(cr), len(cr))
            add("vision", variant, f"{tag}_con_explicacion", sum(bool(r["explicacion"]) for r in cr) / len(cr), len(cr))
            add("vision", variant, f"{tag}_palabras_prom", sum(len(r["explicacion"].split()) for r in cr) / len(cr), len(cr))
            add("vision", variant, f"{tag}_modelo_dijo", "/".join(r["nivel_modelo"] for r in cr), len(cr))
        print(f"  visión [{variant}] n={n} español {1 - sum(r['ingles'] for r in runs)/n:.0%} | JSON ok {sum(r['json_ok'] for r in runs)/n:.0%} | "
              f"{sum(r['latencia'] for r in runs)/n:.1f}s prom | niveles "
              + "/".join(str(sum(r['nivel'] == l for r in runs)) for l in ("Low", "Medium", "High")))
    return detail


# ─── Main ──────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="all", choices=["all", "language", "readability", "text", "vision"])
    ap.add_argument("--reps", type=int, default=2, help="repeticiones por caso en las suites con modelo")
    args = ap.parse_args()
    detail = {}
    if args.suite in ("all", "language"):
        print("== idioma =="); suite_language()
    if args.suite in ("all", "readability"):
        print("== legibilidad =="); suite_readability()
    if args.suite in ("all", "text"):
        print("== texto (phi3) =="); detail["text"] = suite_text(args.reps)
    if args.suite in ("all", "vision"):
        print("== visión (qwen2.5vl) =="); detail["vision"] = suite_vision(args.reps)

    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = NOW.strftime("%Y%m%d_%H%M%S")
    (RESULTS / f"metrics_{stamp}.json").write_text(
        json.dumps({"fecha": NOW.isoformat(), "reps": args.reps, "filas": ROWS, "detalle": detail},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    history = RESULTS / "history.csv"
    new_file = not history.exists()
    with history.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["fecha", "suite", "variante", "metrica", "valor", "n", "notas"])
        if new_file:
            w.writeheader()
        w.writerows(ROWS)
    print(f"\nGuardado: evaluation/results/metrics_{stamp}.json y history.csv ({len(ROWS)} filas)")


if __name__ == "__main__":
    main()
