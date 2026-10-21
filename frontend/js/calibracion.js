// ═══════════════════════════════════════════════════════════════
// Comprobación de la mirada (5 puntos) al inicio de la sesión (2026-10-20).
// Después de la calibración del Tobii (Tobii Experience), la persona mira 5
// puntos; se compara dónde estaba cada punto con dónde llegó la mirada y se
// ajusta una corrección por eje (gaze_mapping.fitCorrection). La corrección
// queda guardada para el resto de la sesión (gaze.js la aplica) y el error
// medido se registra ("gaze_check") para el criterio de exclusión.
// Con mouse no hace falta: pasa directo a la primera página.
// ═══════════════════════════════════════════════════════════════
(function () {
    const CONFIG_URL = "http://127.0.0.1:5000/config";
    const GAZE_WS_URL = "ws://127.0.0.1:5600";
    const SETTLE_MS = 800;       // tiempo para que la mirada llegue al punto
    const COLLECT_MS = 1500;     // muestras que se usan por punto
    const MIN_SAMPLES = 15;      // por punto (el Tobii envía ~90 por segundo)
    const GOOD_ERROR_PX = 60;    // ≈ dispersión del I-DT: más que esto, revisar la calibración
    const TARGETS = [[0.1, 0.12], [0.9, 0.12], [0.5, 0.5], [0.1, 0.88], [0.9, 0.88]];

    const session = (() => {
        try { return JSON.parse(sessionStorage.getItem(SESSION_STORAGE_KEY)); } catch (e) { return null; }
    })();
    const order = session?.order || ["facil", "intermedio", "avanzado"];
    const nextUrl = `${order[0]}.html`;
    const dot = document.getElementById("calib-dot");
    const text = document.getElementById("calib-text");
    const note = document.getElementById("calib-note");
    const actions = document.getElementById("calib-actions");
    const panel = document.getElementById("calib-panel");

    let latest = null;          // último punto válido (sin corrección), en la página
    let collecting = null;      // muestras del punto en curso

    function log(type, data) {
        if (session) ExperimentSession.log(type, data);
    }

    function button(label, primary, onClick) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = primary ? "btn-primary" : "btn-outline";
        b.textContent = label;
        b.addEventListener("click", onClick);
        actions.appendChild(b);
    }

    function goNext() {
        ExperimentSession.flush().finally(() => { window.location.href = nextUrl; });
    }

    function connect() {
        const ws = new WebSocket(GAZE_WS_URL);
        ws.onmessage = event => {
            let data;
            try { data = JSON.parse(event.data); } catch (e) { return; }
            if (!data?.valid || typeof data.nx !== "number") return;
            latest = GazeMapping.normalizedToClient(data.nx, data.ny, window);
            if (collecting) collecting.push(latest);
        };
        ws.onclose = () => setTimeout(connect, 1500);
    }

    const wait = ms => new Promise(r => setTimeout(r, ms));

    async function run() {
        actions.innerHTML = "";
        panel.style.display = "none";
        const points = [];
        for (const [fx, fy] of TARGETS) {
            const target = { x: fx * window.innerWidth, y: fy * window.innerHeight };
            dot.style.left = `${target.x}px`;
            dot.style.top = `${target.y}px`;
            dot.style.display = "block";
            await wait(SETTLE_MS);
            collecting = [];
            await wait(COLLECT_MS);
            const samples = collecting;
            collecting = null;
            if (samples.length < MIN_SAMPLES) {
                dot.style.display = "none";
                return showResult(null, `No se detectó la mirada en el punto ${points.length + 1} `
                    + `(${samples.length} muestras). Revisa que el Tobii esté conectado y vea los ojos.`);
            }
            points.push({ target, measured: { x: GazeMapping.median(samples.map(s => s.x)),
                                              y: GazeMapping.median(samples.map(s => s.y)) },
                          samples: samples.length });
        }
        dot.style.display = "none";
        showResult(GazeMapping.fitCorrection(points), null, points);
    }

    function showResult(fit, problem, points) {
        panel.style.display = "flex";
        actions.innerHTML = "";
        if (!fit) {
            text.textContent = problem;
            note.textContent = "";
            button("Repetir", true, run);
            return;
        }
        GazeMapping.saveCorrection(sessionStorage, fit.correction);
        log("gaze_check", { ...fit, points, screen: [screen.width, screen.height],
                            window: [innerWidth, innerHeight], origin: GazeMapping.contentOrigin(window) });
        const ok = fit.errorAfterPx <= GOOD_ERROR_PX;
        text.innerHTML = ok
            ? "Listo. La mirada se detecta bien."
            : "La mirada se detecta con bastante error. Conviene repetir la calibración del Tobii (Tobii Experience) y esta comprobación.";
        note.textContent = `Para el investigador: error medio ${fit.errorBeforePx} px sin corregir → `
            + `${fit.errorAfterPx} px corregido (aceptable: ≤ ${GOOD_ERROR_PX} px).`;
        button("Repetir", !ok, run);
        button("Continuar", ok, goNext);
    }

    fetch(CONFIG_URL).then(r => r.json()).catch(() => ({})).then(config => {
        if (config.input_source !== "tobii") {
            // Con mouse no hay nada que corregir.
            GazeMapping.saveCorrection(sessionStorage, null);
            window.location.replace(nextUrl);
            return;
        }
        connect();
        document.getElementById("calib-start").addEventListener("click", run);
    });
})();
