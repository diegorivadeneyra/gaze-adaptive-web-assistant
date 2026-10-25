"""Genera evaluation/cuestionarios_participante.xlsx. Todo se responde al final,
después de las 3 páginas. Hojas, en orden:
  Comprensión       un recuadro por página para escribir lo que se entendió
  NASA-TLX          una vez, sobre toda la tarea (Anexo 3, protocolo CIEI-UTEC)
  SUS               versión en español validada (Sevilla-González et al., 2020)
  Post-experimento  Anexo 4: Método 1 = ayuda automática, Método 2 = a pedido
  _mapa (oculta)    celda de cada respuesta (la lee puntuar_cuestionarios.py)

Uso: python evaluation/crear_cuestionarios_excel.py
"""
import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.pagebreak import Break

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "evaluation" / "cuestionarios_participante.xlsx"

F = "Arial"
BANNER = Font(name=F, size=16, bold=True, color="FFFFFF")
SUB = Font(name=F, size=12, bold=True, color="FFFFFF")
BOLD = Font(name=F, size=11, bold=True)
NORMAL = Font(name=F, size=11)
SMALL = Font(name=F, size=9, color="606060")
NOTE = Font(name=F, size=10, color="404040")
STEP = Font(name=F, size=10, color="FFFFFF", italic=True)
BANNER_FILL = PatternFill("solid", fgColor="1F4E79")
SUB_FILL = PatternFill("solid", fgColor="2E75B6")
CALLOUT_FILL = PatternFill("solid", fgColor="EAF1FB")
ZEBRA_FILL = PatternFill("solid", fgColor="F7F9FC")
INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")
# Leyenda 1–5: de rojo suave (1) a verde suave (5), para leer la escala de un vistazo.
SCALE_FILLS = [PatternFill("solid", fgColor=c) for c in ("F8CBAD", "FCE4D6", "EDEDED", "E2EFDA", "C6E0B4")]
thin = Side(style="thin", color="A6A6A6")
input_side = Side(style="medium", color="BF9000")
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
INPUT_BOX = Border(left=input_side, right=input_side, top=input_side, bottom=input_side)
CALLOUT_BORDER = Border(left=Side(style="thick", color="2E75B6"))
WRAP = Alignment(wrap_text=True, vertical="top")
MIDDLE = Alignment(wrap_text=True, vertical="center")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)

# Secciones con el título de cada página tal como lo vio la persona (ayuda a
# saber de cuál se habla); NO "Página fácil", que revelaba el nivel.
PAGES = [("facil", "El hielo del planeta se está derritiendo"),
         ("intermedio", "Cambio climático: causas y evidencia observacional"),
         ("avanzado", "Forzamiento radiativo y sensibilidad climática")]
COMPRENSION_SHEET, NASA_SHEET = "Comprensión", "NASA-TLX"

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


# Opciones de las listas desplegables de 1 a 5: cada número lleva su
# significado ("4 = De acuerdo"); puntuar_cuestionarios.py lee el número del inicio.
SUS_SCALE = ["1 = Totalmente en desacuerdo", "2 = En desacuerdo", "3 = Neutral", "4 = De acuerdo",
             "5 = Totalmente de acuerdo"]
LIKERT_SCALE = ["1 = Muy bajo", "2 = Bajo", "3 = Medio", "4 = Alto", "5 = Muy alto"]
RANK_SCALE = ["1 = Primer lugar", "2 = Segundo lugar"]
HOW_TO = "Cómo responder: haz clic en una celda amarilla y elige tu respuesta en la flecha ▼ que aparece a la derecha."
N_SHEETS = 4


