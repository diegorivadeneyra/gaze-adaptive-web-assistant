"""Lee los Excel respondidos (data/respuestas/P01.xlsx…; celdas según la hoja _mapa)
y calcula los puntajes en data/sessions/resumen/:
  comprension_textos.csv  texto por página + columnas para calificar a mano
                          (ideas_correctas, ideas_incorrectas, notas; se conservan)
  nasa_tlx.csv            6 dimensiones 0–100 (Desempeño: 0 = Muy bueno); peso = veces
                          elegida en los 15 pares. bruto = promedio; ponderado = suma(nivel × peso) / 15
  sus.csv                 impares − 1, 5 − pares; suma × 2.5 (0–100)
  post_experimento.csv    Anexo 4 adaptado (Método 1 = "ayuda", Método 2 = "a_pedido");
                          en "distraccion" un valor alto es negativo
  post_metodos.csv        una fila por participante y método
  avisos.txt              respuestas vacías o incoherentes

Uso: python evaluation/puntuar_cuestionarios.py
"""
import csv
import re
import sys
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent.parent
IN_DIR = ROOT / "data" / "respuestas"
OUT_DIR = ROOT / "data" / "sessions" / "resumen"

# Hojas del Excel (ver crear_cuestionarios_excel.py).
COMPRENSION_SHEET, NASA_SHEET = "Comprensión", "NASA-TLX"
PAGES = ["facil", "intermedio", "avanzado"]
MANUAL = ["ideas_correctas", "ideas_incorrectas", "notas"]   # columnas que se llenan a mano
NASA_KEYS = ["mental", "fisica", "temporal", "desempeno", "esfuerzo", "frustracion"]
NASA_NAME_TO_KEY = {"Exigencia mental": "mental", "Exigencia física": "fisica", "Exigencia temporal": "temporal",
                    "Desempeño": "desempeno", "Esfuerzo": "esfuerzo", "Frustración": "frustracion"}
METHODS = {"m1": "ayuda", "m2": "a_pedido"}          # método del Anexo 4 -> condición del sistema
RANKINGS = ["momento", "comodo", "comprension", "elegiria"]
# "distraccion" es inversa: 5 = distrajo mucho (se guarda tal cual).
LIKERT = ["entender", "utilidad", "agradable", "aprender", "oportuna", "confianza", "vida_diaria", "distraccion"]
COMMENTS = ["positivos", "dificultades", "sugerencias"]


def number(value, low, high):
    """Número de la respuesta; acepta las opciones con significado ("4 = De acuerdo")."""
    match = re.match(r"\s*(\d+(?:\.\d+)?)", str(value)) if value is not None else None
    if not match:
        return None
    v = float(match.group(1))
    return v if low <= v <= high else None


