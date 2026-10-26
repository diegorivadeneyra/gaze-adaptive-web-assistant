// ─── Configuración ───────────────────────────────────────────
// Mirada mínima para analizar un elemento (= BASE_DWELL_MS de decision_engine.py).
const DWELL_THRESHOLD_MS    = 500;
const POLL_INTERVAL_MS      = 100;
const BACKEND_URL           = "http://127.0.0.1:5000/analyze";

// ─── Fijaciones (I-DT) ───────────────────────────────────────
// Ventana y dispersión amplias: al leer, la mirada salta entre palabras.
const IDT_WINDOW_MS         = 300;  // ventana de tiempo para analizar puntos
const IDT_DISPERSION_PX     = 60;   // dispersión máxima para considerar fijación

// Tobii: datos inválidos por menos de esto = parpadeo (un parpadeo dura hasta ~400 ms).
const BLINK_GRACE_MS        = 450;

// Tobii: un cambio de elemento se confirma si dura esto (absorbe saltos de ruido).
const ELEMENT_SWITCH_GRACE_MS = 300;

// Tiempo visible del tooltip tras dejar el elemento (con 2.5 s se ocultaba
// mientras se leía, piloto P01).
const TOOLTIP_HOLD_MS       = 4000;
// Estabilidad del punto del Tobii en los bordes de los elementos (medido con el piloto P00).
const GAZE_SMOOTH_MS        = 100;   // mediana de los últimos 100 ms (~3 puntos a 33 Hz)
const EDGE_MARGIN_PX        = 40;    // margen alrededor del elemento actual

// ─── Estado ──────────────────────────────────────────────────
let mouseX                  = 0;
let mouseY                  = 0;
let lastValidGazeAt         = null;
let pointerActive            = false;
let gazePoints              = [];   // buffer de puntos para IDT
let currentObservedElement  = null;
let pendingElement          = null; // candidato a nuevo elemento (aún sin confirmar)
let pendingElementSince     = null; // desde cuándo se viene viendo ese candidato
let previousHighlighted     = null;
let observationStartTime    = null;
let analysisTriggered       = false;
let hadFixationOnCurrentElement = false;
// Resultado de /analyze por elemento: al volver a mirarlo no se llama al modelo.
const analysisCache = new WeakMap();
const pendingAnalyses = new WeakMap();   // figura -> análisis en curso (no se pide dos veces)
let activeRequestController = null;

// ─── Panel de monitoreo: ?debug=0 o la opción de la sesión lo ocultan ──
if (new URLSearchParams(window.location.search).get("debug") === "0"
    || ExperimentSession.session?.hideDebug) {
    document.querySelector(".debug-panel")?.classList.add("is-hidden");
    document.querySelector(".layout")?.classList.add("no-debug");
}

// ─── Referencias UI ──────────────────────────────────────────
const gazeInfo          = document.getElementById("gaze-info");
const currentElementBox = document.getElementById("current-element");
const contentTypeBox    = document.getElementById("content-type");
const dwellTimeBox      = document.getElementById("dwell-time");
const analysisResultBox = document.getElementById("analysis-result");
const backendStatus     = document.getElementById("backend-status");
const adaptiveTooltip   = document.getElementById("adaptive-tooltip");
const statusDot         = document.getElementById("status-dot");
const dwellBar          = document.getElementById("dwell-bar");

// ─── IDT: Identificación de fijaciones ───────────────────────
// Dispersión I-DT: (max_x - min_x) + (max_y - min_y).
function calculateDispersion(points) {
    if (points.length < 2) return 0;
    const xs = points.map(p => p.x);
    const ys = points.map(p => p.y);
    return (Math.max(...xs) - Math.min(...xs)) +
           (Math.max(...ys) - Math.min(...ys));
}

// Centro de la fijación.
function calculateCentroid(points) {
    const x = points.reduce((sum, p) => sum + p.x, 0) / points.length;
    const y = points.reduce((sum, p) => sum + p.y, 0) / points.length;
    return { x: Math.round(x), y: Math.round(y) };
}

// ¿Los puntos de la ventana forman una fijación? { isFixation, centroid, dispersion }
function runIDT(points) {
    const now = Date.now();

    const windowPoints = points.filter(
        p => now - p.timestamp <= IDT_WINDOW_MS
    );

    if (windowPoints.length < 3) {
        return { isFixation: false, centroid: null };
    }

    const dispersion = calculateDispersion(windowPoints);
    const isFixation = dispersion <= IDT_DISPERSION_PX;
    const centroid   = isFixation
        ? calculateCentroid(windowPoints)
        : null;

    return { isFixation, centroid, dispersion };
}

// ─── Clasificación de elementos ──────────────────────────────
// Las celdas no están: una tabla se analiza completa.
const TEXT_TAGS = ["P","SPAN","H1","H2","H3","H4","H5","H6",
                   "LI","BUTTON","A"];

function classifyElement(element) {
    if (!element) return "Otro";
    if (element.tagName === "TABLE")               return "Tabla";
    if (element.tagName.toLowerCase() === "svg")   return "Gráfico";
    if (TEXT_TAGS.includes(element.tagName))       return "Texto";
    if (element.tagName === "IMG")                 return "Imagen";
    return "Otro";
}

// ─── Identificador de elementos para el registro ─────────────
// Ruta desde <body> (p. ej. "main[0]>article[1]>p[0]"); page_enter guarda un
// hash del texto para detectar si la página cambió.
const elementIds = new WeakMap();

function elementId(element) {
    if (!element) return null;
    let id = elementIds.get(element);
    if (id) return id;
    const parts = [];
    for (let node = element; node && node !== document.body && node.nodeType === 1; node = node.parentElement) {
        let index = 0;
        for (let sibling = node.previousElementSibling; sibling; sibling = sibling.previousElementSibling) {
            if (sibling.tagName === node.tagName) index++;
        }
        parts.unshift(`${node.tagName.toLowerCase()}[${index}]`);
    }
    id = parts.join(">");
    elementIds.set(element, id);
    return id;
}

function elementSnippet(element) {
    const text = element.tagName === "IMG" ? element.alt : element.textContent;
    return (text || "").replace(/\s+/g, " ").trim().slice(0, 80);
}

// Hash simple (FNV-1a) del texto de la página: identifica la versión del
// contenido que vio cada participante.
function textHash(text) {
    let hash = 0x811c9dc5;
    for (let i = 0; i < text.length; i++) {
        hash ^= text.charCodeAt(i);
        hash = Math.imul(hash, 0x01000193) >>> 0;
    }
    return hash.toString(16);
}

// Posición de cada elemento analizable: con la mirada cruda permite recalcular después.
function pageLayout() {
    const selector = "p,h1,h2,h3,h4,h5,h6,li,table,img,svg";
    return [...document.querySelectorAll(selector)]
        .filter(element => !element.closest(".debug-panel") && extractContent(element))
        .map(element => {
            const rect = element.getBoundingClientRect();
            return {
                el: elementId(element),
                type: classifyElement(element),
                x: Math.round(rect.left + window.scrollX),
                y: Math.round(rect.top + window.scrollY),
                w: Math.round(rect.width),
                h: Math.round(rect.height),
                text: elementSnippet(element)
            };
        });
}

