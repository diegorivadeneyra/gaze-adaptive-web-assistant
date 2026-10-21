"""Genera evaluation/cuestionarios_participante.xlsx (lo responde cada participante).

Hojas (en el orden en que se aplican; las de página se abren según el orden
aleatorio de la sesión):
  Lectura - (tema de cada página: El hielo del planeta, Causas y evidencia, Forzamiento radiativo)
      Parte A: prueba de comprensión (evaluation/prueba_comprension.md)
      Parte B: NASA-TLX según el Anexo 3 del protocolo CIEI-UTEC (proyecto IRIS,
               v3.0, 29/09/2026): 6 dimensiones (21 niveles, 0–100), las 15
               comparaciones por pares y la tabla de definiciones.
  SUS          Escala de Usabilidad del Sistema, versión en español validada
               (Sevilla-González et al., 2020).
  Post-experimento
               Anexo 4 del protocolo (cuestionario post-experimento), para los
               DOS métodos que se comparan: Método 1 = ayuda automática,
               Método 2 = ayuda a pedido.
  _mapa (oculta)
               Qué celda tiene cada respuesta: la usa
               evaluation/puntuar_cuestionarios.py (así el diseño puede cambiar
               sin romper la lectura).

Uso: python evaluation/crear_cuestionarios_excel.py
"""
import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "evaluation" / "cuestionarios_participante.xlsx"

F = "Arial"
TITLE = Font(name=F, size=14, bold=True)
SUB = Font(name=F, size=12, bold=True, color="FFFFFF")
BOLD = Font(name=F, size=11, bold=True)
NORMAL = Font(name=F, size=11)
SMALL = Font(name=F, size=9, color="606060")
ITALIC = Font(name=F, size=10, italic=True)
SUB_FILL = PatternFill("solid", fgColor="2F5496")
SOFT_FILL = PatternFill("solid", fgColor="EEF2F8")
INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")
thin = Side(style="thin", color="808080")
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
WRAP = Alignment(wrap_text=True, vertical="top")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)

# Nombres de hoja NEUTROS (por tema): "Página fácil" revelaba el nivel al
# participante. Deben coincidir con marking.js (pantalla de pausa).
PAGES = [("facil", "Lectura - El hielo del planeta"), ("intermedio", "Lectura - Causas y evidencia"), ("avanzado", "Lectura - Forzamiento radiativo")]
PREFIX = {"facil": "F", "intermedio": "I", "avanzado": "A"}

# ── NASA-TLX (Anexo 3) ──────────────────────────────────────────────
NASA_INSTR = ("Por favor, lea cuidadosamente la descripción de cada dimensión y seleccione el nivel que mejor "
              "represente su experiencia durante la realización de la tarea. Preste especial atención al "
              "significado de cada extremo de la escala.")
# clave, nombre, extremo izquierdo, extremo derecho, definición (tabla del Anexo 3)
NASA = [
    ("mental", "Exigencia mental", "Muy bajo", "Muy alto",
     "Cantidad de actividad mental y perceptiva que la tarea exige (decidir, pensar, calcular, procurar, etc.)."),
    ("fisica", "Exigencia física", "Muy bajo", "Muy alto",
     "Cantidad de actividad física que la tarea exige (mover, empujar, girar, etc.)."),
    ("temporal", "Exigencia temporal", "Muy bajo", "Muy alto",
     "Nivel de presión temporal percibida. Razón entre el tiempo necesario y el tiempo disponible para la "
     "ejecución de la tarea."),
    ("desempeno", "Desempeño", "Muy bueno", "Muy malo",
     "Medida en que el individuo se siente satisfecho con el rendimiento y desempeño de su trabajo."),
    ("esfuerzo", "Esfuerzo", "Muy bajo", "Muy alto",
     "Medida de esfuerzo físico y mental que el individuo precisa realizar para alcanzar su nivel de rendimiento."),
    ("frustracion", "Frustración", "Muy bajo", "Muy alto",
     "Nivel de inseguridad, estrés, irritación y otros sentimientos o estados negativos que el usuario "
     "experimenta durante la ejecución de la actividad."),
]
NASA_PAIRS_INSTR = ("Para cada par de mediciones que se muestran a continuación, elija entre las dos posibilidades "
                    "la que considere que tuvo mayor impacto en la carga de trabajo que sintió al completar la tarea.")
