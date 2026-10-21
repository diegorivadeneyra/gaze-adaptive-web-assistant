// Pruebas del modelo de lectura (frontend/js/reading_model.js).
//
// 1) Pruebas unitarias de cada regla (atascado y su tope, relectura al
//    volver, relectura dentro del párrafo, salida corta, reinicio, ritmo).
// 2) Simulación con los párrafos reales de las 3 páginas
//    (evaluation/assets/bloques_lectura.json) y lectores SIMULADOS. Compara:
//      - la regla anterior (solo contenido + tiempo fijo),
//      - la regla por conducta con los tiempos actuales (v2) y con la
//        propuesta para acortarlos (v3).
//    (Resultados de versiones anteriores, v1, en REGLAS_DEL_SISTEMA.md §8.)
//    Mide ayudas innecesarias (a quien no se trabó), cobertura (a quien sí) y
//    demora. Es una prueba del MECANISMO con lectores inventados, no de
//    personas reales: eso lo mide el piloto (marcado → acierto y cobertura).
//
// Uso: node tests/test_reading_model.js
// Los parámetros se leen de backend/analyzers/decision_engine.py.

const assert = require("assert");
const path = require("path");
const fs = require("fs");
const { execFileSync } = require("child_process");
const { createReadingModel } = require("../frontend/js/reading_model.js");

const ROOT = path.resolve(__dirname, "..");
const POLICY = JSON.parse(execFileSync("python", ["-c",
    "import json,sys; sys.path.insert(0,'backend'); "
    + "from analyzers.decision_engine import READING_POLICY, HELP_POLICY; "
    + "print(json.dumps({'reading': READING_POLICY, 'help': HELP_POLICY}))"], { cwd: ROOT }).toString());
const RP = POLICY.reading;
const BLOCKS = JSON.parse(fs.readFileSync(path.join(ROOT, "evaluation/assets/bloques_lectura.json"), "utf8")).bloques;

// Zona vertical según cuánto del párrafo se ha recorrido (lectura de arriba abajo).
const zoneAt = progress => (progress >= 2 / 3 ? "final" : progress <= 1 / 3 ? "inicio" : "medio");

let passed = 0;
function test(name, fn) {
    fn();
    passed++;
    console.log(`  ok  ${name}`);
}

// ── 1. Pruebas unitarias ────────────────────────────────────────
console.log("Pruebas unitarias");
const medium = { syllables: 120, level: "Medium" };
const EXP = 120 * RP.base_ms_per_syllable * RP.level_factor.Medium;      // 21.8 s
const longHigh = { syllables: 200, level: "High" };
const EXP_LONG = 200 * RP.base_ms_per_syllable * RP.level_factor.High;   // 44.8 s

// Lee de arriba abajo durante ms (la zona sigue el avance).
function read(m, key, ms, info, from = 0) {
    for (let t = 0; t < ms; t += 100) m.tick(key, 100, zoneAt(from + t / ms), info);
}

test("lectura fluida (1.0 × esperado) no da señal", () => {
    const m = createReadingModel(RP);
    m.enter("p", 0);
    read(m, "p", EXP, medium);
    assert.strictEqual(m.signal("p", medium), null);
});

test("atascado: en un párrafo corto aparece a 1.5 × esperado", () => {
    const m = createReadingModel(RP);
    m.enter("p", 0);
    let fired = null;
    for (let t = 0; t < EXP * 2; t += 100) {
        m.tick("p", 100, "medio", medium);
        if (!fired && m.signal("p", medium)) fired = t + 100;
    }
    const expectedAt = Math.min(RP.stuck_ratio * EXP, EXP + RP.stuck_max_extra_ms);
    assert.ok(Math.abs(fired - expectedAt) <= 100, `disparó en ${fired}, esperado ${expectedAt}`);
});

test("atascado: en un párrafo largo, tope de esperado + 15 s", () => {
    const m = createReadingModel(RP);
    m.enter("p", 0);
    let fired = null;
    for (let t = 0; t < EXP_LONG * 2; t += 100) {
        m.tick("p", 100, "medio", longHigh);
        if (!fired && m.signal("p", longHigh)) fired = t + 100;
    }
    assert.ok(Math.abs(fired - (EXP_LONG + RP.stuck_max_extra_ms)) <= 100, `disparó en ${fired}`);
    assert.ok(fired < RP.stuck_ratio * EXP_LONG, "el tope adelanta la ayuda");
});