// ─── Extracción de contenido ─────────────────────────────────
// Contexto de una figura (alt + pie): da el tema y el idioma al modelo de visión.
function getVisualContext(element) {
    const parts = [];
    if (element.tagName === "IMG" && element.alt) parts.push(element.alt.trim());
    const caption = element.closest("figure")?.querySelector("figcaption")
        || element.closest(".mini-chart")?.querySelector(".chart-caption");
    const captionText = caption?.innerText?.trim();
    if (captionText) parts.push(captionText);
    return parts.join(" — ").slice(0, 300);
}

// Textos de una gráfica SVG (título, ejes, valores): leyendo solo la imagen,
// Qwen confundía el orden de barras parecidas.
function getChartText(svgElement) {
    const seen = new Set();
    return [...svgElement.querySelectorAll("text")]
        .map(node => node.textContent.replace(/\s+/g, " ").trim())
        .filter(text => text && !seen.has(text) && seen.add(text))
        .join(" · ")
        .slice(0, 600);
}

// ─── Contexto para el modelo: título de la página y subtítulo de la sección ──
function cleanDocumentTitle() {
    return (document.title || "").split(/\s[|·–—-]\s/)[0].trim();
}

function getPageTitle() {
    const h1 = [...document.querySelectorAll("h1")].find(h => !h.closest(".debug-panel"));
    return (h1?.innerText || cleanDocumentTitle()).replace(/\s+/g, " ").trim().slice(0, 150);
}

function getSectionHeading(element) {
    let last = null;
    for (const heading of document.querySelectorAll("h2,h3,h4,h5,h6")) {
        if (heading.closest(".debug-panel")) continue;
        if (!(heading.compareDocumentPosition(element) & Node.DOCUMENT_POSITION_FOLLOWING)) break;
        last = heading;
    }
    return (last?.innerText || "").replace(/\s+/g, " ").trim().slice(0, 150);
}

// Nivel diseñado de una figura (data-design-level); reemplaza al del modelo.
function getDesignLevel(element) {
    return element.closest("[data-design-level]")?.dataset.designLevel || "";
}

// Tipos: "text" | "table" | "image" | "chart" (el SVG se pasa a PNG solo al analizar).
const NO_HELP_SELECTOR = ".footnote, footer, cite, small, [role='note'], [role='doc-footnote'], "
    + "[role='doc-endnotes'], [role='doc-bibliography']";

function extractContent(element) {
    if (!element) return null;

    if (element.tagName === "TABLE") {
        const text = element.innerText?.trim();
        if (!text || text.length < 10) return null;
        // Sin legibilidad: el nivel lo juzga el modelo.
        return { type: "table", value: text };
    }

    if (element.tagName.toLowerCase() === "svg") {
        return { type: "chart", value: element, context: getVisualContext(element),
                 designLevel: getDesignLevel(element), chartText: getChartText(element) };
    }

    // Títulos sin ayuda (eran 6 de 26 ayudas y poco útiles).
    if (/^H[1-6]$/.test(element.tagName)) return null;

    // Notas y referencias sin ayuda.
    if (element.closest(NO_HELP_SELECTOR)) return null;

    if (TEXT_TAGS.includes(element.tagName)) {
        const text = element.innerText?.trim();
        if (!text || text.length < 20) return null;
        return { type: "text", value: text };
    }

    if (element.tagName === "IMG") {
        const src = element.src;
        if (!src || src.startsWith("data:")) return null;
        return { type: "image", value: src, context: getVisualContext(element),
                 designLevel: getDesignLevel(element) };
    }

    return null;
}

function getContentElement(element) {
    if (!element) return null;
    if (element.tagName === "IMG") return element;

    const svgElement = element.closest("svg");
    if (svgElement) return svgElement;

    const tableElement = element.closest("table");
    if (tableElement) return tableElement;

    const blockElement = element.closest(
        "p,h1,h2,h3,h4,h5,h6,li,button,a"
    );
    return blockElement || element.closest("span");
}

// ─── Conversión de gráficas SVG a PNG/base64 ──────────────────
// Las variables CSS (var(--accent)) se reemplazan por su valor antes de rasterizar.
function resolveSvgColors(svgMarkup) {
    const rootStyles = getComputedStyle(document.documentElement);
    return svgMarkup.replace(/var\(--([a-zA-Z0-9-]+)\)/g, (match, name) => {
        const value = rootStyles.getPropertyValue(`--${name}`).trim();
        return value || match;
    });
}

function svgToBase64Png(svgElement) {
    return new Promise((resolve) => {
        try {
            const viewBox = svgElement.viewBox?.baseVal;
            const width   = (viewBox && viewBox.width)  || svgElement.clientWidth  || 260;
            const height  = (viewBox && viewBox.height) || svgElement.clientHeight || 160;

            let markup = new XMLSerializer().serializeToString(svgElement);
            if (!markup.includes("xmlns=")) {
                markup = markup.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"');
            }
            markup = resolveSvgColors(markup);

            const blobUrl = URL.createObjectURL(
                new Blob([markup], { type: "image/svg+xml;charset=utf-8" })
            );
            const scale = 2;
            const img = new Image();

            img.onload = () => {
                const canvas = document.createElement("canvas");
                canvas.width  = width  * scale;
                canvas.height = height * scale;
                const ctx = canvas.getContext("2d");
                ctx.fillStyle = getComputedStyle(document.documentElement)
                    .getPropertyValue("--card-bg").trim() || "#1a1d27";
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                URL.revokeObjectURL(blobUrl);
                const dataUrl = canvas.toDataURL("image/png");
                resolve(dataUrl.split(",")[1] || null);
            };
            img.onerror = () => {
                URL.revokeObjectURL(blobUrl);
                resolve(null);
            };
            img.src = blobUrl;
        } catch (error) {
            console.error("Error convirtiendo gráfico a imagen:", error);
            resolve(null);
        }
    });
}

// Contenido → lo que se envía al backend (las gráficas como PNG base64).
async function resolveContentPayload(content) {
    if (content.type !== "chart") return content;
    const base64 = await svgToBase64Png(content.value);
    return base64
        ? { type: "image_base64", value: base64, context: content.context,
            designLevel: content.designLevel, chartText: content.chartText }
        : null;
}

// ─── Highlight del elemento observado ────────────────────────
function highlightElement(element) {
    if (previousHighlighted && previousHighlighted !== element) {
        previousHighlighted.classList.remove("gaze-highlight");
    }
    if (element) {
        element.classList.add("gaze-highlight");
        previousHighlighted = element;
    }
}

function clearHighlight() {
    if (previousHighlighted) {
        previousHighlighted.classList.remove("gaze-highlight");
        previousHighlighted = null;
    }
}

// ─── Tooltip ─────────────────────────────────────────────────
let tooltipHideTimer = null;

// ─── Lugar del tooltip: derecha, izquierda, debajo o arriba; la primera
// posición que no tapa contenido (si ninguna, la que menos tapa). ─────
const TOOLTIP_GAP_PX = 14;
// Un roce de menos de ~1 % del tooltip (un borde que toca) no cuenta como tapar.
const TOOLTIP_TOUCH_PX2 = 600;
const TOOLTIP_OBSTACLES = "p,li,h1,h2,h3,h4,h5,h6,table,img,svg,figcaption,.chart-caption,"
    + "nav,header,footer,.widget,button,input,.note-box";

