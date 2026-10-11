// ═══════════════════════════════════════════════════════════════
// Modelo de lectura: decide, por la CONDUCTA de la persona, si necesita la
// ayuda que el contenido tiene disponible. Reglas en REGLAS_DEL_SISTEMA.md;
// parámetros en backend/analyzers/decision_engine.py (READING_POLICY).
//
// Señales (por párrafo de texto corrido):
//   - "atascado": tiempo acumulado >= stuck_ratio × tiempo esperado, y a más
//     tardar esperado + stuck_max_extra_ms (en párrafos largos 1.5× era casi
//     un minuto).
//   - "relectura": vuelve tras haberlo leído (>= read_fraction del tiempo
//     esperado y la mirada llegó al final del párrafo) y haber salido más de
//     revisit_gap_ms.
//   - "relectura_en_el_parrafo": ya lo leyó y, sin salir, la mirada vuelve al
//     primer tercio del párrafo con FIJACIONES que suman >= reread_start_min_ms
//     (una regresión). Si reread_requires_fixation es false, cuenta cualquier
//     mirada ahí (por si el Tobii detecta pocas fijaciones al leer).
// "Lo leyó" = la mirada está en el último tercio cuando ya acumuló
// >= read_fraction del tiempo esperado (llegar al final hojeando no cuenta).
// La posición de la mirada dentro del párrafo llega como zona vertical:
// "inicio" (primer tercio), "medio" o "final" (último tercio).
// Tiempo esperado = sílabas × ritmo (ms/sílaba) × factor del nivel.
// El ritmo arranca en el promedio general y se adapta a la persona con los
// párrafos fáciles que lee (sin medición previa).
//
// Es un módulo puro (sin DOM): gaze.js lo usa en el navegador y
// tests/test_reading_model.js lo prueba con escenarios simulados en Node.
// ═══════════════════════════════════════════════════════════════
(function (root) {
    // initialPace: ritmo ya aprendido en otra página de la misma visita.
    function createReadingModel(policy, initialPace) {
        const p = policy;
        const base = p.base_ms_per_syllable;
        let pace = base;                 // ms por sílaba de esta persona
        if (Number.isFinite(initialPace)) {
            pace = Math.min(Math.max(initialPace, base * p.pace_bounds[0]), base * p.pace_bounds[1]);
        }
        const states = new Map();        // clave del elemento -> estado

        function stateOf(key) {
            let st = states.get(key);
            if (!st) {
                st = { accMs: 0, reachedEnd: false, readComplete: false,
                       lastLeftAt: null, revisitPending: false, paceUsed: false,
                       startRunMs: 0, internalReread: false };
                states.set(key, st);
            }
            return st;
        }

        function expectedMs(info) {
            if (!info || !info.syllables) return null;
            return info.syllables * pace * (p.level_factor[info.level] ?? 1);
        }

        // La mirada entra al elemento. Devuelve qué pasó con la lectura previa.
        function enter(key, now) {
            const st = stateOf(key);
            let event = "primera";
            if (st.lastLeftAt !== null) {
                const gap = now - st.lastLeftAt;
                if (gap <= p.revisit_gap_ms) {
                    event = "continua";          // salida corta: misma lectura
                } else if (st.readComplete) {
                    st.revisitPending = true;    // lo había leído y vuelve
                    event = "relectura";
                } else {
                    st.accMs = 0;                // solo había mirado el inicio
                    st.reachedEnd = false;
                    event = "reinicio";
                }
            }
            return { event, accMs: st.accMs };
        }

        // Cada tick con la mirada en el elemento. zone: "inicio" | "medio" |
        // "final"; onFixation: la mirada forma una fijación (I-DT) en este tick.
        function tick(key, dtMs, zone, info, onFixation = true) {
            const st = stateOf(key);
            st.accMs += dtMs;
            if (zone === "final") st.reachedEnd = true;
            const expected = expectedMs(info);
            if (expected && !st.readComplete && zone === "final"
                && st.accMs >= p.read_fraction * expected) {
                st.readComplete = true;
            }
            // Ya lo leyó y vuelve al inicio sin salir: suma el tiempo fijado
            // ahí (un salto breve o sin fijación puede ser ruido del Tobii).
            if (st.readComplete && zone === "inicio") {
                if (onFixation || !p.reread_requires_fixation) st.startRunMs += dtMs;
                if (st.startRunMs >= p.reread_start_min_ms) st.internalReread = true;
            } else {
                st.startRunMs = 0;
            }
        }

        // ¿Hay señal de que necesita ayuda? (null si no, o si aún no se
        // conocen las sílabas: llegan con el análisis del backend).
        function signal(key, info) {
            const st = stateOf(key);
            const expected = expectedMs(info);
            if (!expected) return null;
            const ratio = st.accMs / expected;
            // Umbral de "atascado": stuck_ratio × esperado; si se define
            // stuck_max_extra_ms, a más tardar esperado + ese margen (en
            // párrafos largos 1.5× puede ser casi un minuto).
            const threshold = p.stuck_max_extra_ms
                ? Math.min(p.stuck_ratio * expected, expected + p.stuck_max_extra_ms)
                : p.stuck_ratio * expected;
            if (st.revisitPending) return { type: "relectura", ratio, expected, accMs: st.accMs };
            if (st.internalReread) return { type: "relectura_en_el_parrafo", ratio, expected, accMs: st.accMs };
            if (st.accMs >= threshold) return { type: "atascado", ratio, expected, accMs: st.accMs };
            return null;
        }

        // La mirada sale del elemento. Si fue la lectura de un párrafo fácil,
        // completa y sin señales, el ritmo se acerca al observado.
        function leave(key, now, info, hadSignal) {
            const st = stateOf(key);
            st.lastLeftAt = now;
            st.revisitPending = false;
            st.internalReread = false;
            st.startRunMs = 0;
            const snapshot = { accMs: st.accMs, expected: expectedMs(info),
                               readComplete: st.readComplete, reachedEnd: st.reachedEnd, pace };
            let paceUpdate = null;
            const expected = snapshot.expected;
            if (info && info.level === "Low" && expected && !hadSignal && !st.paceUsed
                && st.reachedEnd && info.syllables >= p.pace_min_syllables
                && st.accMs >= p.pace_min_fraction * expected
                && st.accMs <= p.pace_max_fraction * expected) {
                const observed = st.accMs / info.syllables;
                const old = pace;
                pace = old + p.pace_alpha * (observed - old);
                pace = Math.min(Math.max(pace, base * p.pace_bounds[0]), base * p.pace_bounds[1]);
                st.paceUsed = true;
                paceUpdate = { old, new: pace, observed };
            }
            return { snapshot, paceUpdate };
        }

        return {
            enter, tick, signal, leave, expectedMs,
            get pace() { return pace; },
            isReadComplete: key => stateOf(key).readComplete,
            accMs: key => stateOf(key).accMs
        };
    }

    if (typeof module !== "undefined" && module.exports) {
        module.exports = { createReadingModel };
    } else {
        root.createReadingModel = createReadingModel;
    }
})(typeof window !== "undefined" ? window : globalThis);
