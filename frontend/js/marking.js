// ═══════════════════════════════════════════════════════════════
// "Marca lo que te costó entender" (solo en sesión experimental).
// Al terminar cada página, el participante marca con clics los párrafos,
// tablas o figuras que le costaron. Es la referencia ("verdad") para medir si
// la ayuda llegó a quien la necesitaba: acierto y cobertura en
// evaluation/analyze_sessions.py. Mientras marca, el seguimiento se pausa.
// Orden de las páginas: fácil → intermedio → avanzado → índice.
// ═══════════════════════════════════════════════════════════════
(function () {
    if (!ExperimentSession.active) return;

    // Orden de lectura de esta sesión (aleatorio, desde index.html).
    const ORDER = ExperimentSession.session?.order || ["facil", "intermedio", "avanzado"];
    const nextPage = ORDER[ORDER.indexOf(ExperimentSession.pageKey) + 1];
    const nextUrl = nextPage ? `${nextPage}.html` : "index.html";

    const startButton = document.createElement("button");
    startButton.type = "button";
    startButton.className = "btn-primary marking-start";
    startButton.textContent = "Terminé esta página →";
    document.body.appendChild(startButton);

    function candidates() {
        return [...document.querySelectorAll("p,li,table,img,svg")]
            .filter(el => !el.closest(".debug-panel") && !el.closest(".marking-bar")
                && !el.closest(".marking-start") && extractContent(el));
    }

    function toggle(event) {
        event.preventDefault();
        event.stopPropagation();
        event.currentTarget.classList.toggle("is-marked");
    }

    // Durante el marcado, los enlaces no navegan.
    document.addEventListener("click", event => {
        if (window.markingMode && event.target.closest("a") && !event.target.closest(".marking-bar")) {
            event.preventDefault();
        }
    }, true);

    // Hoja del Excel que corresponde a esta página (nombres neutros: no
    // revelan el nivel; deben coincidir con evaluation/crear_cuestionarios_excel.py).
    const SHEETS = {"facil": "Lectura - El hielo del planeta", "intermedio": "Lectura - Causas y evidencia", "avanzado": "Lectura - Forzamiento radiativo"};

    startButton.addEventListener("click", () => {
        // Termina la lectura: se cierra la visita en curso, se pausa el
        // seguimiento y se registra cuánto duró la lectura (sin la pausa).
        logElementExit();
        currentObservedElement = null;
        window.markingMode = true;
        hideTooltip();
        startButton.remove();
        ExperimentSession.log("reading_end", { duration_ms: Date.now() - pageEnteredAt });
        showPause();
    });

    // Pausa entre páginas (2026-10-20): tapa el texto para responder el
    // cuestionario de la página (la comprensión se responde SIN ver el texto)
    // y descansar. Mientras dura NO se registra nada (ni la mirada); solo el
    // inicio y fin de la pausa, para conocer su duración.
    function showPause() {
        window.recordingPaused = true;
        const pauseStart = Date.now();
        ExperimentSession.log("pause_start", {});
        const position = ORDER.indexOf(ExperimentSession.pageKey) + 1;
        const overlay = document.createElement("div");
        overlay.className = "pause-overlay";
        overlay.innerHTML = `
            <div class="pause-card">
                <p class="pause-step">Página web ${position} de ${ORDER.length} terminada</p>
                <h2>Pausa</h2>
                <p>Ahora responde en el Excel la hoja
                   <strong>«${SHEETS[ExperimentSession.pageKey] || ExperimentSession.pageKey}»</strong>
                   (Parte A y Parte B), sin volver a la página web. Puedes descansar el tiempo que necesites.</p>
                <p class="pause-note">Mientras ves esta pantalla, el sistema no registra nada.</p>
                <button type="button" class="btn-primary pause-done">Listo, continuar</button>
            </div>`;
        document.body.appendChild(overlay);
        overlay.querySelector(".pause-done").addEventListener("click", () => {
            ExperimentSession.log("pause_end", { duration_ms: Date.now() - pauseStart });
            window.recordingPaused = false;
            overlay.remove();
            startMarking();
        });
    }

    function startMarking() {
        ExperimentSession.log("marking_start", {});

        document.body.classList.add("marking-mode");
        const list = candidates();
        list.forEach(el => {
            el.classList.add("mark-candidate");
            el.addEventListener("click", toggle, true);
        });

        const bar = document.createElement("div");
        bar.className = "marking-bar";
        bar.innerHTML = `<span>Haz clic en los párrafos, tablas o figuras que te <strong>costó entender</strong>
            (puedes no marcar ninguno). Luego pulsa Continuar.</span>`;
        const done = document.createElement("button");
        done.type = "button";
        done.className = "btn-primary";
        done.textContent = "Continuar";
        done.addEventListener("click", () => {
            const marked = list.filter(el => el.classList.contains("is-marked")).map(elementId);
            ExperimentSession.log("difficulty_marks", { els: marked, count: marked.length, candidates: list.length });
            if (!nextPage) ExperimentSession.save({ ...ExperimentSession.session, finished: true });
            window.location.href = nextUrl;   // pagehide envía el registro
        });
        bar.appendChild(done);
        document.body.appendChild(bar);
    }
})();