function rectOverlap(a, b) {
    const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
    const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    return w > 0 && h > 0 ? w * h : 0;
}

// Devuelve { left, top, side, overlap } en coordenadas del documento.
function computeTooltipPlacement(element, width, height) {
    const r = element.getBoundingClientRect();
    const sx = window.scrollX, sy = window.scrollY;
    const el = { left: r.left + sx, top: r.top + sy, right: r.right + sx, bottom: r.bottom + sy };
    const minX = sx + 8, maxX = sx + window.innerWidth - 8;
    // A los costados, alineado con el inicio y con el final del elemento.
    const candidates = [
        { side: "derecha",   left: el.right + TOOLTIP_GAP_PX, top: el.top },
        { side: "derecha",   left: el.right + TOOLTIP_GAP_PX, top: el.bottom - height },
        { side: "izquierda", left: el.left - TOOLTIP_GAP_PX - width, top: el.top },
        { side: "izquierda", left: el.left - TOOLTIP_GAP_PX - width, top: el.bottom - height },
        { side: "debajo",    left: el.left, top: el.bottom + TOOLTIP_GAP_PX },
        { side: "arriba",    left: el.left, top: el.top - TOOLTIP_GAP_PX - height },
    ];
    const obstacles = [...document.querySelectorAll(TOOLTIP_OBSTACLES)]
        .filter(o => o !== element && !o.contains(element) && !element.contains(o)
            && !o.closest(".debug-panel") && !o.closest("#adaptive-tooltip") && o.offsetParent !== null)
        .map(o => {
            const b = o.getBoundingClientRect();
            return { left: b.left + sx, top: b.top + sy, right: b.right + sx, bottom: b.bottom + sy };
        });
    let best = null;
    for (const c of candidates) {
        // Debajo / arriba: se ajusta horizontalmente para no salirse de la ventana.
        if (c.side === "debajo" || c.side === "arriba") c.left = Math.min(Math.max(c.left, minX), maxX - width);
        if (c.left < minX || c.left + width > maxX || c.top < sy) continue;
        const box = { left: c.left, top: c.top, right: c.left + width, bottom: c.top + height };
        c.overlap = obstacles.reduce((sum, o) => sum + rectOverlap(box, o), 0);
        if (c.overlap < TOOLTIP_TOUCH_PX2) return c;
        if (!best || c.overlap < best.overlap) best = c;
    }
    return best || { ...candidates[4], left: Math.min(Math.max(el.left, minX), maxX - width), overlap: null };
}

function showTooltip(message, mode, element) {
    if (!message || !adaptiveTooltip) return;
    // Un tooltip nuevo cancela el ocultamiento pendiente.
    if (tooltipHideTimer) {
        clearTimeout(tooltipHideTimer);
        tooltipHideTimer = null;
    }
    const icon = mode === "ampliada" ? "📘" : mode === "summary" ? "📋" : "💡";
    adaptiveTooltip.innerText = `${icon} ${message}`;
    adaptiveTooltip.style.display = "block";

    if (element) {
        // Se mide con el texto ya puesto y luego se ubica sin tapar contenido.
        const place = computeTooltipPlacement(element, adaptiveTooltip.offsetWidth, adaptiveTooltip.offsetHeight);
        adaptiveTooltip.style.top  = `${place.top}px`;
        adaptiveTooltip.style.left = `${place.left}px`;
        adaptiveTooltip.dataset.side = place.side;
    }
}

function hideTooltip() {
    if (tooltipHideTimer) {
        clearTimeout(tooltipHideTimer);
        tooltipHideTimer = null;
    }
    closeHelpLog("oculta");
    if (adaptiveTooltip)
        adaptiveTooltip.style.display = "none";
}

// Se oculta TOOLTIP_HOLD_MS después de dejar el elemento.
function hideTooltipSoon() {
    if (tooltipHideTimer) clearTimeout(tooltipHideTimer);
    tooltipHideTimer = setTimeout(() => {
        tooltipHideTimer = null;
        hideTooltip();
    }, TOOLTIP_HOLD_MS);
}

// Con el Tobii, el tooltip también tiene margen (EDGE_MARGIN_PX).
function isPointInsideTooltip(point) {
    if (!adaptiveTooltip || adaptiveTooltip.style.display === "none") {
        return false;
    }
    const margin = inputSource === "tobii" ? EDGE_MARGIN_PX : 0;
    return GazeMapping.insideRect(adaptiveTooltip.getBoundingClientRect(), point, margin);
}

// ─── Status dot ──────────────────────────────────────────────
function setStatus(state) {
    if (!statusDot) return;
    statusDot.className = "status-dot";
    if (state === "active")    statusDot.classList.add("active");
    if (state === "analyzing") statusDot.classList.add("analyzing");
}

// ─── Barra de dwell time ─────────────────────────────────────
function updateDwellBar(dwellTime) {
    if (!dwellBar) return;
    const pct = Math.min((dwellTime / DWELL_THRESHOLD_MS) * 100, 100);
    dwellBar.style.width = `${pct}%`;
}

// ─── Panel de análisis ────────────────────────────────────────
function updateAnalysisPanel(diagnosis) {
    if (!analysisResultBox || !diagnosis) return;
    const complexityClass = {
        "Low": "low", "Medium": "medium", "High": "high"
    }[diagnosis.complexity] || "medium";

    const concept = document.createElement("div");
    concept.className = "concept";
    concept.textContent = diagnosis.concept || "—";

    const badge = document.createElement("span");
    badge.className = `badge ${complexityClass}`;
    badge.textContent = diagnosis.complexity || "—";

    const assistance = document.createElement("div");
    assistance.className = "analysis-assistance";
    assistance.textContent = diagnosis.needs_assistance
        ? "Asistencia activada"
        : "Sin asistencia requerida";

    // Origen del nivel: INFLESZ, nivel diseñado o modelo.
    const source = document.createElement("div");
    source.className = "analysis-assistance";
    source.textContent = diagnosis.difficulty_source === "legibilidad"
        ? `Nivel por legibilidad: INFLESZ ${diagnosis.inflesz} (${diagnosis.inflesz_label})`
        : diagnosis.difficulty_source === "diseño"
            ? "Nivel diseñado de la figura"
            : "Nivel por juicio del modelo";
    if (diagnosis.llm_complexity) source.textContent += ` · modelo: ${diagnosis.llm_complexity}`;

    analysisResultBox.replaceChildren(concept, badge, assistance, source);
}

// Términos ya explicados en la página: el backend no los repite (sin esto se
// repetían 4 de 24). Se llena igual con o sin ayuda visible.
const definedTermsOnPage = [];

function rememberDefinedTerms(terms) {
    for (const term of terms) {
        if (term && !definedTermsOnPage.includes(term)) definedTermsOnPage.push(term);
    }
}

