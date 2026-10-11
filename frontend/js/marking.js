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

    const ORDER = ["facil", "intermedio", "avanzado"];
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

    startButton.addEventListener("click", () => {
        // Cierra la lectura en curso y pausa el seguimiento.
        logElementExit();
        currentObservedElement = null;
        window.markingMode = true;
        hideTooltip();
        startButton.remove();
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
            window.location.href = nextUrl;   // pagehide envía el registro
        });
        bar.appendChild(done);
        document.body.appendChild(bar);
    });
})();