class Sheet:
    """Ayudante: escribe filas hacia abajo y registra cada celda de respuesta."""

    def __init__(self, wb, title, mapa, widths, last_col="F", tab_color="2E75B6"):
        self.ws = wb.create_sheet(title)
        self.title, self.mapa, self.r, self.last = title, mapa, 1, last_col
        for col, w in widths.items():
            self.ws.column_dimensions[col].width = w
        self.ws.sheet_view.showGridLines = False
        self.ws.sheet_properties.tabColor = tab_color
        self.ws.page_setup.fitToWidth, self.ws.page_setup.fitToHeight = 1, 0
        self.ws.sheet_properties.pageSetUpPr.fitToPage = True
        self.ws.print_options.horizontalCentered = True
        self.validations = {}

    def merge(self, first, last, row=None):
        row = row or self.r
        if first != last:
            self.ws.merge_cells(f"{first}{row}:{last}{row}")
        return self.ws[f"{first}{row}"]

    def style_range(self, first, last, row, fill=None, border=None):
        """Formato a TODAS las celdas de un rango (en celdas combinadas, el borde
        solo de la primera se ve cortado)."""
        for col in range(self.ws[f"{first}1"].column, self.ws[f"{last}1"].column + 1):
            c = self.ws.cell(row, col)
            if fill:
                c.fill = fill
            if border:
                c.border = border

    def banner(self, title, step, subtitle):
        """Franja de título + "Hoja n de 4"; queda fija al desplazarse."""
        c = self.merge("A", self.last)
        c.value, c.font, c.alignment = title, BANNER, Alignment(vertical="center", indent=1)
        self.style_range("A", self.last, self.r, fill=BANNER_FILL)
        self.ws.row_dimensions[self.r].height = 36
        self.r += 1
        c = self.merge("A", self.last)
        c.value, c.font, c.alignment = f"Hoja {step} de {N_SHEETS} · {subtitle}", STEP, Alignment(vertical="center", indent=1)
        self.style_range("A", self.last, self.r, fill=BANNER_FILL)
        self.ws.row_dimensions[self.r].height = 20
        self.ws.freeze_panes = "A3"
        self.r += 2

    def text(self, text, font=NORMAL, first="A", height=None, fill=None, alignment=WRAP):
        c = self.merge(first, self.last)
        c.value, c.font, c.alignment = text, font, alignment
        if fill:
            self.style_range(first, self.last, self.r, fill=fill)
        if height:
            self.ws.row_dimensions[self.r].height = height
        self.r += 1

    def callout(self, lines):
        """Recuadro celeste de instrucciones: [(texto, fuente, alto), ...]."""
        for text, font, height in lines:
            c = self.merge("A", self.last)
            c.value, c.font, c.alignment = text, font, Alignment(wrap_text=True, vertical="center", indent=1)
            self.style_range("A", self.last, self.r, fill=CALLOUT_FILL)
            self.ws[f"A{self.r}"].border = CALLOUT_BORDER
            self.ws.row_dimensions[self.r].height = height
            self.r += 1
        self.r += 1

    def legend(self, title, scale):
        """Qué significa cada número, ANTES de las preguntas (un número por fila)."""
        self.text(title, font=BOLD, first="B")
        for n, (label, fill) in enumerate(zip(scale, SCALE_FILLS if len(scale) == 5 else SCALE_FILLS[::4])):
            number, meaning = label.split(" = ")
            c = self.ws.cell(self.r, 1, int(number))
            c.font, c.alignment, c.fill, c.border = BOLD, CENTER, fill, BOX
            c = self.merge("B", "B")
            c.value, c.font, c.alignment = meaning, NORMAL, Alignment(vertical="center", indent=1)
            c.fill, c.border = fill, BOX
            self.ws.row_dimensions[self.r].height = 20
            self.r += 1
        self.r += 1

    def header(self, text):
        self.r += 1
        c = self.merge("A", self.last)
        c.value, c.font, c.alignment = text, SUB, Alignment(vertical="center", indent=1)
        self.style_range("A", self.last, self.r, fill=SUB_FILL)
        self.ws.row_dimensions[self.r].height = 26
        self.r += 2

    def table_head(self, labels):
        """Fila de encabezados de tabla: {columna: texto}."""
        for col, text in labels.items():
            c = self.ws[f"{col}{self.r}"]
            c.value, c.font, c.alignment, c.fill, c.border = text, BOLD, CENTER, CALLOUT_FILL, BOX
        self.ws.row_dimensions[self.r].height = 32
        self.r += 1

    def answer(self, ref, key, options, font=BOLD, to=None):
        """Celda amarilla de respuesta (con lista desplegable si hay opciones);
        `to` = última columna si la celda va combinada."""
        c = self.ws[ref]
        col, row = re.match(r"([A-Z]+)(\d+)", ref).groups()
        if to:
            self.ws.merge_cells(f"{ref}:{to}{row}")
        self.style_range(col, to or col, int(row), fill=INPUT_FILL, border=INPUT_BOX)
        c.alignment, c.font = CENTER, font
        if options:
            formula = '"' + ",".join(options) + '"'
            if formula not in self.validations:
                dv = DataValidation(type="list", formula1=formula, allow_blank=True, showInputMessage=True,
                                    promptTitle="Elige una opción", prompt="Usa la flecha ▼ de la derecha.",
                                    error="Elige una opción de la lista.", errorTitle="Respuesta no válida")
                self.ws.add_data_validation(dv)
                self.validations[formula] = dv
            self.validations[formula].add(ref)
        self.mapa.append((self.title, key, ref))