class Answers:
    """Lee las respuestas de un Excel usando su hoja oculta _mapa."""

    def __init__(self, wb):
        self.wb = wb
        self.cells = {(h, k): c for h, k, c in wb["_mapa"].iter_rows(min_row=2, values_only=True)}

    def get(self, sheet, key):
        ref = self.cells.get((sheet, key))
        if ref is None or sheet not in self.wb.sheetnames:
            return None
        value = self.wb[sheet][ref].value
        return None if value is None or str(value).strip() == "" else value


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # la consola de Windows no imprime "⚠"
    # Calificaciones a mano ya hechas: se conservan al regenerar el archivo.
    graded = {}
    texts_csv = OUT_DIR / "comprension_textos.csv"
    if texts_csv.exists():
        with texts_csv.open(encoding="utf-8-sig", newline="") as f:
            graded = {(r["participante"], r["pagina"]): r for r in csv.DictReader(f)}
    files = sorted(f for f in IN_DIR.glob("*.xlsx") if not f.name.startswith("~$"))   # ~$ = abierto en Excel
    if not files:
        sys.exit(f"No hay Excel en {IN_DIR.relative_to(ROOT)} (guarda cada uno como P01.xlsx, P02.xlsx…)")

    pages, nasa_rows, sus_rows, post_rows, method_rows, warnings = [], [], [], [], [], []
    for path in files:
        participant = path.stem.strip().upper()
        try:
            wb = load_workbook(path, data_only=True)
        except Exception as error:
            warnings.append(f"{path.name}: no se pudo abrir ({error})")
            continue
        if "_mapa" not in wb.sheetnames:
            warnings.append(f"{path.name}: es de una versión anterior del cuestionario (sin hoja _mapa); no se leyó")
            continue
        ans = Answers(wb)
        warn = lambda msg: warnings.append(f"{participant}, {msg}")

        # ── Comprensión: lo que escribió de cada página ─────────────
        for page in PAGES:
            raw = ans.get(COMPRENSION_SHEET, f"resumen_{page}")
            text = "" if raw is None else str(raw).strip()
            if not text:
                warn(f"comprensión, página {page}: recuadro vacío")
            old = graded.get((participant, page), {})
            pages.append({"participante": participant, "pagina": page, "palabras": len(re.findall(r"\w+", text)),
                          "texto": text, **{c: old.get(c, "") for c in MANUAL}})

        # ── NASA-TLX (una vez, sobre toda la tarea) ─────────────────
        nasa = {"participante": participant}
        levels = {}
        for dim in NASA_KEYS:
            v = number(ans.get(NASA_SHEET, f"nasa_{dim}"), 0, 100)
            if v is None:
                warn(f"NASA-TLX '{dim}': sin responder o fuera de 0–100")
            levels[dim] = v
            nasa[f"nasa_{dim}"] = "" if v is None else v
        weights = dict.fromkeys(NASA_KEYS, 0)
        pairs_ok = 0
        for n in range(1, 16):
            choice = ans.get(NASA_SHEET, f"par_{n:02d}")
            dim = NASA_NAME_TO_KEY.get(str(choice).strip()) if choice is not None else None
            if dim is None:
                warn(f"NASA-TLX comparación {n}: sin responder")
                continue
            weights[dim] += 1
            pairs_ok += 1
        for dim in NASA_KEYS:
            nasa[f"peso_{dim}"] = weights[dim] if pairs_ok == 15 else ""
        complete = None not in levels.values()
        nasa["nasa_bruto"] = round(sum(levels.values()) / 6, 1) if complete else ""
        nasa["nasa_ponderado"] = (round(sum(levels[d] * weights[d] for d in NASA_KEYS) / 15, 1)
                                  if complete and pairs_ok == 15 else "")
        nasa_rows.append(nasa)

        # ── SUS ─────────────────────────────────────────────────────
        sus = {"participante": participant}
        values = []
        for n in range(1, 11):
            v = number(ans.get("SUS", f"sus_{n}"), 1, 5)
            if v is None:
                warn(f"SUS, enunciado {n}: sin responder o fuera de 1–5")
            sus[f"sus_{n}"] = "" if v is None else int(v)
            values.append(v)
        sus["sus_puntaje"] = (sum((v - 1) if i % 2 == 0 else (5 - v) for i, v in enumerate(values)) * 2.5
                              if None not in values else "")
        sus_rows.append(sus)

        # ── Post-experimento (Anexo 4) ──────────────────────────────
        post = {"participante": participant}
        per_method = {m: {"participante": participant, "metodo": m, "condicion": c} for m, c in METHODS.items()}
        for item in RANKINGS:
            ranks = {}
            for m in METHODS:
                v = number(ans.get("Post-experimento", f"orden_{item}_{m}"), 1, 2)
                ranks[m] = None if v is None else int(v)
                post[f"orden_{item}_{m}"] = "" if v is None else int(v)
                per_method[m][f"orden_{item}"] = "" if v is None else int(v)
            if None in ranks.values():
                warn(f"post-experimento, orden '{item}': sin responder")
            elif ranks["m1"] == ranks["m2"]:
                warn(f"post-experimento, orden '{item}': los dos métodos tienen el mismo lugar ({ranks['m1']})")
        for item in LIKERT:
            for m in METHODS:
                v = number(ans.get("Post-experimento", f"califica_{item}_{m}"), 1, 5)
                if v is None:
                    warn(f"post-experimento, '{item}' ({m}): sin responder o fuera de 1–5")
                post[f"califica_{item}_{m}"] = "" if v is None else int(v)
                per_method[m][f"califica_{item}"] = "" if v is None else int(v)
        for item in COMMENTS:
            text = ans.get("Post-experimento", f"comentario_{item}")
            post[f"comentario_{item}"] = "" if text is None else str(text).strip()
        post_rows.append(post)
        method_rows.extend(per_method.values())

    codes = [f.stem.strip().upper() for f in files]
    for code in sorted({c for c in codes if codes.count(c) > 1}):
        warnings.append(f"Código repetido: {code} aparece en más de un archivo")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = {"comprension_textos.csv": pages, "nasa_tlx.csv": nasa_rows,
               "sus.csv": sus_rows,
               "post_experimento.csv": post_rows, "post_metodos.csv": method_rows}
    for name, rows in outputs.items():
        write(OUT_DIR / name, rows)
    (OUT_DIR / "avisos.txt").write_text("\n".join(warnings) or "Sin avisos.", encoding="utf-8")

    print(f"Leídos {len(files)} archivos: {', '.join(codes)}")
    for row in pages:
        print(f"  {row['participante']:6} {row['pagina']:10} comprensión: {row['palabras']} palabras"
              + (f", calificada ({row['ideas_correctas']} ideas correctas)" if row["ideas_correctas"] != "" else ""))
    dash = lambda v: v if v != "" else "—"
    for nasa, sus in zip(nasa_rows, sus_rows):
        print(f"  {nasa['participante']:6} NASA bruto {dash(nasa['nasa_bruto'])}, "
              f"ponderado {dash(nasa['nasa_ponderado'])} · SUS {dash(sus['sus_puntaje'])}")
    print(f"\n{len(warnings)} aviso(s)" + (":" if warnings else "."))
    for w in warnings:
        print("  ⚠", w)
    print(f"\nGuardado en {OUT_DIR.relative_to(ROOT)}: {', '.join(outputs)}, avisos.txt")


def write(path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as f:   # utf-8-sig: Excel abre bien los acentos
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