test("relectura al volver: leído, fuera > 5 s, vuelve", () => {
    const m = createReadingModel(RP);
    m.enter("p", 0);
    read(m, "p", EXP * 0.9, medium);
    m.leave("p", 20000, medium, false);
    assert.strictEqual(m.enter("p", 20000 + RP.revisit_gap_ms + 1000).event, "relectura");
    assert.strictEqual(m.signal("p", medium).type, "relectura");
});

test("relectura en el párrafo: tras leerlo vuelve al inicio sin salir", () => {
    const m = createReadingModel(RP);
    m.enter("p", 0);
    read(m, "p", EXP * 0.9, medium);
    assert.strictEqual(m.signal("p", medium), null);
    for (let t = 0; t < RP.reread_start_min_ms; t += 100) m.tick("p", 100, "inicio", medium);
    assert.strictEqual(m.signal("p", medium).type, "relectura_en_el_parrafo");
});

test("un salto breve al inicio (< 0.4 s) no cuenta como relectura", () => {
    const m = createReadingModel(RP);
    m.enter("p", 0);
    read(m, "p", EXP * 0.9, medium);
    m.tick("p", 100, "inicio", medium);
    m.tick("p", 100, "inicio", medium);
    m.tick("p", 100, "final", medium);
    assert.strictEqual(m.signal("p", medium), null);
});

test("volver al inicio ANTES de haberlo leído no cuenta", () => {
    const m = createReadingModel(RP);
    m.enter("p", 0);
    read(m, "p", EXP * 0.3, medium);
    for (let t = 0; t < 2000; t += 100) m.tick("p", 100, "inicio", medium);
    assert.strictEqual(m.signal("p", medium), null);
});

test("sin llegar al final no cuenta como leído (al volver se reinicia)", () => {
    const m = createReadingModel(RP);
    m.enter("p", 0);
    for (let t = 0; t < EXP * 0.9; t += 100) m.tick("p", 100, "medio", medium);
    m.leave("p", 20000, medium, false);
    assert.strictEqual(m.enter("p", 30000).event, "reinicio");
    assert.strictEqual(m.signal("p", medium), null);
});

test("salida corta (< 5 s): sigue sumando, misma lectura", () => {
    const m = createReadingModel(RP);
    m.enter("p", 0);
    for (let t = 0; t < 3000; t += 100) m.tick("p", 100, "medio", medium);
    m.leave("p", 3000, medium, false);
    const r = m.enter("p", 5000);
    assert.strictEqual(r.event, "continua");
    assert.strictEqual(r.accMs, 3000);
});

test("ritmo adaptativo: un lector rápido en párrafos fáciles baja su ritmo", () => {
    const m = createReadingModel(RP);
    const low = { syllables: 60, level: "Low" };
    let now = 0;
    for (let i = 0; i < 6; i++) {
        const readMs = 60 * RP.base_ms_per_syllable * 0.7;
        m.enter(`low${i}`, now);
        read(m, `low${i}`, readMs, low);
        now += readMs;
        m.leave(`low${i}`, now, low, false);
        now += 1000;
    }
    assert.ok(m.pace < RP.base_ms_per_syllable * 0.8, `ritmo ${m.pace.toFixed(0)}`);
    assert.ok(m.pace >= RP.base_ms_per_syllable * RP.pace_bounds[0]);
});

test("el ritmo no aprende de hojeos ni de párrafos con señal", () => {
    const m = createReadingModel(RP);
    const low = { syllables: 60, level: "Low" };
    m.enter("a", 0);
    read(m, "a", 1000, low);
    m.leave("a", 1000, low, false);
    m.enter("b", 2000);
    read(m, "b", 8000, low);
    m.leave("b", 10000, low, true);
    assert.strictEqual(m.pace, RP.base_ms_per_syllable);
});