# Los 15 pares, en el orden del Anexo 3 (de arriba abajo, columna por columna).
NASA_PAIRS = [
    ("Esfuerzo", "Desempeño"), ("Exigencia temporal", "Esfuerzo"), ("Desempeño", "Frustración"),
    ("Exigencia mental", "Exigencia física"), ("Exigencia física", "Desempeño"), ("Frustración", "Esfuerzo"),
    ("Desempeño", "Exigencia temporal"), ("Exigencia física", "Frustración"), ("Frustración", "Exigencia mental"),
    ("Exigencia temporal", "Frustración"), ("Desempeño", "Exigencia mental"), ("Exigencia mental", "Esfuerzo"),
    ("Exigencia física", "Exigencia temporal"), ("Exigencia temporal", "Exigencia mental"),
    ("Esfuerzo", "Exigencia física"),
]

# ── SUS (Sevilla-González et al., 2020) ─────────────────────────────
SUS_INSTR = ("Por favor seleccione de cada uno de los enunciados la opción que mejor describa su experiencia "
             "con la herramienta electrónica. Un puntaje de 1 significa que usted se encuentra totalmente en "
             "desacuerdo con el enunciado, mientras que un puntaje en 5 significa que está totalmente de acuerdo, "
             "un puntaje de 3 significaría que usted se encuentra neutral con el enunciado.")
SUS = [
    "Me gustaría usar esta herramienta frecuentemente.",
    "Considero que esta herramienta es innecesariamente compleja",
    "Considero que la herramienta es fácil de usar.",
    "Considero necesario el apoyo de personal experto para poder utilizar esta herramienta",
    "Considero que las funciones de la herramienta están bien integradas",
    "Considero que la herramienta presenta muchas contradicciones",
    "Imagino que la mayoría de las personas aprenderían a usar esta herramienta rápidamente",
    "Considero que el uso de esta herramienta es tedioso",
    "Me sentí muy confiado al usar la herramienta",
    "Necesité saber bastantes cosas antes de poder empezar a usar esta herramienta",
]

# ── Post-experimento (Anexo 4), adaptado a 2 métodos ────────────────
METHODS = [("m1", "Método 1", "Ayuda automática: la ayuda apareció sola cuando el sistema detectó que te costaba leer."),
           ("m2", "Método 2", "Ayuda a pedido: apareció el botón \"Ver ayuda\" y tú decidías si abrirla.")]
RANKINGS = [
    ("rapido", "Considerando los 2 métodos, ¿cuál te pareció el más rápido? Por favor, ordénalos."),
    ("comodo", "¿Cuál te resultó más cómodo (en orden)?"),
    ("errores", "¿Con cuál crees que cometiste menos errores (en orden)?"),
    ("elegiria", "Si tuvieras que usar un solo método para comunicarte, ¿cuál elegirías? Por favor, ordena:"),
]
LIKERT = [
    ("rendimiento", "¿En qué medida la técnica te permitió mejorar tu rendimiento?"),
    ("menos_errores", "¿Hasta qué punto la técnica ha permitido una reducción en el número de errores cometidos?"),
    ("agradable", "¿En qué nivel resultaban más agradables de usar las interfaces con la técnica?"),
    ("aprender", "¿Qué tan fácil fue aprender a utilizar esta técnica?"),
    ("precision", "¿Qué tan precisa percibiste la técnica durante la interacción?"),
    ("confianza", "¿Qué nivel de confianza sentiste al utilizar esta técnica?"),
    ("vida_diaria", "¿Qué tan dispuesto(a) estarías a utilizar esta técnica en tu vida diaria?"),
]
COMMENTS = [
    ("positivos", "¿Qué aspectos positivos encontraste en cada técnica?"),
    ("dificultades", "¿Qué dificultades encontraste?"),
    ("sugerencias", "¿Tienes alguna sugerencia para mejorar las técnicas evaluadas?"),
]