// background: terminó con la mirada en otro elemento (figuras).
function logAnalysis(element, diagnosis, { fromCache = false, background = false } = {}) {
    ExperimentSession.log("analysis", {
        el: elementId(element),
        from_cache: fromCache,
        background,
        complexity: diagnosis.complexity,
        difficulty_source: diagnosis.difficulty_source,
        inflesz: diagnosis.inflesz ?? null,
        llm_complexity: diagnosis.llm_complexity ?? null,
        action: diagnosis.action,
        help_blocked: diagnosis.help_blocked ?? null,
        section: getSectionHeading(element),
        concept: diagnosis.concept,
        explanation: diagnosis.explanation,
        processing_time_s: fromCache ? 0 : diagnosis.processing_time ?? null
    });
}

// ─── Comunicación con backend ─────────────────────────────────
// cancellable: se cancela al cambiar de elemento o con otra petición (texto).
async function analyzeWithBackend(content, dwellTime, { cancellable = true } = {}) {
    const requestController = new AbortController();
    if (cancellable) {
        activeRequestController?.abort();
        activeRequestController = requestController;
    }
    try {
        if (backendStatus)
            backendStatus.innerText = "Analizando...";

        const response = await fetch(BACKEND_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                content:      content.value,
                content_type: content.type,
                dwell_time:   dwellTime,
                context:      content.context || "",
                design_level: content.designLevel || "",
                chart_text:   content.chartText || "",
                section:      content.section || "",
                defined_terms: content.type === "text" ? definedTermsOnPage : []
            }),
            signal: requestController.signal
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const result = await response.json();

        // Descartado por uno más nuevo: nada que mostrar ni guardar.
        if (result.stale) return null;

        if (backendStatus)
            backendStatus.innerText =
                `OK · ${result.processing_time ?? "—"}s`;

        return result;

    } catch (error) {
        if (error.name === "AbortError") return null;
        console.error("Error backend:", error);
        if (backendStatus)
            backendStatus.innerText = "Error de conexión";
        return {
            concept: "Error", complexity: "Low",
            needs_assistance: false, explanation: "",
            action: "none", mode: "none"
        };
    }
}

// ─── Ayuda pendiente: análisis recibido, esperando la señal de conducta
// (texto) o el tiempo fijo de su nivel (tablas, gráficas, imágenes). ──
let pendingHelp      = null;        // { element, diagnosis }
let currentIsRevisit = false;
const elementVisits  = new WeakMap();

// ─── Modelo de lectura (reading_model.js), solo en texto corrido. Si /config
// falla, todo usa tiempo fijo. ─────────────────────────────────────
let readingModel     = null;
let readingPolicy    = null;
let lastTickAt       = null;
let visitHadSignal   = false;   // hubo señal en esta visita (no adapta el ritmo)
// Fijaciones de la visita: cantidad, tiempo y dónde empezó la actual.
let visitFix         = { count: 0, ms: 0, anchor: null };
let lowSignalLogged  = false;   // ya se registró "se habría disparado" en Low

// El ritmo aprendido ({pace, samples}) pasa a la página siguiente (misma pestaña).
const PACE_STORAGE_KEY = "gazeReadingPace";

function loadStoredPace() {
    try {
        const raw = sessionStorage.getItem(PACE_STORAGE_KEY);
        if (!raw) return null;
        return raw.trim().startsWith("{") ? JSON.parse(raw) : parseFloat(raw);
    } catch (error) {
        return null;
    }
}

function storePace(state) {
    try {
        sessionStorage.setItem(PACE_STORAGE_KEY, JSON.stringify(state));
    } catch (error) { /* sin almacenamiento: el ritmo se reinicia por página */ }
}

// Sílabas y nivel INFLESZ del párrafo, calculados al entrar (sin esperar al
// análisis). En textos de < 8 palabras, el nivel del análisis. Sin títulos.
const localReadability = new WeakMap();

function readingInfo(element) {
    if (!readingModel || !isTextElement(element) || /^H[1-6]$/.test(element.tagName)) return null;
    let local = localReadability.get(element);
    if (!local) {
        const text = extractContent(element).value;
        local = { syllables: Readability.countTextSyllables(text),
                  level: Readability.computeReadability(text)?.level ?? null };
        localReadability.set(element, local);
    }
    const level = analysisCache.get(element)?.complexity || local.level;
    if (!local.syllables || !level) return null;
    return { syllables: local.syllables, level };
}

function isTextElement(element) {
    return Boolean(element) && extractContent(element)?.type === "text";
}

// Zona de la mirada en el párrafo: "inicio" | "medio" | "final" (bloques bajos: "final").
function gazeZone(element, point) {
    const rect = element.getBoundingClientRect();
    if (rect.height < readingPolicy.end_min_height_px) return "final";
    if (point.y >= rect.top + rect.height * (1 - readingPolicy.end_region)) return "final";
    if (point.y <= rect.top + rect.height * readingPolicy.start_region) return "inicio";
    return "medio";
}

// Ayuda visible en este momento (para registrar cuánto duró y cuánto se miró).
let helpCounter = 0;
let helpState   = null;  // { id, el, shownAt, gazeInsideMs }
let wasOnTooltip = false;   // la mirada estaba en el tooltip en el tick anterior
// Última ayuda de cada elemento, para que reaparezca si sale y vuelve rápido.
const lastHelpShown = new WeakMap();   // elemento -> { id, el, message, mode }

function tooltipRectOnPage() {
    if (!adaptiveTooltip || adaptiveTooltip.style.display === "none") return null;
    const r = adaptiveTooltip.getBoundingClientRect();
    return { x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height) };
}

function closeHelpLog(reason) {
    if (!helpState) return;
    ExperimentSession.log("help_hidden", {
        help_id: helpState.id,
        el: helpState.el,
        reason,
        visible_ms: Date.now() - helpState.shownAt,
        gaze_inside_ms: helpState.gazeInsideMs,
        tooltip_rect: tooltipRectOnPage()
    });
    helpState = null;
}

function offerPendingHelp(dwellTime) {
    if (!pendingHelp || pendingHelp.element !== currentObservedElement) return;
    const { diagnosis } = pendingHelp;

    // Texto: conducta. Tablas, gráficas e imágenes: tiempo fijo por nivel.
    let decision;
    const info = readingInfo(currentObservedElement);
    if (info && helpLevelGiven.get(currentObservedElement)) {
        pendingHelp = null;   // ya tuvo la primera ayuda: ahora decide el segundo nivel
        return;
    }
    if (info) {
        const sig = readingModel.signal(elementId(currentObservedElement), info);
        if (!sig) return;
        visitHadSignal = true;
        decision = { rule: "conducta", signal: sig.type, ratio: Math.round(sig.ratio * 100) / 100,
                     expected_ms: Math.round(sig.expected), acc_ms: Math.round(sig.accMs),
                     pace_ms_per_syllable: Math.round(readingModel.pace) };
    } else {
        const required = (currentIsRevisit
            ? diagnosis.revisit_min_dwell_ms
            : diagnosis.min_dwell_ms) ?? 0;
        if (dwellTime < required) return;
        decision = { rule: "tiempo_fijo", signal: currentIsRevisit ? "relectura" : "tiempo" };
    }

    const helpEvent = {
        ...decision,
        help_id: `${ExperimentSession.pageKey}-${++helpCounter}`,
        el: elementId(currentObservedElement),
        dwell_ms: dwellTime,
        revisit: currentIsRevisit,
        complexity: diagnosis.complexity,
        mode: diagnosis.mode,
        concept: diagnosis.concept,
        explanation: diagnosis.explanation,
        help_level: 1
    };
    pendingHelp = null;
    rememberDefinedTerms([diagnosis.concept]);

    // Las señales siguientes piden el segundo nivel; se prepara en segundo plano.
    if (decision.rule === "conducta") {
        readingModel.rearm(elementId(currentObservedElement));
        helpLevelGiven.set(currentObservedElement, 1);
        prefetchExpandedHelp(currentObservedElement, diagnosis.concept);
    }

    // Sin ayuda automática ("a pedido"): se registra la que habría salido.
    if (!ExperimentSession.helpEnabled) {
        ExperimentSession.log("help_suppressed", helpEvent);
        return;
    }

    closeHelpLog("reemplazada");
    showTooltip(diagnosis.explanation, diagnosis.mode, currentObservedElement);
    ExperimentSession.log("help_shown", helpEvent);
    helpState = { id: helpEvent.help_id, el: helpEvent.el, shownAt: Date.now(), gazeInsideMs: 0 };
    lastHelpShown.set(currentObservedElement, { id: helpEvent.help_id, el: helpEvent.el,
                                                message: diagnosis.explanation, mode: diagnosis.mode });
}

