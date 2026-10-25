// ═══════════════════════════════════════════════════════════════
// Modelo de lectura: decide por la conducta si la persona necesita la ayuda.
// Reglas: REGLAS_DEL_SISTEMA.md §4; parámetros: decision_engine.READING_POLICY.
//   atascado                 tiempo >= stuck_ratio × esperado (tope: + stuck_max_extra_ms)
//   relectura                vuelve tras haberlo leído y salir > revisit_gap_ms
//   relectura_en_el_parrafo  ya leído, fijaciones >= reread_start_min_ms en el primer tercio
// Tiempo esperado = sílabas × ritmo × factor del nivel. El ritmo aprende de
// cualquier lectura completa y sin señales (mediana; subir limitado).
// Tras la primera ayuda, rearm() hace que las señales pidan el segundo nivel.
// Módulo puro: lo usa gaze.js y lo prueba tests/test_reading_model.js.
// ═══════════════════════════════════════════════════════════════
(function (root) {
    const median = xs => {
        const s = [...xs].sort((a, b) => a - b);
        const m = Math.floor(s.length / 2);
        return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
    };

    // initial: ritmo aprendido en otra página ({pace, samples} o solo el número).
    function createReadingModel(policy, initial) {
        const p = policy;
        const base = p.base_ms_per_syllable;
        const clampPace = v => Math.min(Math.max(v, base * p.pace_bounds[0]), base * p.pace_bounds[1]);
        let pace = base;                 // ms por sílaba de esta persona
        let samples = [];                // últimas medidas (ms/sílaba, normalizadas por nivel)
        const initialPace = typeof initial === "object" && initial !== null ? initial.pace : initial;
        if (Number.isFinite(initialPace)) pace = clampPace(initialPace);
        if (Array.isArray(initial?.samples)) samples = initial.samples.filter(Number.isFinite).slice(-(p.pace_window || 5));
        const states = new Map();        // clave del elemento -> estado

        function stateOf(key) {
            let st = states.get(key);
            if (!st) {
                st = { accMs: 0, reachedEnd: false, readComplete: false,
                       lastLeftAt: null, revisitPending: false, paceUsed: false, signaled: false,
                       startRunMs: 0, internalReread: false,
                       helpAcc: null, needsEndAgain: false };
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
            if (zone === "final") {
                st.reachedEnd = true;
                st.needsEndAgain = false;
            }
            const expected = expectedMs(info);
            if (expected && !st.readComplete && zone === "final"
                && st.accMs >= p.read_fraction * expected) {
                st.readComplete = true;
            }
            // Ya leído y vuelve al inicio: suma solo el tiempo con fijación.
            if (st.readComplete && !st.needsEndAgain && zone === "inicio") {
                if (onFixation || !p.reread_requires_fixation) st.startRunMs += dtMs;
                if (st.startRunMs >= p.reread_start_min_ms) st.internalReread = true;
            } else {
                st.startRunMs = 0;
            }
        }

        // ¿Hay señal? null si no o si no se conocen las sílabas.
        function signal(key, info) {
            const st = stateOf(key);
            const expected = expectedMs(info);
            if (!expected) return null;
            const ratio = st.accMs / expected;
            // Atascado: stuck_ratio × esperado, como máximo esperado + stuck_max_extra_ms.
            const threshold = st.helpAcc !== null
                ? st.helpAcc + p.level2_extra_fraction * expected
                : p.stuck_max_extra_ms
                    ? Math.min(p.stuck_ratio * expected, expected + p.stuck_max_extra_ms)
                    : p.stuck_ratio * expected;
            if (st.revisitPending) return { type: "relectura", ratio, expected, accMs: st.accMs };
            if (st.internalReread) return { type: "relectura_en_el_parrafo", ratio, expected, accMs: st.accMs };
            if (st.accMs >= threshold) return { type: "atascado", ratio, expected, accMs: st.accMs };
            return null;
        }

        // Al salir: si fue una lectura completa, razonable y sin señales, el ritmo aprende.
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
            const learnable = info && expected && !hadSignal && !st.signaled && !st.paceUsed
                && (p.pace_from_all_levels || info.level === "Low")
                && st.reachedEnd && info.syllables >= p.pace_min_syllables
                && st.accMs >= p.pace_min_fraction * expected
                && st.accMs <= p.pace_max_fraction * expected;
            if (hadSignal) st.signaled = true;
            if (learnable) {
                const old = pace;
                let observed;
                if (p.pace_from_all_levels) {
                    // Medida normalizada: lo que le habría tomado si fuera Low.
                    observed = st.accMs / info.syllables / (p.level_factor[info.level] ?? 1);
                    samples.push(observed);
                    if (samples.length > p.pace_window) samples.shift();
                    const pool = samples.length < p.pace_prior_until ? [base, ...samples] : samples;
                    pace = clampPace(Math.min(median(pool), old * (1 + p.pace_max_increase)));
                } else {
                    observed = st.accMs / info.syllables;
                    pace = clampPace(old + p.pace_alpha * (observed - old));
                }
                st.paceUsed = true;
                paceUpdate = { old, new: pace, observed, samples: samples.length };
            }
            return { snapshot, paceUpdate };
        }

        // Tras la primera ayuda: las señales siguientes piden el segundo nivel.
        function rearm(key) {
            const st = stateOf(key);
            st.helpAcc = st.accMs;
            st.signaled = true;          // ya no sirve para aprender el ritmo
            st.needsEndAgain = true;
            st.internalReread = false;
            st.startRunMs = 0;
            st.revisitPending = false;
        }

        return {
            enter, tick, signal, leave, expectedMs, rearm,
            get pace() { return pace; },
            // Para guardarlo entre páginas (gaze.js, sessionStorage).
            get paceState() { return { pace, samples: [...samples] }; },
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
