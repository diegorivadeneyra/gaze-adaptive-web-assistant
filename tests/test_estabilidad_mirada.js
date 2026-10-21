// Estabilidad de la mirada del Tobii en los bordes de los párrafos (2026-10-20).
// Prueba el suavizado (mediana de 100 ms) y el margen de 40 px de
// frontend/js/gaze_mapping.js con una simulación.
// Uso: node tests/test_estabilidad_mirada.js
const assert = require("assert");
const M = require("../frontend/js/gaze_mapping.js");

let passed = 0;
function test(name, fn) { fn(); passed++; console.log(`  ok  ${name}`); }

test("suavizado: mediana de los últimos 150 ms (un salto suelto no la mueve)", () => {
    const pts = [{ x: 0, y: 0, timestamp: 0 }, { x: 10, y: 10, timestamp: 900 }, { x: 12, y: 8, timestamp: 950 },
                 { x: 200, y: 200, timestamp: 980 }, { x: 11, y: 9, timestamp: 1000 }];
    assert.deepStrictEqual(M.smoothPoint(pts, 1000, 150), { x: 11.5, y: 9.5 });
    assert.strictEqual(M.smoothPoint(pts, 5000, 150), null);
});

test("margen: dentro del rectángulo ampliado 40 px", () => {
    const r = { left: 100, right: 300, top: 100, bottom: 200 };
    assert.ok(M.insideRect(r, { x: 330, y: 150 }, 40));
    assert.ok(!M.insideRect(r, { x: 350, y: 150 }, 40));
    assert.ok(!M.insideRect(r, { x: 330, y: 150 }, 0));
});

// ── Simulación ────────────────────────────────────────────────────
// Párrafo de 600×200 px; 24 px más abajo empieza el párrafo vecino. Muestras
// a 34 Hz (medido con el Tobii real) con ruido gaussiano σ = 25 px. El sistema
// decide cada 100 ms y confirma un cambio de elemento si dura ≥ 300 ms (igual
// que gaze.js en modo Tobii). Simplificación: no se modela la fijación I-DT
// (al leer casi no hay: la mirada salta entre palabras).
function rng(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }
function gauss(r) { return Math.sqrt(-2 * Math.log(r() + 1e-12)) * Math.cos(2 * Math.PI * r()); }
const P = { left: 0, right: 600, top: 0, bottom: 200 };
const N = { left: 0, right: 600, top: 224, bottom: 424 };

function simulate(path, seed, mejorado, sigma = 25) {
    const r = rng(seed), samples = [];
    for (let t = 0; t <= path.duration; t += 1000 / 34) {
        const g = path.at(t);
        samples.push({ x: g.x + gauss(r) * sigma, y: g.y + gauss(r) * sigma, timestamp: t });
    }
    let current = "P", pending = null, pendingSince = 0, falseExits = 0, switchAt = null;
    for (let now = 100; now <= path.duration; now += 100) {
        const seen = samples.filter(s => s.timestamp <= now);
        const pt = mejorado ? (M.smoothPoint(seen, now, 100) || seen[seen.length - 1]) : seen[seen.length - 1];
        let cand = M.insideRect(P, pt) ? "P" : M.insideRect(N, pt) ? "N" : null;
        if (mejorado && !cand && M.insideRect(current === "P" ? P : N, pt, 40)) cand = current;
        if (cand === current) { pending = null; continue; }
        if (cand !== pending) { pending = cand; pendingSince = now; }
        if (now - pendingSince >= 300) {
            const truth = path.at(now).el;
            if (truth === current) falseExits++;
            else if (switchAt === null && cand === truth) switchAt = now - path.changeAt;
            current = cand;
            pending = null;
        }
    }
    return { falseExits, switchAt };
}

// Lectura de 60 s recorriendo los renglones de borde a borde (7 renglones).
const lectura = { duration: 60000, at(t) {
    const lineT = 2400, k = Math.floor(t / lineT) % 7, f = (t % lineT) / lineT;
    return { x: f * 600, y: 13 + k * 29, el: "P" };
} };
// Cambio real al párrafo vecino a los 3 s.
const cambio = { duration: 6000, changeAt: 3000, at(t) {
    return t < 3000 ? { x: 300, y: 187, el: "P" } : { x: 300, y: 260, el: "N" };
} };

test("simulación: menos salidas falsas en los bordes, y el cambio real se sigue detectando", () => {
    const seeds = [...Array(20).keys()].map(i => 101 + i);
    const mean = a => a.reduce((s, v) => s + v, 0) / a.length;
    const antes = mean(seeds.map(sd => simulate(lectura, sd, false).falseExits));
    const despues = mean(seeds.map(sd => simulate(lectura, sd, true).falseExits));
    const lagA = seeds.map(sd => simulate(cambio, sd, false).switchAt).filter(v => v !== null);
    const lagD = seeds.map(sd => simulate(cambio, sd, true).switchAt).filter(v => v !== null);
    console.log(`        salidas falsas por minuto de lectura: antes ${antes.toFixed(1)} → después ${despues.toFixed(1)}`);
    console.log(`        cambio real al párrafo vecino detectado: antes a los ${Math.round(mean(lagA))} ms (${lagA.length}/20)`
        + ` → después a los ${Math.round(mean(lagD))} ms (${lagD.length}/20)`);
    assert.ok(despues < antes);
    assert.strictEqual(lagD.length, 20);
});

console.log(`\n${passed} pruebas OK`);