// Salida corta (< 5 s) y vuelta: misma lectura, la ayuda reaparece
// ("help_reshown", mismo help_id: no cuenta como ayuda nueva).
function reshowHelpOnReturn(element, readingEvent) {
    const last = lastHelpShown.get(element);
    if (!last || readingEvent !== "continua" || !ExperimentSession.helpEnabled) return;
    showTooltip(last.message, last.mode, element);   // cancela un ocultamiento pendiente
    if (helpState && helpState.id === last.id) return;   // no llegó a ocultarse
    closeHelpLog("reemplazada");
    ExperimentSession.log("help_reshown", { help_id: last.id, el: last.el });
    helpState = { id: last.id, el: last.el, shownAt: Date.now(), gazeInsideMs: 0 };
}

// ─── Condición "a pedido": botón "Ver ayuda" apenas hay ayuda disponible;
// luego "Más detalle". La regla automática sigue en silencio (help_suppressed). ──
let askState = null;   // { element, diagnosis, level }

if (adaptiveTooltip && ExperimentSession.onDemand) {
    adaptiveTooltip.classList.add("on-demand");
    adaptiveTooltip.addEventListener("click", event => {
        const button = event.target.closest("button[data-ask]");
        if (button && askState) requestHelp(button.dataset.ask);
    });
}

function renderTooltipHTML(element, html) {
    if (tooltipHideTimer) { clearTimeout(tooltipHideTimer); tooltipHideTimer = null; }
    adaptiveTooltip.innerHTML = html;
    adaptiveTooltip.style.display = "block";
    const place = computeTooltipPlacement(element, adaptiveTooltip.offsetWidth, adaptiveTooltip.offsetHeight);
    adaptiveTooltip.style.top  = `${place.top}px`;
    adaptiveTooltip.style.left = `${place.left}px`;
    adaptiveTooltip.dataset.side = place.side;
}

function escapeHTML(text) {
    return String(text).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function offerHelpButton(element, diagnosis) {
    if (askState && askState.element === element && adaptiveTooltip.style.display !== "none") return;
    closeHelpLog("reemplazada");
    askState = { element, diagnosis, level: 0 };
    renderTooltipHTML(element, '<button type="button" class="help-ask-btn" data-ask="1">💡 Ver ayuda</button>');
    ExperimentSession.log("help_offered", { el: elementId(element), complexity: diagnosis.complexity });
}

async function requestHelp(level) {
    const { element, diagnosis } = askState;
    const key = elementId(element);
    const canExpand = diagnosis && isTextElement(element) && readingInfo(element);
    if (level === "1") {
        prefetchExpandedHelp(element, diagnosis.concept);
        rememberDefinedTerms([diagnosis.concept]);
        const more = canExpand ? '<button type="button" class="help-ask-btn" data-ask="2">📘 Más detalle</button>' : "";
        renderTooltipHTML(element, `<div>${escapeHTML(`${diagnosis.mode === "summary" ? "📋" : "💡"} ${diagnosis.explanation}`)}</div>${more}`);
        logRequestedHelp(element, { help_level: 1, concept: diagnosis.concept, explanation: diagnosis.explanation,
                                    complexity: diagnosis.complexity, mode: diagnosis.mode });
        askState.level = 1;
        return;
    }
    renderTooltipHTML(element, '<div>📘 Preparando la explicación…</div>');
    const result = await expandedHelp.get(element);
    if (askState?.element !== element) return;
    if (!result || result.error || !result.explanation) {
        ExperimentSession.log("help_level2_unavailable", { el: key, error: result?.error ?? "vacía", requested: true });
        renderTooltipHTML(element, `<div>${escapeHTML(`💡 ${diagnosis.explanation}`)}</div>`);
        return;
    }
    rememberDefinedTerms(result.terms.map(t => t.term));
    renderTooltipHTML(element, `<div>${escapeHTML(`📘 ${result.explanation}`)}</div>`);
    logRequestedHelp(element, { help_level: 2, terms: result.terms.map(t => t.term), explanation: result.explanation,
                                complexity: diagnosis.complexity, mode: "ampliada" });
    askState.level = 2;
}

function logRequestedHelp(element, data) {
    closeHelpLog("reemplazada");
    const helpEvent = { rule: "a_pedido", signal: "clic", requested: true,
                        help_id: `${ExperimentSession.pageKey}-${++helpCounter}`, el: elementId(element),
                        dwell_ms: Date.now() - observationStartTime, ...data };
    ExperimentSession.log("help_requested", { el: helpEvent.el, help_level: data.help_level, help_id: helpEvent.help_id });
    ExperimentSession.log("help_shown", helpEvent);
    helpState = { id: helpEvent.help_id, el: helpEvent.el, shownAt: Date.now(), gazeInsideMs: 0 };
}

// ─── Segundo nivel (expanded_help.py): si se vuelve a trabar tras la primera
// ayuda. Se pide en segundo plano al dar la primera. ───────────────
const EXPAND_URL = BACKEND_URL.replace("/analyze", "/expand");
const helpLevelGiven = new WeakMap();   // elemento -> 1 o 2
const expandedHelp   = new WeakMap();   // elemento -> promesa del resultado
let level2Busy = false;

function prefetchExpandedHelp(element, alreadyDefined) {
    if (expandedHelp.has(element)) return;
    const content = extractContent(element);
    if (!content || content.type !== "text") return;
    expandedHelp.set(element, fetch(EXPAND_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: content.value, section: getSectionHeading(element),
                               already_defined: alreadyDefined || "",
                               defined_terms: definedTermsOnPage })
    }).then(r => r.json()).catch(() => ({ error: "sin conexión" })));
}