def read_comprehension():
    """{"facil": [(pregunta, [a, b, c, d]), ...], ...} desde prueba_comprension.md."""
    text = (ROOT / "evaluation" / "prueba_comprension.md").read_text(encoding="utf-8")
    out = {page: [] for page, _ in PAGES}
    for block in re.split(r"\n(?=\*\*[FIA]\d\*\*)", text):
        head = re.match(r"\*\*([FIA])(\d)\*\*[^\n]*\n([^\n]+)\n", block)
        if not head:
            continue
        options = [re.sub(r"\s*✓", "", o).strip() for o in re.findall(r"^- [a-d]\) ([^\n]+)", block, re.M)]
        question = re.sub(r"\*\*(\w+)\*\*", lambda m: m.group(1).upper(), head.group(3)).strip()
        page = {"F": "facil", "I": "intermedio", "A": "avanzado"}[head.group(1)]
        out[page].append((question, options))
    assert all(len(v) == 6 for v in out.values()), "prueba_comprension.md debe tener 6 preguntas por página"
    return out


class Sheet:
    """Ayudante: escribe filas hacia abajo y registra cada celda de respuesta."""

    def __init__(self, wb, title, mapa, widths):
        self.ws = wb.create_sheet(title)
        self.title, self.mapa, self.r = title, mapa, 1
        for col, w in widths.items():
            self.ws.column_dimensions[col].width = w
        self.ws.sheet_view.showGridLines = False
        self.ws.page_setup.fitToWidth, self.ws.page_setup.fitToHeight = 1, 0
        self.ws.sheet_properties.pageSetUpPr.fitToPage = True
        self.validations = {}

    def text(self, text, font=NORMAL, span="A:F", height=None, fill=None):
        a, b = span.split(":")
        self.ws.merge_cells(f"{a}{self.r}:{b}{self.r}")
        c = self.ws[f"{a}{self.r}"]
        c.value, c.font, c.alignment = text, font, WRAP
        if fill:
            c.fill = fill
        if height:
            self.ws.row_dimensions[self.r].height = height
        self.r += 1

    def header(self, text):
        self.r += 1
        self.text(text, font=SUB, fill=SUB_FILL, height=22)

    def answer(self, ref, key, options, font=BOLD):
        c = self.ws[ref]
        c.fill, c.border, c.alignment, c.font = INPUT_FILL, BOX, CENTER, font
        if options:
            formula = '"' + ",".join(options) + '"'
            if formula not in self.validations:
                dv = DataValidation(type="list", formula1=formula, allow_blank=True,
                                    error="Elige una opción de la lista.", errorTitle="Respuesta no válida")
                self.ws.add_data_validation(dv)
                self.validations[formula] = dv
            self.validations[formula].add(ref)
        self.mapa.append((self.title, key, ref))