def comprehension_sheet(wb, mapa):
    """Comprensión por recuerdo libre (2026-10-25): un recuadro por página web
    donde la persona escribe lo que entendió. Clave en _mapa: resumen_<página>."""
    s = Sheet(wb, COMPRENSION_SHEET, mapa, {"A": 6, "B": 30, "C": 16, "D": 16, "E": 13, "F": 16})
    ws = s.ws
    s.banner("Lo que entendiste de cada página web", 1, "Comprensión")
    s.callout([("Sin volver a las páginas web, escribe en cada recuadro amarillo, con tus propias palabras, "
                "lo que entendiste de esa página: las ideas principales y los detalles que recuerdes.", BOLD, 34),
               ("No importa la redacción: puedes escribir oraciones o una lista de ideas. Si de una página no "
                "recuerdas nada, escribe «No recuerdo».", NORMAL, 30),
               ("Cómo escribir: haz clic en el recuadro y escribe. Para pasar a otra línea dentro del recuadro "
                "usa Alt + Enter. Al terminar, pulsa Enter o haz clic fuera del recuadro.", NOTE, 30)])
    for i, (key, title) in enumerate(PAGES):
        if i:
            ws.row_breaks.append(Break(id=s.r - 1))   # al imprimir, cada página web empieza en hoja nueva
        s.header(f"Página web: «{title}»")   # sin número: cada persona las leyó en otro orden
        s.text("¿Qué entendiste de esta página web?", font=BOLD)
        s.answer(f"A{s.r}", f"resumen_{key}", None, font=NORMAL, to="F")
        ws[f"A{s.r}"].alignment = Alignment(wrap_text=True, vertical="top", indent=1)
        ws.row_dimensions[s.r].height = 260
        s.r += 2


def nasa_sheet(wb, mapa):
    s = Sheet(wb, NASA_SHEET, mapa, {"A": 6, "B": 22, "C": 12, "D": 20, "E": 12, "F": 46}, tab_color="7030A0")
    ws = s.ws
    s.banner("Cuestionario NASA-TLX", 2, "Carga de trabajo")
    s.callout([(HOW_TO, NORMAL, 30),
               ("Responde pensando en TODA la tarea: la lectura de las 3 páginas web.", BOLD, 24)])
    s.text("Cuestionario NASA-TLX aplicado al proyecto IRIS · Versión 3.0 — 29/09/2026", font=SMALL)

    s.header("Parte 1 · ¿Cuánto te exigió la tarea?")
    s.text(NASA_INSTR, height=46)
    s.text("La escala va de 0 a 100 en pasos de 5: 0 es el extremo izquierdo y 100 el derecho. "
           "Ojo: en «Desempeño» la escala va al revés (0 = Muy bueno, 100 = Muy malo).", font=NOTE, height=32)
    s.r += 1
    s.table_head({"B": "Dimensión", "C": "Si eliges 0", "D": "Tu nivel\n(0 a 100)", "E": "Si eliges 100",
                  "F": "Qué significa"})
    levels = [str(v) for v in range(0, 101, 5)]
    for i, (dim, name, low, high, definition) in enumerate(NASA):
        fill = ZEBRA_FILL if i % 2 else None
        ws.cell(s.r, 2, name).font = BOLD
        ws.cell(s.r, 3, low).font = NOTE
        ws.cell(s.r, 5, high).font = NOTE
        ws.cell(s.r, 6, definition).font = SMALL
        for col in (2, 3, 5, 6):
            c = ws.cell(s.r, col)
            c.alignment, c.border = (MIDDLE if col in (2, 6) else CENTER), BOX
            if fill:
                c.fill = fill
        s.answer(f"D{s.r}", f"nasa_{dim}", levels)
        ws.row_dimensions[s.r].height = 44
        s.r += 1

    s.header("Parte 2 · Comparaciones por pares")
    s.text(NASA_PAIRS_INSTR, height=32)
    s.text("En cada fila, elige en la lista cuál de las dos tuvo MAYOR impacto. "
           "Puedes revisar qué significa cada una en la tabla de la Parte 1.", font=NOTE, height=30)
    s.r += 1
    s.table_head({"A": "N.º", "B": "Opción A", "C": "", "D": "Opción B", "E": "Tu elección"})
    ws.merge_cells(f"E{s.r - 1}:F{s.r - 1}")
    for n, (a, b) in enumerate(NASA_PAIRS, start=1):
        fill = ZEBRA_FILL if n % 2 == 0 else None
        for col, value in ((1, n), (2, a), (3, "o"), (4, b)):
            c = ws.cell(s.r, col, value)
            c.font = BOLD if col == 1 else (NOTE if col == 3 else NORMAL)
            c.alignment, c.border = CENTER, BOX
            if fill:
                c.fill = fill
        s.answer(f"E{s.r}", f"par_{n:02d}", [a, b], font=NORMAL, to="F")
        ws.row_dimensions[s.r].height = 22
        s.r += 1