async function offerLevel2(element, sig, dwellTime) {
    if (level2Busy || !expandedHelp.has(element)) return;
    level2Busy = true;
    try {
        const result = await expandedHelp.get(element);
        if (currentObservedElement !== element) return;   // ya se fue: se ofrecerá en otra señal
        const key = elementId(element);
        readingModel.rearm(key);
        helpLevelGiven.set(element, 2);
        if (!result || result.error || !result.explanation) {
            ExperimentSession.log("help_level2_unavailable", { el: key, error: result?.error ?? "vacía" });
            return;
        }
        const helpEvent = {
            rule: "conducta", signal: sig.type, ratio: Math.round(sig.ratio * 100) / 100,
            expected_ms: Math.round(sig.expected), acc_ms: Math.round(sig.accMs),
            help_id: `${ExperimentSession.pageKey}-${++helpCounter}`, el: key, dwell_ms: dwellTime,
            mode: "ampliada", help_level: 2, terms: result.terms.map(t => t.term),
            discarded_terms: result.discarded_terms, explanation: result.explanation
        };
        rememberDefinedTerms(helpEvent.terms);
        if (!ExperimentSession.helpEnabled) {
            ExperimentSession.log("help_suppressed", helpEvent);
            return;
        }
        closeHelpLog("reemplazada");
        showTooltip(result.explanation, "ampliada", element);
        ExperimentSession.log("help_shown", helpEvent);
        helpState = { id: helpEvent.help_id, el: key, shownAt: Date.now(), gazeInsideMs: 0 };
        lastHelpShown.set(element, { id: helpEvent.help_id, el: key, message: result.explanation, mode: "ampliada" });
    } finally {
        level2Busy = false;
    }
}