test("llegar al final hojeando (poco tiempo) no cuenta como leído", () => {
    const m = createReadingModel(RP);
    m.enter("p", 0);
    read(m, "p", EXP * 0.2, medium);                 // hojea de arriba abajo en 20 % del tiempo
    assert.strictEqual(m.isReadComplete("p"), false);
    read(m, "p", EXP * 0.3, medium);                 // vuelve arriba y empieza a leer
    assert.strictEqual(m.signal("p", medium), null);
});

test("relectura en el párrafo: el tiempo sin fijación no cuenta", () => {
    const m = createReadingModel({ ...RP, reread_requires_fixation: true });
    m.enter("p", 0);
    read(m, "p", EXP * 0.9, medium);
    for (let t = 0; t < 3000; t += 100) m.tick("p", 100, "inicio", medium, false);
    assert.strictEqual(m.signal("p", medium), null);
    for (let t = 0; t < RP.reread_start_min_ms; t += 100) m.tick("p", 100, "inicio", medium, true);
    assert.strictEqual(m.signal("p", medium).type, "relectura_en_el_parrafo");
});

test("segundo nivel: tras la ayuda, la relectura en el párrafo exige volver a llegar al final", () => {
    const m = createReadingModel(RP);
    m.enter("p", 0);
    read(m, "p", EXP * 0.9, medium);
    for (let t = 0; t < RP.reread_start_min_ms; t += 100) m.tick("p", 100, "inicio", medium, true);
    assert.strictEqual(m.signal("p", medium).type, "relectura_en_el_parrafo");
    m.rearm("p");                                             // se mostró la primera ayuda
    assert.strictEqual(m.signal("p", medium), null);
    for (let t = 0; t < 3000; t += 100) m.tick("p", 100, "inicio", medium, true);
    assert.strictEqual(m.signal("p", medium), null, "seguir arriba no basta");
    read(m, "p", EXP * 0.6, medium);                           // vuelve a leer hasta el final
    for (let t = 0; t < RP.reread_start_min_ms; t += 100) m.tick("p", 100, "inicio", medium, true);
    assert.strictEqual(m.signal("p", medium).type, "relectura_en_el_parrafo");
});

test("segundo nivel: atascado se mide desde la ayuda", () => {
    const m = createReadingModel(RP);
    m.enter("p", 0);
    for (let t = 0; t < EXP * 1.6; t += 100) m.tick("p", 100, "medio", medium);
    assert.strictEqual(m.signal("p", medium).type, "atascado");
    m.rearm("p");
    assert.strictEqual(m.signal("p", medium), null);
    for (let t = 0; t < EXP * RP.level2_extra_fraction - 200; t += 100) m.tick("p", 100, "medio", medium);
    assert.strictEqual(m.signal("p", medium), null);
    for (let t = 0; t < 300; t += 100) m.tick("p", 100, "medio", medium);
    assert.strictEqual(m.signal("p", medium).type, "atascado");
});

test("segundo nivel: releer una vez completo a ritmo normal no lo dispara", () => {
    // Releer tras recibir la definición puede ser solo integrarla. A ritmo
    // normal, leer un párrafo Medium toma 1/1.3 del tiempo esperado.
    const m = createReadingModel(RP);
    m.enter("p", 0);
    for (let t = 0; t < EXP * 1.6; t += 100) m.tick("p", 100, "medio", medium);
    m.rearm("p");                                             // primera ayuda
    read(m, "p", EXP / RP.level_factor.Medium, medium);        // una relectura completa
    assert.strictEqual(m.signal("p", medium), null);
});

test("segundo nivel: volver después de la ayuda cuenta como relectura", () => {
    const m = createReadingModel(RP);
    m.enter("p", 0);
    read(m, "p", EXP * 0.9, medium);
    m.rearm("p");
    m.leave("p", 30000, medium, true);
    assert.strictEqual(m.enter("p", 30000 + RP.revisit_gap_ms + 1000).event, "relectura");
    assert.strictEqual(m.signal("p", medium).type, "relectura");
});

// ── 2. Simulación con lectores simulados ─────────────────────────
function rng(seed) {
    let s = seed >>> 0;
    return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}