def sus_sheet(wb, mapa):
    s = Sheet(wb, "SUS", mapa, {"A": 6, "B": 62, "C": 32}, last_col="C", tab_color="00B050")
    ws = s.ws
    s.banner("Opinión sobre el sistema", 3, "SUS")
    s.callout([(HOW_TO, NORMAL, 30), (SUS_INSTR, NORMAL, 64)])
    s.legend("Qué significa cada número:", SUS_SCALE)
    s.table_head({"A": "N.º", "B": "Enunciado", "C": "Tu respuesta"})
    for n, text in enumerate(SUS, start=1):
        fill = ZEBRA_FILL if n % 2 == 0 else None
        for col, value in ((1, n), (2, text)):
            c = ws.cell(s.r, col, value)
            c.font = BOLD if col == 1 else NORMAL
            c.alignment, c.border = (CENTER if col == 1 else Alignment(wrap_text=True, vertical="center", indent=1)), BOX
            if fill:
                c.fill = fill
        s.answer(f"C{s.r}", f"sus_{n}", SUS_SCALE, font=NORMAL)
        ws.row_dimensions[s.r].height = 34
        s.r += 1


def post_sheet(wb, mapa):
    s = Sheet(wb, "Post-experimento", mapa, {"A": 6, "B": 58, "C": 22, "D": 22}, last_col="D", tab_color="C55A11")
    ws = s.ws
    s.banner("Cuestionario post-experimento", 4, "Comparación de los dos métodos")
    s.text("Versión 3.0 — 29/09/2026", font=SMALL)
    s.callout([(HOW_TO + " En los comentarios, escribe directamente en el recuadro.", NORMAL, 30),
               ("Los dos métodos que usaste:", BOLD, 20)]
              + [(f"{name}: {description}", NORMAL, 22) for _, name, description in METHODS])

    s.header("Ordena los métodos")
    s.legend("Qué significa cada número:", RANK_SCALE)
    for key, question in RANKINGS:
        s.text(question, font=BOLD, height=30, alignment=MIDDLE)
        for mkey, name, _ in METHODS:
            c = ws.cell(s.r, 2, name)
            c.font, c.alignment = NORMAL, Alignment(vertical="center", indent=2)
            s.answer(f"C{s.r}", f"orden_{key}_{mkey}", RANK_SCALE, font=NORMAL)
            ws.row_dimensions[s.r].height = 20
            s.r += 1
        s.r += 1

    s.header("Califica cada método de 1 a 5")
    s.legend("Qué significa cada número:", LIKERT_SCALE)
    s.table_head({"A": "N.º", "B": "Pregunta", "C": "Método 1\n(automática)", "D": "Método 2\n(a pedido)"})
    for n, (key, question) in enumerate(LIKERT, start=1):
        fill = ZEBRA_FILL if n % 2 == 0 else None
        for col, value in ((1, n), (2, question)):
            c = ws.cell(s.r, col, value)
            c.font = BOLD if col == 1 else NORMAL
            c.alignment, c.border = (CENTER if col == 1 else Alignment(wrap_text=True, vertical="center", indent=1)), BOX
            if fill:
                c.fill = fill
        s.answer(f"C{s.r}", f"califica_{key}_m1", LIKERT_SCALE, font=NORMAL)
        s.answer(f"D{s.r}", f"califica_{key}_m2", LIKERT_SCALE, font=NORMAL)
        ws.row_dimensions[s.r].height = 34
        s.r += 1

    s.header("Comentarios finales")
    for key, question in COMMENTS:
        s.text(question, font=BOLD)
        s.answer(f"A{s.r}", f"comentario_{key}", None, font=NORMAL, to="D")
        ws[f"A{s.r}"].alignment = Alignment(wrap_text=True, vertical="top", indent=1)
        ws.row_dimensions[s.r].height = 70
        s.r += 2


def main():
    wb = Workbook()
    wb.remove(wb.active)
    mapa = []
    comprehension_sheet(wb, mapa)
    nasa_sheet(wb, mapa)
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
