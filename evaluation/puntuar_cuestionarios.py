"""Lee los Excel respondidos por los participantes y calcula sus puntajes.

Cada participante responde una copia de evaluation/cuestionarios_participante.xlsx
(se genera con evaluation/crear_cuestionarios_excel.py) y se guarda en
data/respuestas/ con su código como nombre (P01.xlsx, P02.xlsx…; data/ está
fuera de git: son datos de participantes). La celda de cada respuesta se lee
de la hoja oculta "_mapa" del propio Excel.

Puntajes:
  - Comprensión (6 por página): 1 si acierta; 0 si falla, elige "No lo sé" o
    la deja vacía. Respuestas correctas y tipo (literal / inferencial): las
    marcadas con ✓ en evaluation/prueba_comprension.md.
  - NASA-TLX (Anexo 3, por página): 6 dimensiones de 0 a 100 (en Desempeño,
    0 = Muy bueno). Peso de cada dimensión = veces que se eligió en las 15
    comparaciones por pares (0 a 5; suman 15).
      nasa_bruto     = promedio de las 6 dimensiones (Raw TLX)
      nasa_ponderado = suma(nivel × peso) / 15 (TLX ponderado clásico)
  - SUS: impares = respuesta − 1, pares = 5 − respuesta; suma × 2.5 (0–100).
  - Post-experimento (Anexo 4): orden de los 2 métodos (1 = primer lugar) en
    4 preguntas, 7 calificaciones de 1 a 5 por método y 3 comentarios.
    Método 1 = ayuda automática (condición "ayuda"); Método 2 = ayuda a
    pedido (condición "a_pedido").
Lo que falte o sea incoherente se avisa (pantalla y avisos.txt).

Salida en data/sessions/resumen/ (junto a las tablas del sistema):
  respuestas_detalle.csv     una fila por pregunta de comprensión
  cuestionarios_paginas.csv  una fila por participante y página (comprensión y NASA-TLX)
  sus.csv                    una fila por participante
  post_experimento.csv       una fila por participante (Anexo 4, todo)
  post_metodos.csv           una fila por participante y método (para comparar métodos)
  avisos.txt

Uso: python evaluation/puntuar_cuestionarios.py
"""
import csv
import json
import re
import sys
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent.parent
IN_DIR = ROOT / "data" / "respuestas"
OUT_DIR = ROOT / "data" / "sessions" / "resumen"

# Hoja del Excel -> página del sistema (nombres neutros, ver crear_cuestionarios_excel.py).
PAGES = {"Lectura - El hielo del planeta": "facil", "Lectura - Causas y evidencia": "intermedio", "Lectura - Forzamiento radiativo": "avanzado"}
PREFIX = {"facil": "F", "intermedio": "I", "avanzado": "A"}
NASA_KEYS = ["mental", "fisica", "temporal", "desempeno", "esfuerzo", "frustracion"]
NASA_NAME_TO_KEY = {"Exigencia mental": "mental", "Exigencia física": "fisica", "Exigencia temporal": "temporal",
                    "Desempeño": "desempeno", "Esfuerzo": "esfuerzo", "Frustración": "frustracion"}
METHODS = {"m1": "ayuda", "m2": "a_pedido"}          # método del Anexo 4 -> condición del sistema
RANKINGS = ["rapido", "comodo", "errores", "elegiria"]
LIKERT = ["rendimiento", "menos_errores", "agradable", "aprender", "precision", "confianza", "vida_diaria"]
COMMENTS = ["positivos", "dificultades", "sugerencias"]


def load_key():
    """{"F1": {"tipo": "literal", "correcta": "a"}, ...} desde prueba_comprension.md."""
    text = (ROOT / "evaluation" / "prueba_comprension.md").read_text(encoding="utf-8")
    key = {}
    for block in re.split(r"\n(?=\*\*[FIA]\d\*\*)", text):
        head = re.match(r"\*\*([FIA]\d)\*\*\s*·\s*(literal|inferencial)", block)
        if not head:
            continue
        correct = re.search(r"^- ([a-d])\)[^\n]*✓", block, re.M)
        if not correct:
            sys.exit(f"Pregunta {head.group(1)} sin respuesta correcta (✓) en prueba_comprension.md")
        key[head.group(1)] = {"tipo": head.group(2), "correcta": correct.group(1)}
    if len(key) != 18:
        sys.exit(f"Se esperaban 18 preguntas en prueba_comprension.md y se leyeron {len(key)}")
    return key