// Lentitud "real" por nivel (distinta a propósito de los factores del modelo)
// y cuánto se queda quien se traba. Exigente: se traba de forma menos marcada
// y los textos difíciles se leen más lento de lo que el modelo supone.
const SCENARIOS = {
    base:     { slowdown: { Low: 1.0, Medium: 1.25, High: 1.5 }, stay: 2.2 },
    exigente: { slowdown: { Low: 1.0, Medium: 1.4,  High: 1.9 }, stay: 1.6 },
};
const ANALYSIS_LATENCY_MS = { Low: 0, Medium: 3000, High: 3000 };

// Conductas de quien ENTIENDE: "revisa" (vuelve 1 s al inicio a comprobar un
// dato) y "hojea" (primero recorre el párrafo rápido hasta abajo y luego lo
// lee con calma). Quien SE TRABA alterna: se queda, relee volviendo después,
// o relee dentro del párrafo (hasta 3 lecturas completas seguidas).
// skipFacil: empieza directo en intermedio (su ritmo no se adapta antes).
const PROFILES = [
    { name: "entiende, rápido (0.7×)",   pace: 0.7, struggles: false },
    { name: "entiende, promedio",         pace: 1.0, struggles: false },
    { name: "entiende, lento (1.4×)",     pace: 1.4, struggles: false },
    { name: "entiende pero revisa",       pace: 1.0, struggles: false, habit: "revisa" },
    { name: "entiende, hojea y luego lee", pace: 1.0, struggles: false, habit: "hojea" },
    { name: "se traba, rápido (0.7×)",   pace: 0.7, struggles: true },
    { name: "se traba, promedio",         pace: 1.0, struggles: true },
    { name: "se traba, lento (1.4×)",     pace: 1.4, struggles: true },
    { name: "rápido sin pasar por fácil, se traba", pace: 0.7, struggles: true, skipFacil: true },
    { name: "rápido sin pasar por fácil, entiende", pace: 0.7, struggles: false, skipFacil: true },
];

// Propuesta del 2026-10-11 para acortar los tiempos, separada en partes.
const PROPOSED = { ...RP, read_fraction: 0.4, level_factor: { Low: 1.0, Medium: 1.15, High: 1.3 }, stuck_ratio: 1.3 };
const RULES = [
    ["contenido", "Regla anterior (solo contenido, tiempo fijo)", null],
    ["v2", "Conducta v2 (tiempos actuales)", RP],
    ["v3a", "v3a: solo 'leído' al 40 %", { ...RP, read_fraction: 0.4 }],
    ["v3b", "v3b: 'leído' 40 % + factores 1.15/1.3", { ...RP, read_fraction: 0.4, level_factor: PROPOSED.level_factor }],
    ["v3", "v3: propuesta completa (+ atascado 1.3×)", PROPOSED],
];

