// ═══════════════════════════════════════════════════════════════
// Fin de cada página (solo en sesión): leer → "Terminé" → marcar lo que costó
// (referencia para acierto y cobertura en analyze_sessions.py) → descanso
// cronometrado sin interacción → siguiente página. Tras la última: cierre.
// ═══════════════════════════════════════════════════════════════
(function () {
    if (!ExperimentSession.active) return;

    // Orden de lectura de la sesión (sorteo previo).
    const ORDER = ExperimentSession.session?.order || ["facil", "intermedio", "avanzado"];
    const nextPage = ORDER[ORDER.indexOf(ExperimentSession.pageKey) + 1];
    const nextUrl = nextPage ? ExperimentSession.pageUrl(nextPage) : "index.html";
    // Descanso entre páginas (cada lectura dura ~2–5 min). Ver README.
    const PAUSE_MS = 1.5 * 60 * 1000;

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

    // Tiempo máximo de lectura por página (2026-10-28): al cumplirse, pasa lo mismo
    // que con "Terminé esta página". Sin aviso previo (decisión del 2026-10-28).
    const READING_LIMIT_MS = { facil: 4, intermedio: 7, avanzado: 10 }[ExperimentSession.pageKey] * 60 * 1000;
    let readingFinished = false;

    function finishReading(timedOut) {
        if (readingFinished) return;
        readingFinished = true;
        clearTimeout(limitTimer);
        // Fin de la lectura: se cierra la visita y se registra su duración.
        logElementExit();
        currentObservedElement = null;
        window.markingMode = true;
        hideTooltip();
        startButton.remove();
        ExperimentSession.log("reading_end", { duration_ms: Date.now() - pageEnteredAt, timed_out: timedOut,
                                               limit_ms: READING_LIMIT_MS });
        startMarking(timedOut);
    }

    startButton.addEventListener("click", () => finishReading(false));
    const limitTimer = setTimeout(() => finishReading(true), READING_LIMIT_MS - (Date.now() - pageEnteredAt));

    // Descanso: tapa el texto, no pide nada y pasa sola a la siguiente página.
    // No se registra la mirada; solo su inicio y fin.
    function showPause() {
        window.recordingPaused = true;
        const pauseStart = Date.now();
        ExperimentSession.log("pause_start", { planned_ms: PAUSE_MS });
        const overlay = document.createElement("div");
        overlay.className = "pause-overlay";
        overlay.innerHTML = `
            <div class="pause-card">
                <h2>Descanso</h2>
                <p>Descansa la vista: puedes cerrar los ojos o mirar a lo lejos.
                   No tienes que hacer nada. La siguiente página web empezará sola.</p>
                <div class="pause-row">
                    <p class="pause-countdown" aria-live="off"></p>
                    <button type="button" class="btn-outline pause-skip">Saltar descanso</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);
        const countdown = overlay.querySelector(".pause-countdown");
        // skipped: la persona pulsó "Saltar descanso" antes de que acabara el tiempo
        const finish = skipped => {
            clearInterval(timer);
            ExperimentSession.log("pause_end", { duration_ms: Date.now() - pauseStart, skipped });
            window.location.href = nextUrl;   // pagehide envía el registro
        };
        const tick = () => {
            const left = Math.max(0, PAUSE_MS - (Date.now() - pauseStart));
            const s = Math.ceil(left / 1000);
            countdown.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
            if (left === 0) finish(false);
        };
        const timer = setInterval(tick, 250);
        overlay.querySelector(".pause-skip").addEventListener("click", () => finish(true), { once: true });
        tick();
    }

    function startMarking(timedOut) {
        ExperimentSession.log("marking_start", {});

        document.body.classList.add("marking-mode");
        const list = candidates();
        list.forEach(el => {
            el.classList.add("mark-candidate");
            el.addEventListener("click", toggle, true);
        });

        const bar = document.createElement("div");
        bar.className = "marking-bar";
        bar.innerHTML = `<span>${timedOut ? "<strong>Se acabó el tiempo de esta página.</strong> " : ""}Haz clic en los párrafos, tablas o figuras que te <strong>costó entender</strong>
            (puedes no marcar ninguno). Luego pulsa Continuar.</span>`;
        const done = document.createElement("button");
        done.type = "button";
        done.className = "btn-primary";
        done.textContent = "Continuar";
        done.addEventListener("click", () => {
            const marked = list.filter(el => el.classList.contains("is-marked")).map(elementId);
            ExperimentSession.log("difficulty_marks", { els: marked, count: marked.length, candidates: list.length });
            bar.remove();
            document.body.classList.remove("marking-mode");
            if (nextPage) {
                showPause();
            } else {
                ExperimentSession.save({ ...ExperimentSession.session, finished: true });
                window.location.href = nextUrl;   // pagehide envía el registro
            }
        });
        bar.appendChild(done);
        document.body.appendChild(bar);
    }
})();