// ─── Proceso principal ────────────────────────────────────────
async function processObservation() {
    // Pausado mientras el participante marca lo que le costó (marking.js).
    if (window.markingMode) return;
    const idt = runIDT(gazePoints);

    if (gazeInfo)
        gazeInfo.innerText = idt.isFixation
            ? `Fijación · (${idt.centroid?.x}, ${idt.centroid?.y})`
            : `Movimiento · dispersión: ${idt.dispersion?.toFixed(0)}px`;

    // Punto de referencia: centro de la fijación; si no hay, el punto suavizado
    // (Tobii) o la última posición (mouse).
    const smoothed = inputSource === "tobii"
        ? GazeMapping.smoothPoint(gazePoints, Date.now(), GAZE_SMOOTH_MS) : null;
    const referencePoint = idt.isFixation
        ? idt.centroid
        : (smoothed || { x: mouseX, y: mouseY });

    // Tobii: más de BLINK_GRACE_MS sin datos válidos = dejó de mirar.
    const msSinceValidGaze = lastValidGazeAt !== null ? Date.now() - lastValidGazeAt : null;
    const trackingLost = inputSource === "tobii"
        && msSinceValidGaze !== null
        && msSinceValidGaze > BLINK_GRACE_MS;

    const rawElement = trackingLost
        ? null
        : document.elementFromPoint(referencePoint.x, referencePoint.y);
    const isReadingTooltip = !trackingLost
        && currentObservedElement
        && isPointInsideTooltip(referencePoint);
    let candidateElement = isReadingTooltip
        ? currentObservedElement
        : getContentElement(rawElement);
    // Tobii: salir hasta EDGE_MARGIN_PX hacia espacio vacío sigue contando como el elemento.
    if (inputSource === "tobii" && !trackingLost && !candidateElement && currentObservedElement
        && GazeMapping.insideRect(currentObservedElement.getBoundingClientRect(), referencePoint, EDGE_MARGIN_PX)) {
        candidateElement = currentObservedElement;
    }

    // Tiempo con la mirada dentro del tooltip (resolución: un tick de 100 ms).
    const gazeOnTooltip = !trackingLost && isPointInsideTooltip(referencePoint);
    if (helpState && gazeOnTooltip) {
        helpState.gazeInsideMs += POLL_INTERVAL_MS;
    }
    // Mirar el tooltip cancela su ocultamiento; al dejarlo, vuelve a contar
    // (salvo que la mirada esté en el elemento de esa ayuda).
    if (gazeOnTooltip) {
        if (tooltipHideTimer) { clearTimeout(tooltipHideTimer); tooltipHideTimer = null; }
        wasOnTooltip = true;
    } else if (wasOnTooltip) {
        wasOnTooltip = false;
        const helpEl = helpState?.el ?? (askState?.element ? elementId(askState.element) : null);
        const onHelpElement = currentObservedElement && helpEl === elementId(currentObservedElement);
        if (!onHelpElement && adaptiveTooltip.style.display !== "none") hideTooltipSoon();
    }

    // Tobii: el cambio de elemento se confirma tras ELEMENT_SWITCH_GRACE_MS
    // (el ruido del sensor no reinicia la lectura). Con mouse, inmediato.
    let fixatedElement = currentObservedElement;
    if (inputSource === "tobii") {
        if (candidateElement === currentObservedElement) {
            pendingElement = null;
            pendingElementSince = null;
        } else {
            if (candidateElement !== pendingElement) {
                pendingElement = candidateElement;
                pendingElementSince = Date.now();
            }
            if (Date.now() - pendingElementSince >= ELEMENT_SWITCH_GRACE_MS) {
                fixatedElement = candidateElement;
                pendingElement = null;
                pendingElementSince = null;
            }
        }
    } else {
        fixatedElement = candidateElement;
    }

    // Cambió de elemento: se reinicia la visita.
    if (fixatedElement !== currentObservedElement) {
        logElementExit();
        activeRequestController?.abort();
        currentObservedElement      = fixatedElement;
        observationStartTime        = Date.now();
        analysisTriggered           = false;
        hadFixationOnCurrentElement = false;
        pendingHelp                 = null;
        visitHadSignal              = false;
        visitFix                    = { count: 0, ms: 0, anchor: null };
        lowSignalLogged             = false;

        // Volver a un elemento ya mirado (regresión) = relectura.
        let readingEvent = null;
        if (fixatedElement) {
            const visits = (elementVisits.get(fixatedElement) || 0) + 1;
            elementVisits.set(fixatedElement, visits);
            currentIsRevisit = visits >= 2;
            // primera / continua (salida corta) / relectura / reinicio
            const reading = readingModel && isTextElement(fixatedElement)
                ? readingModel.enter(elementId(fixatedElement), Date.now()) : null;
            readingEvent = reading?.event ?? null;
            ExperimentSession.log("element_enter", {
                el: elementId(fixatedElement),
                el_type: classifyElement(fixatedElement),
                visit: visits,
                reading_event: reading?.event ?? null
            });
        } else {
            currentIsRevisit = false;
        }
        // El tooltip se oculta TOOLTIP_HOLD_MS después, salvo que vuelva a él o a su elemento.
        hideTooltipSoon();
        const backToShown = fixatedElement && ((helpState && helpState.el === elementId(fixatedElement))
            || (askState && askState.element === fixatedElement));
        if (backToShown && tooltipHideTimer && adaptiveTooltip.style.display !== "none") {
            clearTimeout(tooltipHideTimer);
            tooltipHideTimer = null;
        }
        if (fixatedElement) reshowHelpOnReturn(fixatedElement, readingEvent);
        updateDwellBar(0);
        if (dwellTimeBox) dwellTimeBox.innerText = "0.0s";
        clearHighlight();
        setStatus("");
    }

    if (!currentObservedElement) return;

    const dwellTime = Date.now() - observationStartTime;

    if (currentElementBox)
        currentElementBox.innerText = currentObservedElement.tagName || "—";
    if (contentTypeBox)
        contentTypeBox.innerText = classifyElement(currentObservedElement);
    if (dwellTimeBox)
        dwellTimeBox.innerText = `${(dwellTime / 1000).toFixed(1)}s`;

    updateDwellBar(dwellTime);

    const content      = extractContent(currentObservedElement);
    const isAnalyzable = content !== null;

    if (isAnalyzable) {
        setStatus("active");
        highlightElement(currentObservedElement);
    } else {
        setStatus("");
        clearHighlight();
        return;
    }

    if (idt.isFixation) {
        hadFixationOnCurrentElement = true;
    }

    const now = Date.now();
    const dt = lastTickAt === null ? 0 : Math.min(now - lastTickAt, POLL_INTERVAL_MS * 2.5);
    lastTickAt = now;

    // Fijación nueva si no había o si se alejó más que la dispersión I-DT del
    // punto donde empezó la actual.
    if (idt.isFixation && !isReadingTooltip) {
        const moved = visitFix.anchor
            && Math.hypot(idt.centroid.x - visitFix.anchor.x, idt.centroid.y - visitFix.anchor.y) > IDT_DISPERSION_PX;
        if (!visitFix.anchor || moved) {
            visitFix.count++;
            visitFix.anchor = idt.centroid;
        }
        visitFix.ms += dt;
    } else {
        visitFix.anchor = null;
    }

    // Modelo de lectura: tiempo en el párrafo y zona de la mirada (no al leer el tooltip).
    if (readingModel && isTextElement(currentObservedElement) && !trackingLost && !isReadingTooltip) {
        const key = elementId(currentObservedElement);
        const info = readingInfo(currentObservedElement);
        readingModel.tick(key, dt, gazeZone(currentObservedElement, referencePoint), info, idt.isFixation);
        if (info && helpLevelGiven.get(currentObservedElement)) {
            const sig = readingModel.signal(key, info);
            if (sig) offerLevel2(currentObservedElement, sig, dwellTime);
        }
        if (info && info.level === "Low" && !lowSignalLogged) {
            const sig = readingModel.signal(key, info);
            if (sig) {
                lowSignalLogged = true;
                // Low sin ayuda: se registra. "Atascado" en Low es ritmo lento y
                // sí enseña el ritmo; una relectura no.
                if (sig.type !== "atascado") visitHadSignal = true;
                ExperimentSession.log("help_would_trigger_low", {
                    el: key, signal: sig.type, ratio: Math.round(sig.ratio * 100) / 100,
                    expected_ms: Math.round(sig.expected), acc_ms: Math.round(sig.accMs)
                });
            }
        }
        // Panel de monitoreo: tiempo acumulado / esperado y ritmo actual.
        if (dwellTimeBox && info) {
            dwellTimeBox.innerText = `${(dwellTime / 1000).toFixed(1)}s · leído `
                + `${(readingModel.accMs(key) / 1000).toFixed(1)}/${(readingModel.expectedMs(info) / 1000).toFixed(1)}s`
                + ` · ritmo ${Math.round(readingModel.pace)} ms/síl`;
        }
    }

    // Con mouse se exige una fijación (pasar por encima no cuenta). Con el
    // Tobii basta quedarse 500 ms en el mismo elemento.
    const fixationRequirementMet = inputSource === "tobii" || hadFixationOnCurrentElement;

    offerPendingHelp(dwellTime);

    if (dwellTime >= DWELL_THRESHOLD_MS
        && fixationRequirementMet
        && !analysisTriggered) {

        analysisTriggered = true;
        setStatus("analyzing");

        const elementAtTrigger = currentObservedElement;

        try {
            let diagnosis = analysisCache.get(elementAtTrigger);
            const cachedBefore = diagnosis;

            if (!diagnosis) {
                // Figuras: el análisis sigue aunque la mirada se vaya y queda
                // guardado (en GPU de 6 GB tarda ~11 s y se cancelaba en cada salida).
                const isVisual = content.type === "chart" || content.type === "image";
                let pending = pendingAnalyses.get(elementAtTrigger);
                if (!pending) {
                    const payload = await resolveContentPayload(content);
                    if (!payload || (!isVisual && currentObservedElement !== elementAtTrigger)) return;
                    // Contexto: solo el subtítulo de la sección, en texto y tablas
                    // (medido con evaluation/ab_contexto.py).
                    if (payload.type === "text" || payload.type === "table") {
                        payload.section = getSectionHeading(elementAtTrigger);
                    }
                    pending = analyzeWithBackend(payload, dwellTime / 1000, { cancellable: !isVisual })
                        .then(result => {
                            // Los errores no se guardan (dejarían el elemento sin ayuda).
                            if (result && result.concept !== "Error") {
                                analysisCache.set(elementAtTrigger, result);
                                if (currentObservedElement !== elementAtTrigger) {
                                    logAnalysis(elementAtTrigger, result, { background: true });
                                }
                            }
                            return result;
                        })
                        .finally(() => pendingAnalyses.delete(elementAtTrigger));
                    if (isVisual) pendingAnalyses.set(elementAtTrigger, pending);
                }
                diagnosis = await pending;
            }

            if (!diagnosis || currentObservedElement !== elementAtTrigger) return;

            logAnalysis(elementAtTrigger, diagnosis, { fromCache: Boolean(cachedBefore) });
            updateAnalysisPanel(diagnosis);

            if (ExperimentSession.onDemand && diagnosis.action === "tooltip" && diagnosis.explanation) {
                offerHelpButton(elementAtTrigger, diagnosis);
            }
            if (diagnosis.action === "tooltip" && diagnosis.explanation) {
                pendingHelp = { element: elementAtTrigger, diagnosis };
                offerPendingHelp(Date.now() - observationStartTime);
            }
        } finally {
            setStatus(
                currentObservedElement === elementAtTrigger ? "active" : ""
            );
        }
    }
}

// ─── Fuente de la mirada: mouse o Tobii, fijada al arrancar app.py (/config) ──
let inputSource = "mouse";
// Corrección de la mirada medida en calibracion.html (null = sin corregir).
const gazeCorrection = window.GazeMapping ? GazeMapping.loadCorrection(sessionStorage) : null;
const CONFIG_URL = "http://127.0.0.1:5000/config";
const GAZE_WS_URL = "ws://127.0.0.1:5600";

function pushGazePoint(x, y, timestamp) {
    ExperimentSession.logGaze(x, y, true);
    pointerActive = true;
    lastValidGazeAt = timestamp;
    mouseX = x;
    mouseY = y;
    gazePoints.push({ x, y, timestamp });
    const cutoff = Date.now() - IDT_WINDOW_MS * 2;
    gazePoints = gazePoints.filter(p => p.timestamp > cutoff);
}

document.addEventListener("mousemove", (event) => {
    if (inputSource !== "mouse") return; // en modo Tobii el mouse no debe interferir
    pushGazePoint(event.clientX, event.clientY, Date.now());
});