def number(value, low, high):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
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
    key = load_key()
    blocks = json.loads((ROOT / "evaluation/assets/prueba_comprension_bloques.json").read_text(encoding="utf-8"))["preguntas"]
    files = sorted(f for f in IN_DIR.glob("*.xlsx") if not f.name.startswith("~$"))   # ~$ = abierto en Excel
    if not files:
        sys.exit(f"No hay Excel en {IN_DIR.relative_to(ROOT)} (guarda cada uno como P01.xlsx, P02.xlsx…)")

    detail, pages, sus_rows, post_rows, method_rows, warnings = [], [], [], [], [], []
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

        # ── Comprensión y NASA-TLX por página ───────────────────────
        for sheet, page in PAGES.items():
            row = {"participante": participant, "pagina": page}
            score = {"literal": 0, "inferencial": 0}
            blank = dont_know = 0
            for n in range(1, 7):
                qid = f"{PREFIX[page]}{n}"
                raw = ans.get(sheet, qid)
                answer = str(raw).strip().lower() if raw is not None else None
                if answer is None:
                    blank += 1
                    warn(f"{page}, pregunta {n}: sin responder")
                elif answer not in ("a", "b", "c", "d", "e"):
                    warn(f"{page}, pregunta {n}: respuesta no válida '{answer}' (se cuenta como error)")
                hit = int(answer == key[qid]["correcta"])
                dont_know += int(answer == "e")
                score[key[qid]["tipo"]] += hit
                detail.append({"participante": participant, "pagina": page, "pregunta": qid,
                               "tipo": key[qid]["tipo"], "bloque": blocks.get(qid, ""),
                               "respuesta": answer or "", "correcta": key[qid]["correcta"], "acierto": hit})
            row.update(comprension_total=score["literal"] + score["inferencial"],
                       comprension_literal=score["literal"], comprension_inferencial=score["inferencial"],
                       no_lo_se=dont_know, sin_responder=blank)

            levels = {}
            for dim in NASA_KEYS:
                v = number(ans.get(sheet, f"nasa_{dim}"), 0, 100)
                if v is None:
                    warn(f"{page}, NASA-TLX '{dim}': sin responder o fuera de 0–100")
                levels[dim] = v
                row[f"nasa_{dim}"] = "" if v is None else v
            weights = dict.fromkeys(NASA_KEYS, 0)
            pairs_ok = 0
            for n in range(1, 16):
                choice = ans.get(sheet, f"par_{n:02d}")
                dim = NASA_NAME_TO_KEY.get(str(choice).strip()) if choice is not None else None
                if dim is None:
                    warn(f"{page}, NASA-TLX comparación {n}: sin responder")
                    continue
                weights[dim] += 1
                pairs_ok += 1
            for dim in NASA_KEYS:
                row[f"peso_{dim}"] = weights[dim] if pairs_ok == 15 else ""
            complete = None not in levels.values()
            row["nasa_bruto"] = round(sum(levels.values()) / 6, 1) if complete else ""
            row["nasa_ponderado"] = (round(sum(levels[d] * weights[d] for d in NASA_KEYS) / 15, 1)
                                     if complete and pairs_ok == 15 else "")
            pages.append(row)

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
    outputs = {"respuestas_detalle.csv": detail, "cuestionarios_paginas.csv": pages, "sus.csv": sus_rows,
               "post_experimento.csv": post_rows, "post_metodos.csv": method_rows}
    for name, rows in outputs.items():
        write(OUT_DIR / name, rows)
    (OUT_DIR / "avisos.txt").write_text("\n".join(warnings) or "Sin avisos.", encoding="utf-8")

    print(f"Leídos {len(files)} archivos: {', '.join(codes)}")
    for row in pages:
        print(f"  {row['participante']:6} {row['pagina']:10} comprensión {row['comprension_total']}/6 "
              f"(lit. {row['comprension_literal']}/3, inf. {row['comprension_inferencial']}/3) · "
              f"NASA bruto {row['nasa_bruto'] if row['nasa_bruto'] != '' else '—'}, "
              f"ponderado {row['nasa_ponderado'] if row['nasa_ponderado'] != '' else '—'}")
    for row in sus_rows:
        print(f"  {row['participante']:6} SUS {row['sus_puntaje'] if row['sus_puntaje'] != '' else '—'}")
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