def comprehension_and_nasa(wb, mapa, key, title, questions):
    s = Sheet(wb, title, mapa, {"A": 5, "B": 34, "C": 16, "D": 13, "E": 16, "F": 30})
    ws = s.ws
    ws["A1"].value, ws["A1"].font = title, TITLE
    s.r = 2
    s.text("Celdas amarillas: haz clic y elige tu respuesta en la lista desplegable.", font=ITALIC)

    s.header("Parte A · Preguntas sobre el texto")
    s.text("Responde sin volver a la página. Elige una sola letra; si no sabes la respuesta, elige \"e\" (No lo sé).",
           font=ITALIC, height=30)
    for n, (question, options) in enumerate(questions, start=1):
        s.r += 1
        ws.cell(s.r, 1, f"{n}.").font = BOLD
        ws.merge_cells(start_row=s.r, start_column=2, end_row=s.r, end_column=4)
        q = ws.cell(s.r, 2, question)
        q.font, q.alignment = BOLD, WRAP
        ws.row_dimensions[s.r].height = 32
        ws.cell(s.r, 5, "Respuesta:").alignment = Alignment(horizontal="right", vertical="top")
        s.answer(f"F{s.r}", f"{PREFIX[key]}{n}", ["a", "b", "c", "d", "e"])
        for letter, option in zip("abcd", options):
            s.r += 1
            ws.merge_cells(start_row=s.r, start_column=2, end_row=s.r, end_column=6)
            c = ws.cell(s.r, 2, f"{letter})  {option}")
            c.font, c.alignment = NORMAL, WRAP
        s.r += 1
        ws.cell(s.r, 2, "e)  No lo sé.").font = NORMAL
        s.r += 1

    s.header("Parte B · Cuestionario NASA-TLX")
    s.text("Cuestionario NASA-TLX aplicado al proyecto IRIS · Versión 3.0 — 29/09/2026", font=SMALL)
    s.text(NASA_INSTR, font=NORMAL, height=46)
    s.text("La escala tiene 21 niveles: 0 es el extremo izquierdo y 100 el derecho (en pasos de 5).", font=ITALIC)
    s.r += 1
    for col, txt in zip("BCDE", ["Dimensión", "Extremo izquierdo (0)", "Tu nivel", "Extremo derecho (100)"]):
        c = ws[f"{col}{s.r}"]
        c.value, c.font, c.alignment = txt, BOLD, CENTER
    levels = [str(v) for v in range(0, 101, 5)]
    for dim, name, low, high, _ in NASA:
        s.r += 1
        ws.cell(s.r, 2, name).font = BOLD
        ws.cell(s.r, 3, low).alignment = CENTER
        s.answer(f"D{s.r}", f"nasa_{dim}", levels)
        ws.cell(s.r, 5, high).alignment = CENTER
        ws.row_dimensions[s.r].height = 22

    s.r += 1
    s.text(NASA_PAIRS_INSTR, font=NORMAL, height=32)
    s.text("En cada par, elige en la lista la medición que tuvo MAYOR impacto.", font=ITALIC)
    for n, (a, b) in enumerate(NASA_PAIRS, start=1):
        s.r += 1
        ws.cell(s.r, 1, f"{n}.").font = BOLD
        ws.cell(s.r, 2, f"{a}  o  {b}").font = NORMAL
        ws.merge_cells(start_row=s.r, start_column=4, end_row=s.r, end_column=5)
        s.answer(f"D{s.r}", f"par_{n:02d}", [a, b], font=NORMAL)

    s.r += 1
    s.text("Definiciones que podrá utilizar para responder el cuestionario:", font=BOLD)
    for _, name, _, _, definition in NASA:
        ws.cell(s.r, 2, name).font = BOLD
        ws.cell(s.r, 2).alignment = WRAP
        ws.merge_cells(start_row=s.r, start_column=3, end_row=s.r, end_column=6)
        c = ws.cell(s.r, 3, definition)
        c.font, c.alignment = NORMAL, WRAP
        ws.row_dimensions[s.r].height = 32
        s.r += 1


def sus_sheet(wb, mapa):
    s = Sheet(wb, "SUS", mapa, {"A": 5, "B": 62, "C": 16, "D": 13, "E": 16, "F": 4})
    ws = s.ws
    ws["A1"].value, ws["A1"].font = "Opinión sobre el sistema", TITLE
    s.r = 2
    s.text("Celdas amarillas: haz clic y elige tu respuesta en la lista desplegable.", font=ITALIC)
    s.r += 1
    s.text(SUS_INSTR, font=NORMAL, height=62)
    s.r += 1
    for col, txt in zip("BCDE", ["Enunciado", "1 = Totalmente\nen desacuerdo", "Tu respuesta", "5 = Totalmente\nde acuerdo"]):
        c = ws[f"{col}{s.r}"]
        c.value, c.font, c.alignment = txt, BOLD, CENTER
    ws.row_dimensions[s.r].height = 30
    for n, text in enumerate(SUS, start=1):
        s.r += 1
        ws.cell(s.r, 1, f"{n}.").font = BOLD
        c = ws.cell(s.r, 2, text)
        c.font, c.alignment = NORMAL, WRAP
        ws.row_dimensions[s.r].height = 30
        s.answer(f"D{s.r}", f"sus_{n}", ["1", "2", "3", "4", "5"])