function simulate(profile, rule, policy, seed, scenario) {
    const rand = rng(seed);
    const m = createReadingModel(policy || RP);
    let now = 0, k = 0, c = 0;
    const out = { innecesarias: 0, noTrabados: 0, cubiertas: 0, trabados: 0, demoras: [], lecturas: [] };
    for (const b of BLOCKS) {
        if (profile.skipFacil && b.page === "facil") continue;
        const key = `${b.page}:${b.el}`;
        const eligible = b.level !== "Low";
        const struggles = profile.struggles && eligible;
        const readMs = b.syllables * RP.base_ms_per_syllable * profile.pace
            * scenario.slowdown[b.level] * (0.85 + 0.3 * rand());
        const mode = struggles ? (scenario.stayOnly ? "queda" : ["queda", "relee_fuera", "relee_dentro"][k++ % 3])
            : (profile.habit && eligible && c++ % 3 === 0 ? profile.habit : "normal");
        const info = { syllables: b.syllables, level: b.level };
        let helpedAt = null;
        let visitT = 0;

        const gaze = (durationMs, zoneFn) => {
            for (let t = 0; t < durationMs; t += 100) {
                m.tick(key, 100, zoneFn(t / durationMs), info, true);
                visitT += 100;
                now += 100;
                if (helpedAt !== null || !eligible) continue;
                if (rule === "contenido") {
                    const minDwell = POLICY.help[b.level].min_dwell_ms;
                    if (visitT >= Math.max(minDwell, ANALYSIS_LATENCY_MS[b.level])) helpedAt = now;
                } else if (visitT >= ANALYSIS_LATENCY_MS[b.level] && m.signal(key, info)) {
                    helpedAt = now;
                }
            }
        };
        const blockStart = now;
        m.enter(key, now);
        if (mode === "queda") {
            gaze(readMs * scenario.stay, p => zoneAt(Math.min(p * scenario.stay, 0.6)));
        } else if (mode === "relee_dentro") {
            for (let pass = 0; pass < 3 && helpedAt === null; pass++) gaze(readMs, zoneAt);
        } else if (mode === "hojea") {
            gaze(readMs * 0.25, zoneAt);                           // recorre rápido hasta abajo
            gaze(readMs, zoneAt);                                  // y luego lo lee desde arriba
        } else {
            gaze(readMs, zoneAt);
            if (mode === "revisa") gaze(1000, () => "inicio");
        }
        m.leave(key, now, info, helpedAt !== null);
        if (mode === "relee_fuera") {
            now += 8000;
            visitT = 0;
            m.enter(key, now);
            gaze(readMs * 0.5, zoneAt);
            m.leave(key, now, info, true);
        }
        if (helpedAt !== null && struggles) {
            out.demoras.push(helpedAt - blockStart);
            if (mode === "relee_dentro") out.lecturas.push((helpedAt - blockStart) / readMs);
        }
        now += 1500;
        if (!eligible) continue;
        if (struggles) { out.trabados++; if (helpedAt !== null) out.cubiertas++; }
        else { out.noTrabados++; if (helpedAt !== null) out.innecesarias++; }
    }
    return out;
}

function aggregate(profile, rule, policy, scenario) {
    const acc = { innecesarias: 0, noTrabados: 0, cubiertas: 0, trabados: 0, demoras: [], lecturas: [] };
    for (let seed = 1; seed <= 20; seed++) {
        const r = simulate(profile, rule, policy, seed * 7919, scenario);
        for (const key of ["innecesarias", "noTrabados", "cubiertas", "trabados"]) acc[key] += r[key];
        acc.demoras.push(...r.demoras);
        acc.lecturas.push(...r.lecturas);
    }
    return acc;
}
const mean = xs => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
const pct = (a, b) => (b ? `${Math.round(100 * a / b)} %` : "—");

const summary = {};
for (const [scName, scenario] of Object.entries(SCENARIOS)) {
    console.log(`\nSimulación [escenario ${scName}]: párrafos reales, 20 semillas por perfil`);
    for (const [rule, label, policy] of RULES) {
        console.log(`\n  ${label}`);
        for (const prof of PROFILES) {
            const acc = aggregate(prof, rule, policy, scenario);
            const d = mean(acc.demoras), l = mean(acc.lecturas);
            summary[`${scName}|${rule}|${prof.name}`] = {
                innecesarias: acc.noTrabados ? acc.innecesarias / acc.noTrabados : null,
                cobertura: acc.trabados ? acc.cubiertas / acc.trabados : null,
                demora_s: d === null ? null : d / 1000, lecturas_hasta_ayuda: l };
            console.log(`    ${prof.name.padEnd(38)} innecesaria ${pct(acc.innecesarias, acc.noTrabados).padStart(5)}`
                + ` | cobertura ${pct(acc.cubiertas, acc.trabados).padStart(5)}`
                + ` | demora ${d === null ? "   —  " : (d / 1000).toFixed(1).padStart(5) + " s"}`
                + ` | lecturas hasta la ayuda (relee dentro) ${l === null ? "—" : l.toFixed(2)}`);
        }
    }
}

fs.writeFileSync(path.join(ROOT, "evaluation/results/simulacion_conducta.json"),
    JSON.stringify({ fecha: new Date().toISOString(), politica: RP, propuesta: PROPOSED, resumen: summary }, null, 1));
console.log(`\n${passed} pruebas unitarias OK · simulación guardada en evaluation/results/simulacion_conducta.json`);
