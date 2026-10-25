// ═══════════════════════════════════════════════════════════════
// Sesión experimental: se inicia en index.html y vive en sessionStorage (pasa
// entre páginas de la pestaña). Envía eventos y mirada por lotes al backend
// (session_log.py). Sin sesión ("modo libre") no se registra nada.
// ═══════════════════════════════════════════════════════════════
const SESSION_STORAGE_KEY = "gazeExperimentSession";
const SESSION_BACKEND     = "http://127.0.0.1:5000";
const LOG_FLUSH_MS        = 2000;
// Archivos con nombres neutros (no revelan el nivel); en el registro siguen
// siendo facil / intermedio / avanzado.
const PAGE_URLS = { facil: "siteA.html", intermedio: "siteB.html", avanzado: "siteC.html" };

const ExperimentSession = (() => {
    function load() {
        try {
            return JSON.parse(sessionStorage.getItem(SESSION_STORAGE_KEY));
        } catch (error) {
            return null;
        }
    }

    function save(session) {
        try {
            sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
            return true;
        } catch (error) {
            return false;
        }
    }

    function clear() {
        try {
            sessionStorage.removeItem(SESSION_STORAGE_KEY);
        } catch (error) { /* sin almacenamiento: no hay nada que borrar */ }
    }

    const session   = load();
    const fileName  = window.location.pathname.split("/").pop() || "index.html";
    const pageKey   = Object.keys(PAGE_URLS).find(key => PAGE_URLS[key] === fileName) || fileName.replace(".html", "");
    const pageUrl   = key => PAGE_URLS[key] || `${key}.html`;
    // "ayuda" (automática) | "a_pedido" | null (modo libre)
    const condition = session?.plan?.[pageKey] || null;

    let events = [];
    let gaze   = [];

    function log(type, data = {}) {
        if (!session) return;
        events.push({ ...data, type, t: Date.now(), page: pageKey });
    }

    // Muestra cruda: coordenadas de la ventana + desplazamiento de la página.
    function logGaze(x, y, valid) {
        if (!session || window.recordingPaused) return;   // pausa entre páginas: nada se guarda
        gaze.push([
            Date.now(),
            valid ? Math.round(x) : "",
            valid ? Math.round(y) : "",
            Math.round(window.scrollX),
            Math.round(window.scrollY),
            valid ? 1 : 0
        ]);
    }

    function takeBatch() {
        const batch = { session_id: session.id, page: pageKey, events, gaze };
        events = [];
        gaze   = [];
        return batch;
    }

    async function flush() {
        if (!session || (!events.length && !gaze.length)) return;
        const batch = takeBatch();
        try {
            const response = await fetch(`${SESSION_BACKEND}/log`, {
                method: "POST",
                headers: { "Content-Type": "text/plain" },
                body: JSON.stringify(batch)
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
        } catch (error) {
            // Se reintenta en el siguiente envío, sin perder el orden.
            events = batch.events.concat(events);
            gaze   = batch.gaze.concat(gaze);
            console.warn("[sesión] No se pudo enviar el registro; se reintentará.", error);
        }
    }

    // Al salir de la página: sendBeacon sí se entrega aunque la página se cierre.
    function flushOnExit() {
        if (!session || (!events.length && !gaze.length)) return;
        const batch = takeBatch();
        navigator.sendBeacon(
            `${SESSION_BACKEND}/log`,
            new Blob([JSON.stringify(batch)], { type: "text/plain" })
        );
    }

    if (session) setInterval(flush, LOG_FLUSH_MS);
    // En sesión se ocultan elementos que no deben verse (temas.css: .in-session).
    if (session) document.documentElement.classList.add("in-session");

    return {
        session,
        pageKey,
        pageUrl,
        condition,
        active: Boolean(session),
        // helpEnabled: ayuda automática. onDemand: botón "Ver ayuda".
        helpEnabled: condition !== "sin_ayuda" && condition !== "a_pedido",
        onDemand: condition === "a_pedido",
        log,
        logGaze,
        flush,
        flushOnExit,
        save,
        clear
    };
})();