def post_sheet(wb, mapa):
    s = Sheet(wb, "Post-experimento", mapa, {"A": 5, "B": 60, "C": 14, "D": 14, "E": 4, "F": 4})
    ws = s.ws
    ws["A1"].value, ws["A1"].font = "Cuestionario post-experimento", TITLE
    s.r = 2
    s.text("Versión 3.0 — 29/09/2026", font=SMALL)
    s.text("Celdas amarillas: haz clic y elige tu respuesta en la lista desplegable (o escribe, en los comentarios).",
           font=ITALIC)
    s.header("Los dos métodos que usaste")
    for _, name, description in METHODS:
        ws.cell(s.r, 2, f"{name}: {description}").font = NORMAL
        ws.cell(s.r, 2).alignment = WRAP
        ws.row_dimensions[s.r].height = 30
        s.r += 1
    s.r += 1
    s.text("Por favor, responda las siguientes preguntas:", font=BOLD)

    s.header("Ordena los métodos (1 = primer lugar, 2 = segundo lugar)")
    for key, question in RANKINGS:
        s.r += 1
        s.text(question, font=BOLD, span="A:D", height=30)
        for mkey, name, _ in METHODS:
            ws.cell(s.r, 2, name).font = NORMAL
            s.answer(f"C{s.r}", f"orden_{key}_{mkey}", ["1", "2"])
            s.r += 1

    s.header("Califica cada método de 1 (Muy bajo) a 5 (Muy alto)")
    for key, question in LIKERT:
        s.r += 1
        ws.cell(s.r, 3, "Método 1").font = BOLD
        ws.cell(s.r, 3).alignment = CENTER
        ws.cell(s.r, 4, "Método 2").font = BOLD
        ws.cell(s.r, 4).alignment = CENTER
        q = ws.cell(s.r + 1, 2, question)
        q.font, q.alignment = NORMAL, WRAP
        ws.row_dimensions[s.r + 1].height = 32
        s.r += 1
        s.answer(f"C{s.r}", f"califica_{key}_m1", ["1", "2", "3", "4", "5"])
        s.answer(f"D{s.r}", f"califica_{key}_m2", ["1", "2", "3", "4", "5"])
        s.r += 1
        ws.cell(s.r, 3, "1 = Muy bajo · 5 = Muy alto").font = SMALL
        s.r += 1

    s.header("Comentarios finales")
    for key, question in COMMENTS:
        s.r += 1
        s.text(question, font=BOLD, span="A:D")
        ws.merge_cells(start_row=s.r, start_column=2, end_row=s.r, end_column=4)
        ws.row_dimensions[s.r].height = 60
        s.answer(f"B{s.r}", f"comentario_{key}", None, font=NORMAL)
        ws[f"B{s.r}"].alignment = WRAP
        s.r += 1


def main():
    questions = read_comprehension()
    wb = Workbook()
    wb.remove(wb.active)
    mapa = []
    for key, title in PAGES:
        comprehension_and_nasa(wb, mapa, key, title, questions[key])
    sus_sheet(wb, mapa)
    post_sheet(wb, mapa)
    m = wb.create_sheet("_mapa")
    m.append(["hoja", "clave", "celda"])
    for row in mapa:
        m.append(list(row))
    m.sheet_state = "hidden"
    wb.save(OUT)
    print(f"Guardado {OUT.relative_to(ROOT)}: {len(mapa)} respuestas en {len(wb.sheetnames) - 1} hojas")


if __name__ == "__main__":
    main()