function sampleStationaryPointer() {
    if (!pointerActive) return;
    gazePoints.push({ x: mouseX, y: mouseY, timestamp: Date.now() });
    const cutoff = Date.now() - IDT_WINDOW_MS * 2;
    gazePoints = gazePoints.filter(point => point.timestamp > cutoff);
}

// WebSocket con los puntos del Tobii; si no está disponible, reintenta cada 2 s.
let tobiiSocket = null;

function connectTobiiSocket() {
    if (tobiiSocket) return;

    tobiiSocket = new WebSocket(GAZE_WS_URL);

    tobiiSocket.onmessage = (event) => {
        let data;
        try {
            data = JSON.parse(event.data);
        } catch (error) {
            return;
        }
        if (data?.valid && typeof data.nx === "number" && typeof data.ny === "number") {
            // Proporción de pantalla → página, con la corrección de la comprobación de 5 puntos.
            const p = GazeMapping.applyCorrection(GazeMapping.normalizedToClient(data.nx, data.ny, window),
                                                  gazeCorrection);
            pushGazePoint(p.x, p.y, Date.now());
        } else if (data?.valid && typeof data.x === "number" && typeof data.y === "number") {
            pushGazePoint(data.x, data.y, Date.now());   // fuente sin proporción (simulate_gaze.py)
        } else {
            // Muestra inválida (parpadeo o pérdida): se registra.
            ExperimentSession.logGaze(null, null, false);
        }
    };

    tobiiSocket.onclose = () => {
        tobiiSocket = null;
        if (inputSource === "tobii") {
            setTimeout(connectTobiiSocket, 2000);
        }
    };

    tobiiSocket.onerror = () => {
        tobiiSocket?.close();
    };
}

// ─── Indicador (solo lectura) de la fuente activa ─────────────
function renderInputSourceIndicator() {
    let indicator = document.querySelector(".input-source-indicator");
    if (!indicator) {
        const debugHeader = document.querySelector(".debug-header");
        if (!debugHeader) return;
        indicator = document.createElement("div");
        indicator.className = "debug-section input-source-indicator";
        indicator.innerHTML = `
            <span class="debug-label">Fuente de coordenadas</span>
            <span class="debug-value" id="input-source-value">—</span>
        `;
        debugHeader.insertAdjacentElement("afterend", indicator);
    }
    const valueBox = indicator.querySelector("#input-source-value");
    if (valueBox) {
        valueBox.textContent = inputSource === "tobii" ? "👁️ Tobii 5" : "🖱️ Mouse";
    }
}

// Fuente de la mirada y política de lectura desde /config (sin backend: mouse).
async function loadInputSourceConfig() {
    try {
        const response = await fetch(CONFIG_URL);
        if (response.ok) {
            const data = await response.json();
            if (data.input_source === "tobii" || data.input_source === "mouse") {
                inputSource = data.input_source;
            }
            if (data.reading_policy && typeof createReadingModel === "function") {
                readingPolicy = data.reading_policy;
                readingModel = createReadingModel(readingPolicy, loadStoredPace());
            }
        }
    } catch (error) {
        console.warn("[gaze] No se pudo leer /config; usando 'mouse' por defecto.");
    }
    renderInputSourceIndicator();
}

// ─── Registro de la página (solo con sesión) ──────────────────
const pageEnteredAt = Date.now();

function logElementExit() {
    if (!currentObservedElement || observationStartTime === null) return;
    const key = elementId(currentObservedElement);
    ExperimentSession.log("element_exit", {
        el: key,
        dwell_ms: Date.now() - observationStartTime,
        fixation_count: visitFix.count,
        fixation_ms: Math.round(visitFix.ms),
        mean_fixation_ms: visitFix.count ? Math.round(visitFix.ms / visitFix.count) : null
    });
    if (readingModel && isTextElement(currentObservedElement)) {
        const info = readingInfo(currentObservedElement);
        const { snapshot, paceUpdate } = readingModel.leave(key, Date.now(), info, visitHadSignal);
        ExperimentSession.log("reading_state", {
            el: key, level: info?.level ?? null, syllables: info?.syllables ?? null,
            acc_ms: Math.round(snapshot.accMs),
            expected_ms: snapshot.expected ? Math.round(snapshot.expected) : null,
            read_complete: snapshot.readComplete, reached_end: snapshot.reachedEnd,
            pace_ms_per_syllable: Math.round(snapshot.pace)
        });
        if (paceUpdate) {
            storePace(readingModel.paceState);
            ExperimentSession.log("pace_update", {
                el: key, level: info.level, old: Math.round(paceUpdate.old), new: Math.round(paceUpdate.new),
                observed: Math.round(paceUpdate.observed), samples: paceUpdate.samples
            });
        }
    }
}

function logPageEnter() {
    ExperimentSession.log("page_enter", {
        condition: ExperimentSession.condition,
        url: window.location.href,
        input_source: inputSource,
        viewport: { w: window.innerWidth, h: window.innerHeight },
        screen: { w: window.screen.width, h: window.screen.height, dpr: window.devicePixelRatio },
        page_hash: textHash(document.querySelector(".page-wrapper")?.innerText || ""),
        page_title: getPageTitle(),
        config: {
            DWELL_THRESHOLD_MS, POLL_INTERVAL_MS, IDT_WINDOW_MS, IDT_DISPERSION_PX,
            BLINK_GRACE_MS, ELEMENT_SWITCH_GRACE_MS, TOOLTIP_HOLD_MS
        }
    });
    // Layout con la página cargada y al cambiar el tamaño de la ventana.
    const logLayout = () => ExperimentSession.log("layout", {
        viewport: { w: window.innerWidth, h: window.innerHeight },
        elements: pageLayout()
    });
    if (document.readyState === "complete") logLayout();
    else window.addEventListener("load", logLayout, { once: true });
    let resizeTimer = null;
    window.addEventListener("resize", () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(logLayout, 500);
    });
    window.addEventListener("pagehide", () => {
        logElementExit();
        closeHelpLog("salida_de_pagina");
        ExperimentSession.log("page_exit", { duration_ms: Date.now() - pageEnteredAt });
        ExperimentSession.flushOnExit();
    });
}

// Sesión y condición en el panel de monitoreo.
function renderSessionIndicator() {
    const debugHeader = document.querySelector(".debug-header");
    if (!debugHeader) return;
    const indicator = document.createElement("div");
    indicator.className = "debug-section";
    const label = ExperimentSession.active
        ? `${ExperimentSession.session.participant} · ${ExperimentSession.onDemand ? "a pedido" : "automática"}`
        : "Modo libre (sin registro)";
    indicator.innerHTML = `<span class="debug-label">Sesión</span><span class="debug-value"></span>`;
    indicator.querySelector(".debug-value").textContent = label;
    debugHeader.insertAdjacentElement("afterend", indicator);
}

(async function init() {
    await loadInputSourceConfig();
    renderSessionIndicator();
    if (ExperimentSession.active) logPageEnter();

    if (inputSource === "tobii") {
        connectTobiiSocket();
    }

    // Cada 100 ms se evalúa la mirada acumulada (con el Tobii llega por WebSocket).
    setInterval(() => {
        if (inputSource === "mouse") {
            sampleStationaryPointer();
        }
        processObservation();
    }, POLL_INTERVAL_MS);
})();