"""Sorteo previo y balanceado del orden de páginas y del método de cada participante.

Fácil siempre "a pedido" (fuera de la comparación de métodos); intermedia y
avanzada, una con cada método. Con N = 6: cada orden de páginas una vez,
automática 3 en intermedia y 3 en avanzada (6 lecturas por método) y leída antes
que la página a pedido en 2 de 6 (3/3 es imposible con 6). N_BLOCKS = 2 → 12.
Semilla fija: el sorteo se puede reproducir.

Salida: frontend/js/asignacion.js y evaluation/asignacion_participantes.csv
Uso: python evaluation/generar_asignacion.py
"""
import csv
import json
import random
from itertools import combinations, permutations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = 20261025
N_BLOCKS = 1          # 1 bloque de 6 = 6 participantes (2 = 12)
PAGES = ["facil", "intermedio", "avanzado"]


def main():
    rng = random.Random(SEED)
    orders = list(permutations(PAGES))
    # Bloque 1: cada orden una vez, automática 3 en intermedia y 3 en avanzada, y
    # leída antes que la página "a pedido" en 2 o 4 de 6 (para no mezclar método y orden).
    def auto_first(order, auto):
        return order.index(auto) < order.index(next(p for p in ("intermedio", "avanzado") if p != auto))
    options = []
    for chosen in combinations(range(6), 3):
        autos = ["intermedio" if i in chosen else "avanzado" for i in range(6)]
        if sum(auto_first(o, a) for o, a in zip(orders, autos)) in (2, 4):
            options.append(autos)
    block1 = list(zip(orders, rng.choice(options)))
    flip = {"intermedio": "avanzado", "avanzado": "intermedio"}
    rows = []
    for b in range(N_BLOCKS):
        block = block1 if b % 2 == 0 else [(o, flip[a]) for o, a in block1]
        block = block[:]
        rng.shuffle(block)
        rows.extend(block)

    assignment, table = {}, []
    for i, (order, auto) in enumerate(rows, start=1):
        code = f"P{i:02d}"
        plan = {p: ("ayuda" if p == auto else "a_pedido") for p in PAGES}
        assignment[code] = {"order": list(order), "plan": plan}
        table.append({"participante": code, "bloque": (i - 1) // 6 + 1,
                      **{f"posicion_{n}": p for n, p in enumerate(order, start=1)},
                      **{f"metodo_{p}": plan[p] for p in PAGES},
                      "automatica_se_lee": "antes" if auto_first(order, auto) else "despues"})

    # Comprobación del balance (si falla, no se escribe nada).
    for p in ("intermedio", "avanzado"):
        auto_n = sum(a["plan"][p] == "ayuda" for a in assignment.values())
        assert auto_n * 2 == len(assignment), (p, auto_n)
    firsts = sum(auto_first(a["order"], next(p for p, m in a["plan"].items() if m == "ayuda"))
                 for a in assignment.values())
    assert abs(firsts * 2 - len(assignment)) <= 2, firsts      # automática primero ≈ la mitad
    print(f"Automática leída antes que la página a pedido: {firsts} de {len(assignment)}")
    for pos in range(3):
        for p in PAGES:
            assert sum(a["order"][pos] == p for a in assignment.values()) * 3 == len(assignment)

    js = ROOT / "frontend" / "js" / "asignacion.js"
    js.write_text(
        "// Generado por evaluation/generar_asignacion.py (semilla " + str(SEED) + "): NO editar a mano.\n"
        "// Orden de páginas y método de cada participante, sorteados ANTES del piloto.\n"
        "const ASIGNACION = " + json.dumps(assignment, ensure_ascii=False, indent=1) + ";\n",
        encoding="utf-8")
    out = ROOT / "evaluation" / "asignacion_participantes.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(table[0].keys()))
        w.writeheader()
        w.writerows(table)
    print(f"{len(assignment)} participantes -> {js.relative_to(ROOT)} y {out.relative_to(ROOT)}")
    for r in table:
        auto = "intermedio" if r["metodo_intermedio"] == "ayuda" else "avanzado"
        print(f"  {r['participante']} (bloque {r['bloque']}): "
              f"{r['posicion_1']} > {r['posicion_2']} > {r['posicion_3']}, automatica en {auto}")


if __name__ == "__main__":
    main()
