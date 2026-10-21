// ─── Configuración ───────────────────────────────────────────
// Atención mínima para disparar el análisis. Debe coincidir con BASE_DWELL_MS
// de backend/analyzers/decision_engine.py (ahí vive la política de ayuda).
const DWELL_THRESHOLD_MS    = 500;
const POLL_INTERVAL_MS      = 100;
const BACKEND_URL           = "http://127.0.0.1:5000/analyze";

// ─── Parámetros IDT ──────────────────────────────────────────
// Con el mouse (dispersión casi 0 al estar quieto) 150ms/30px sobraba.
// Con mirada real, leer un párrafo implica saltar de palabra en palabra
// (fácil superar 30px aunque sí se esté leyendo ESE párrafo), y en modo
// Tobii solo entra 1 punto nuevo por tick de polling (cada 100ms) — con
// una ventana de 150ms rara vez se juntan los 3 puntos mínimos que pide
// runIDT(). Se sube la ventana (para juntar puntos) y la dispersión
// tolerada (para no confundir sacadas de lectura con "no hay fijación").
const IDT_WINDOW_MS         = 300;  // ventana de tiempo para analizar puntos
const IDT_DISPERSION_PX     = 60;   // dispersión máxima para considerar fijación

// Margen de tolerancia a un parpadeo (solo aplica en modo Tobii): mientras
// el Tobii reporte datos inválidos por menos de esto, se asume que es un
// parpadeo y se mantiene el elemento observado congelado en su última
// posición válida. Si se supera, se asume que de verdad se dejó de mirar.
// Subido de 300 a 450ms: un parpadeo normal puede durar hasta ~400ms: con
// 300 se estaba cancelando la fijación en parpadeos lentos. Trade-off real:
// cuanto más alto, más tarda el sistema en notar que SÍ dejaste de mirar
// algo de verdad (no es gratis, se cambia tolerancia por reacción).
const BLINK_GRACE_MS        = 450;

// Margen de histéresis para CONFIRMAR un cambio de elemento observado (solo
// modo Tobii): absorbe el ruido normal del sensor ("miro algo y el punto
// salta y vuelve") sin resetear dwell/tooltip por saltos que no duran.
// Mismo trade-off que arriba: más alto = más tolerante al ruido, pero más
// lento para reaccionar cuando el cambio de atención sí es real.
const ELEMENT_SWITCH_GRACE_MS = 300;

// Cuánto se mantiene visible el tooltip después de que la mirada SE
// CONFIRMA fuera del elemento (ver más abajo), para dar tiempo real a
// leerlo en vez de que desaparezca apenas la mirada se mueve. No afecta
// la precisión de detección, solo cuánto dura en pantalla — es una mejora
// "gratis" en ese sentido (no compite con nada del tracking).
// 4 s (antes 2.5 s): en el piloto P01, 6 de 15 tooltips se ocultaban a los
// ~3 s mientras la persona intentaba leerlos.
const TOOLTIP_HOLD_MS       = 4000;
// Estabilidad de la mirada del Tobii (2026-10-20): el punto temblaba en los
// bordes de los párrafos y el sistema creía que la persona se había ido.
// 100 ms (antes 150): con la sesión piloto real, 150 ms demoraba 0.41 s en
// reconocer un cambio de elemento y 100 ms 0.36 s (antes del suavizado 0.34 s),
// con la mitad de rebotes que sin suavizar (1.3 frente a 2.6 por minuto).
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
// Cachea el resultado de /analyze por elemento del DOM: si vuelves a mirar
// el mismo párrafo/imagen, se reutiliza en vez de volver a llamar al LLM —
// esto es lo que más ayuda contra la lentitud acumulada en sesiones largas,
// porque cada llamada real es una inferencia pesada (Qwen/phi3). Como el
// contenido de las páginas no cambia en vivo, no hay riesgo de que quede
// "vieja" — si algún día el contenido fuera dinámico, habría que invalidarla.
const analysisCache = new WeakMap();
let activeRequestController = null;

// ─── Visibilidad del panel de debug (?debug=0 lo oculta) ──────
// En una sesión experimental se oculta si así se eligió al iniciarla
// (los enlaces entre páginas no conservan el ?debug=0).
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
/**
 * Calcula la dispersión de un conjunto de puntos.
 * Fórmula IDT: (max_x - min_x) + (max_y - min_y)
 * Si dispersión < umbral → es una fijación
 */
function calculateDispersion(points) {
    if (points.length < 2) return 0;
    const xs = points.map(p => p.x);
    const ys = points.map(p => p.y);
    return (Math.max(...xs) - Math.min(...xs)) +
           (Math.max(...ys) - Math.min(...ys));
}

/**
 * Calcula el centroide (centro promedio) de un conjunto de puntos.
 * Representa el punto central de la fijación.
 */
function calculateCentroid(points) {
    const x = points.reduce((sum, p) => sum + p.x, 0) / points.length;
    const y = points.reduce((sum, p) => sum + p.y, 0) / points.length;
    return { x: Math.round(x), y: Math.round(y) };
}

/**
 * Algoritmo IDT principal.
 * Analiza el buffer de puntos recientes y determina
 * si constituyen una fijación o un movimiento.
 * 
 * Retorna: { isFixation, centroid } o null si no hay datos suficientes
 */
function runIDT(points) {
    const now = Date.now();

    // Filtrar solo los puntos dentro de la ventana temporal
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
// TD/TH no aparecen aquí: getContentElement() los sube hasta la <table>
// contenedora para analizarla como unidad completa, no celda por celda.
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
// Ruta calculada desde <body> (p. ej. "div[0]>main[0]>article[1]>p[0]"):
// funciona en cualquier página sin anotarla. Si cambia el contenido de la
// página cambian las rutas; por eso page_enter registra un hash del texto.
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

// Posición (en coordenadas del documento) de cada elemento analizable:
// junto con la mirada cruda y el scroll permite recalcular offline qué se
// miraba y cuánto tiempo, con otros umbrales.
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
// Texto de contexto de una imagen/gráfica (alt + pie de figura): le da al
// modelo de visión el tema del documento y fija el idioma de la respuesta.
function getVisualContext(element) {
    const parts = [];
    if (element.tagName === "IMG" && element.alt) parts.push(element.alt.trim());
    const caption = element.closest("figure")?.querySelector("figcaption")
        || element.closest(".mini-chart")?.querySelector(".chart-caption");
    const captionText = caption?.innerText?.trim();
    if (captionText) parts.push(captionText);
    return parts.join(" — ").slice(0, 300);
}

// Textos escritos dentro de una gráfica SVG (título, ejes, valores y
// etiquetas), en el orden del documento. Se mandan al modelo de visión como
// texto: leyendo solo la imagen a 512 px, Qwen confundía el orden de barras
// parecidas (dijo transporte > industria con 8.2 vs 10.4). Funciona con
// cualquier gráfica SVG; las imágenes (fotos, PNG) no tienen estos textos.
function getChartText(svgElement) {
    const seen = new Set();
    return [...svgElement.querySelectorAll("text")]
        .map(node => node.textContent.replace(/\s+/g, " ").trim())
        .filter(text => text && !seen.has(text) && seen.add(text))
        .join(" · ")
        .slice(0, 600);
}

// ─── Contexto de la página para el modelo ────────────────────
// Título del contenido (primer <h1>; si no hay, el <title> sin el nombre del
// sitio, que suele ir tras "|", "·" o "-") y el subtítulo de la sección donde
// está el elemento. Le da al modelo el tema antes de leer el párrafo (p. ej.
// que "residuos" es estadístico, no ambiental). Funciona en cualquier página.
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

// Nivel diseñado de una figura (atributo data-design-level en ella o en su
// contenedor). Si existe, el backend lo usa en vez del juicio del modelo.
// (No es data-level: ese ya lo usa <body> para el estilo de la página.)
function getDesignLevel(element) {
    return element.closest("[data-design-level]")?.dataset.designLevel || "";
}

// El resultado puede tener type: "text" | "image" | "chart".
// "chart" se resuelve a una imagen (base64) solo al disparar el análisis,
// para no re-renderizar el SVG en cada tick del polling.
const NO_HELP_SELECTOR = ".footnote, footer, cite, small, [role='note'], [role='doc-footnote'], "
    + "[role='doc-endnotes'], [role='doc-bibliography']";

function extractContent(element) {
    if (!element) return null;

    if (element.tagName === "TABLE") {
        const text = element.innerText?.trim();
        if (!text || text.length < 10) return null;
        // Tipo propio: el backend no le aplica la medida de legibilidad (que
        // es para texto corrido) y deja que el modelo juzgue el nivel.
        return { type: "table", value: text };
    }

    if (element.tagName.toLowerCase() === "svg") {
        return { type: "chart", value: element, context: getVisualContext(element),
                 designLevel: getDesignLevel(element), chartText: getChartText(element) };
    }

    // Títulos (h1–h6): sin ayuda propia. Son cortos, el modelo los juzgaba
    // sin contexto (definió mal "evidencia observacional") y sus términos se
    // repiten en el texto de abajo. Revisión del 2026-10-05: 6 de 26 ayudas
    // eran sobre títulos.
    if (/^H[1-6]$/.test(element.tagName)) return null;

    // Notas al pie y referencias bibliográficas: sin ayuda (la revisión del
    // 2026-10-05 encontró 4 ayudas innecesarias ahí). Se reconocen por el
    // marcado habitual de HTML para notas y bibliografía.
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
// Los estilos inline del SVG usan var(--accent) etc.; al serializarlo fuera
// del documento esas variables no se resuelven, así que se reemplazan por
// su valor computado antes de rasterizar.
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

// Convierte el contenido detectado al payload final que se envía al backend.
// Solo "chart" necesita trabajo async (rasterizar el SVG); el resto pasa igual.
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

// ─── Dónde se coloca el tooltip ───────────────────────────────
// Antes iba siempre debajo del elemento y tapaba el inicio del párrafo
// siguiente (y, mientras estaba visible, mirar ahí contaba como "leer el
// tooltip"). Ahora se prueban, en orden, a la derecha, a la izquierda, debajo
// y arriba del elemento, y se usa la primera posición que no tape otro
// contenido; si ninguna está libre, la que menos tapa. Sirve en cualquier página.
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
    // A los costados se prueba alineado con el inicio y con el final del
    // elemento (a la altura del inicio puede haber un recuadro lateral).
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
    // Si había un ocultamiento pendiente (de un hideTooltipSoon anterior),
    // se cancela: este tooltip nuevo manda.
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

// En vez de ocultarlo de inmediato cuando se confirma que la mirada ya se
// fue del elemento, se le da TOOLTIP_HOLD_MS para que alcances a leerlo.
// Si mientras tanto aparece un tooltip nuevo, showTooltip() cancela este
// timer, así que nunca se pisan entre sí.
function hideTooltipSoon() {
    if (tooltipHideTimer) clearTimeout(tooltipHideTimer);
    tooltipHideTimer = setTimeout(() => {
        tooltipHideTimer = null;
        hideTooltip();
    }, TOOLTIP_HOLD_MS);
}

// Con el Tobii, el tooltip también tiene margen (EDGE_MARGIN_PX): con ~40 px
// de error, al leer cerca de sus bordes la mirada caía justo afuera.
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

    // De dónde salió el nivel: legibilidad INFLESZ (texto), nivel diseñado
    // (figuras con data-design-level) o juicio del modelo.
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

// Términos ya explicados en esta página (primer y segundo nivel): el backend
// no los vuelve a elegir (text_analyzer.choose_terms). Medido con
// evaluation/ab_terminos.py: sin esto se repetían 4 de 24 términos.
// Se llena igual con y sin ayuda visible, para que el sistema funcione igual
// en ambas condiciones.
const definedTermsOnPage = [];

function rememberDefinedTerms(terms) {
    for (const term of terms) {
        if (term && !definedTermsOnPage.includes(term)) definedTermsOnPage.push(term);
    }
}

// ─── Comunicación con backend ─────────────────────────────────
async function analyzeWithBackend(content, dwellTime) {
    activeRequestController?.abort();
    const requestController = new AbortController();
    activeRequestController = requestController;
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

        // El backend descartó este análisis porque llegó uno más nuevo
        // (ya cambió el elemento observado): no hay nada que mostrar ni cachear.
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

// ─── Ayuda pendiente ──────────────────────────────────────────
// Diagnóstico ya recibido para el elemento actual, esperando a que el dwell
// llegue al umbral de su nivel (Medium: 2 s, High: 0.5 s; con relectura,
// 0.5 s). Los umbrales vienen en la respuesta de /analyze.
let pendingHelp      = null;        // { element, diagnosis }
let currentIsRevisit = false;
const elementVisits  = new WeakMap();

// ─── Modelo de lectura: ¿esta persona necesita la ayuda? ──────
// Se crea con READING_POLICY (de /config). Solo aplica a texto corrido con
// sílabas conocidas (llegan con el análisis); en tablas, gráficas e imágenes
// sigue la regla de tiempo fijo. Si /config falla, todo usa tiempo fijo.
let readingModel     = null;
let readingPolicy    = null;
let lastTickAt       = null;
let visitHadSignal   = false;   // hubo señal en esta visita (no adapta el ritmo)
// Fijaciones de la visita en curso (I-DT): cantidad, tiempo total y el punto
// donde empezó la fijación actual (para saber cuándo empieza otra).
let visitFix         = { count: 0, ms: 0, anchor: null };
let lowSignalLogged  = false;   // ya se registró "se habría disparado" en Low

// El ritmo aprendido sigue a la persona entre páginas (misma pestaña).
const PACE_STORAGE_KEY = "gazeReadingPace";

function loadStoredPace() {
    try {
        return parseFloat(sessionStorage.getItem(PACE_STORAGE_KEY));
    } catch (error) {
        return NaN;
    }
}

function storePace(pace) {
    try {
        sessionStorage.setItem(PACE_STORAGE_KEY, String(pace));
    } catch (error) { /* sin almacenamiento: el ritmo se reinicia por página */ }
}

function readingInfo(element) {
    const diagnosis = element ? analysisCache.get(element) : null;
    if (!readingModel || !diagnosis || !diagnosis.syllables) return null;
    return { syllables: diagnosis.syllables, level: diagnosis.complexity };
}

function isTextElement(element) {
    return Boolean(element) && extractContent(element)?.type === "text";
}

// Zona vertical de la mirada dentro del párrafo: "inicio" (primer tercio),
// "medio" o "final" (último tercio). Un bloque de menos de ~3 líneas cuenta
// siempre como "final" (no se distingue arriba de abajo con el Tobii).
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
// Última ayuda mostrada en cada elemento (primer o segundo nivel), para que
// reaparezca si la persona sale un momento y vuelve (ver reshowHelpOnReturn).
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
        // Dónde estaba el tooltip (px de la página), para revisar con la mirada cruda.
        tooltip_rect: tooltipRectOnPage()
    });
    helpState = null;
}

function offerPendingHelp(dwellTime) {
    if (!pendingHelp || pendingHelp.element !== currentObservedElement) return;
    const { diagnosis } = pendingHelp;

    // Texto corrido: decide la conducta (atascado o relectura).
    // Tablas, gráficas, imágenes: tiempo fijo según el nivel.
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
        // Único en la sesión: el contador se reinicia en cada página.
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

    // Texto con regla por conducta: se rearma el modelo (las señales siguientes
    // piden el segundo nivel) y se pide la ayuda ampliada en segundo plano.
    if (decision.rule === "conducta") {
        readingModel.rearm(elementId(currentObservedElement));
        helpLevelGiven.set(currentObservedElement, 1);
        prefetchExpandedHelp(currentObservedElement, diagnosis.concept);
    }

    // Condición "sin ayuda" (sesión intra-sujeto): todo el sistema funciona
    // igual, pero el tooltip no se muestra; se registra la ayuda que se
    // habría mostrado, para comparar los mismos elementos entre condiciones.
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

// Salida corta (< revisit_gap_ms, 5 s) y vuelta al mismo párrafo: es la misma
// lectura (el tiempo sigue sumando), así que la ayuda que ya tenía vuelve a
// aparecer en vez de esperar a que se trabe otra vez (decidido el 2026-10-11:
// con el tooltip oculto, quien volvía enseguida quedaba sin ayuda hasta la
// señal del segundo nivel). Se registra como "help_reshown" con el mismo
// help_id: no cuenta como una ayuda nueva.
function reshowHelpOnReturn(element, readingEvent) {
    const last = lastHelpShown.get(element);
    if (!last || readingEvent !== "continua" || !ExperimentSession.helpEnabled) return;
    showTooltip(last.message, last.mode, element);   // cancela un ocultamiento pendiente
    if (helpState && helpState.id === last.id) return;   // no llegó a ocultarse
    closeHelpLog("reemplazada");
    ExperimentSession.log("help_reshown", { help_id: last.id, el: last.el });
    helpState = { id: last.id, el: last.el, shownAt: Date.now(), gazeInsideMs: 0 };
}

// ─── Condición "a pedido" ──────────────────────────────────────
// En vez de esperar a la conducta, apenas el análisis dice que hay ayuda se
// muestra (en el mismo lugar del tooltip) un botón "Ver ayuda". Si la persona
// hace clic, ve la ayuda; debajo, "Más detalle" da la explicación ampliada.
// La regla automática sigue corriendo en silencio y registra como
// "help_suppressed" dónde habría dado la ayuda: así se compara lo que pide la
// persona con lo que detecta el sistema.
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

// ─── Segundo nivel de ayuda (explicación ampliada) ─────────────
// Si la persona se vuelve a trabar en un párrafo después de la primera ayuda
// (relectura o atascado otra vez), se muestra una explicación más completa:
// 2–3 términos del párrafo y la idea en palabras simples
// (backend/analyzers/expanded_help.py). Se pide en segundo plano apenas se da
// la primera ayuda, para tenerla lista.
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

    // Obtener elemento actual independientemente de si hay fijación
    // Si hay fijación usamos el centroide; si no, con el Tobii, el punto
    // SUAVIZADO (mediana de los últimos GAZE_SMOOTH_MS: quita el temblor del
    // sensor); con mouse, la última posición.
    const smoothed = inputSource === "tobii"
        ? GazeMapping.smoothPoint(gazePoints, Date.now(), GAZE_SMOOTH_MS) : null;
    const referencePoint = idt.isFixation
        ? idt.centroid
        : (smoothed || { x: mouseX, y: mouseY });

    // Margen de parpadeo (solo en modo Tobii): si hace poco que llegó la
    // última lectura VÁLIDA, un parpadeo en curso no debe resetear nada —
    // se sigue usando la última posición conocida, tal cual. Si ya pasó
    // el margen, se asume que de verdad se dejó de mirar la pantalla.
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
    // Margen en los bordes (solo Tobii, 2026-10-20): si la mirada sale un poco
    // del elemento actual (hasta EDGE_MARGIN_PX) y cae en espacio en blanco,
    // sigue contando como ese elemento. Si entra en OTRO elemento, cambia normal.
    if (inputSource === "tobii" && !trackingLost && !candidateElement && currentObservedElement
        && GazeMapping.insideRect(currentObservedElement.getBoundingClientRect(), referencePoint, EDGE_MARGIN_PX)) {
        candidateElement = currentObservedElement;
    }

    // Tiempo con la mirada dentro del tooltip (resolución: un tick de 100 ms).
    const gazeOnTooltip = !trackingLost && isPointInsideTooltip(referencePoint);
    if (helpState && gazeOnTooltip) {
        helpState.gazeInsideMs += POLL_INTERVAL_MS;
    }
    // Mientras se mira el tooltip, no se oculta (2026-10-20: si la mirada pasaba
    // por otro elemento camino al tooltip, empezaba la cuenta para ocultarlo y
    // leerlo ya no la detenía). Al dejar de mirarlo, vuelve a contar el tiempo
    // de permanencia, salvo que la mirada esté en el elemento de esa ayuda.
    if (gazeOnTooltip) {
        if (tooltipHideTimer) { clearTimeout(tooltipHideTimer); tooltipHideTimer = null; }
        wasOnTooltip = true;
    } else if (wasOnTooltip) {
        wasOnTooltip = false;
        const helpEl = helpState?.el ?? (askState?.element ? elementId(askState.element) : null);
        const onHelpElement = currentObservedElement && helpEl === elementId(currentObservedElement);
        if (!onHelpElement && adaptiveTooltip.style.display !== "none") hideTooltipSoon();
    }

    // Histéresis de cambio de elemento (solo en modo Tobii): el Tobii 5 no es
    // un tracker de precisión de laboratorio, tiene ruido esperado de varias
    // decenas de píxeles — "miro un punto y salta a otro lado y vuelve" es
    // justo ese ruido, no un problema de calibración. En vez de resetear el
    // dwell/tooltip apenas el punto crudo se mueve, se exige que el nuevo
    // candidato se mantenga por ELEMENT_SWITCH_GRACE_MS antes de confirmarlo;
    // si la mirada vuelve al elemento original antes de eso, no pasó nada
    // (el tooltip tampoco se oculta). En modo mouse el comportamiento es
    // exactamente el de antes (sin histéresis).
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

    // Si cambió de elemento → resetear dwell time
    if (fixatedElement !== currentObservedElement) {
        logElementExit();
        activeRequestController?.abort();
        currentObservedElement      = fixatedElement;
        observationStartTime        = Date.now();
        analysisTriggered           = false;
        hadFixationOnCurrentElement = false;  // ← línea nueva
        pendingHelp                 = null;
        visitHadSignal              = false;
        visitFix                    = { count: 0, ms: 0, anchor: null };
        lowSignalLogged             = false;

        // Relectura: volver a un elemento ya mirado (regresión) es una señal
        // conocida de dificultad de lectura; adelanta la ayuda de nivel Medium.
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
        // En modo Tobii se da tiempo de lectura en vez de ocultar de golpe;
        // en modo mouse se deja el comportamiento original (inmediato).
        // Al apartar la mirada, el tooltip se mantiene TOOLTIP_HOLD_MS (2.5 s)
        // en todas las condiciones y con mouse o Tobii (2026-10-20: antes, en
        // "automática" con mouse se ocultaba al instante). Si la mirada vuelve
        // al párrafo o al tooltip en ese lapso, sigue visible (reshowHelpOnReturn
        // y showTooltip cancelan el ocultamiento pendiente).
        hideTooltipSoon();
        // Volvió al mismo elemento cuya ayuda (o botón "Ver ayuda") sigue a la
        // vista: se cancela el ocultamiento (párrafos, tablas y gráficas).
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

    // Calcular dwell time — corre siempre que el elemento no cambie
    const dwellTime = Date.now() - observationStartTime;

    // Actualizar UI
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

    // Registrar si hubo fijación en este elemento
    if (idt.isFixation) {
        hadFixationOnCurrentElement = true;
    }

    const now = Date.now();
    const dt = lastTickAt === null ? 0 : Math.min(now - lastTickAt, POLL_INTERVAL_MS * 2.5);
    lastTickAt = now;

    // Métricas de fijaciones de la visita (se registran al salir): empieza
    // una fijación nueva si antes no había o si la mirada se alejó más que la
    // dispersión máxima del punto donde empezó la actual (criterio I-DT; si
    // se compara con el tick anterior, un deslizamiento lento se contaría
    // como una sola fijación larguísima).
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

    // Modelo de lectura: suma el tiempo en el párrafo (no mientras lee el
    // tooltip ni sin seguimiento) y marca en qué parte del párrafo está la mirada.
    if (readingModel && isTextElement(currentObservedElement) && !trackingLost && !isReadingTooltip) {
        const key = elementId(currentObservedElement);
        const info = readingInfo(currentObservedElement);
        readingModel.tick(key, dt, gazeZone(currentObservedElement, referencePoint), info, idt.isFixation);
        // Nivel Low: no hay ayuda, pero se registra si la conducta la habría pedido.
        // Segundo nivel: ya tuvo la primera ayuda y se vuelve a trabar.
        if (info && helpLevelGiven.get(currentObservedElement)) {
            const sig = readingModel.signal(key, info);
            if (sig) offerLevel2(currentObservedElement, sig, dwellTime);
        }
        if (info && info.level === "Low" && !lowSignalLogged) {
            const sig = readingModel.signal(key, info);
            if (sig) {
                lowSignalLogged = true;
                visitHadSignal = true;
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

    // En modo mouse, exigir una fijación IDT evita que "pasar por encima"
    // de un elemento grande cuente como leerlo. Con mirada real esa
    // exigencia sobra: leer texto implica saltar de palabra en palabra
    // (dispersión alta aunque sí se esté leyendo), y ya se exige que la
    // mirada se quede en el MISMO elemento del DOM por 500ms seguidos —
    // eso ya es la señal de atención; no hace falta además una fijación
    // a nivel de píxel crudo.
    const fixationRequirementMet = inputSource === "tobii" || hadFixationOnCurrentElement;

    // Si ya hay una ayuda analizada esperando su umbral de dwell, ofrecerla.
    offerPendingHelp(dwellTime);

    // Disparar análisis si hubo fijación en algún momento Y se superó el umbral
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
                const payload = await resolveContentPayload(content);

                if (!payload || currentObservedElement !== elementAtTrigger) return;
                // Contexto: solo el subtítulo de la sección, y solo para texto y
                // tablas. Medido (evaluation/ab_contexto.py, 2026-10-06): con el
                // título de la página el modelo elegía términos del título que no
                // estaban en el párrafo (un párrafo High se quedaba sin ayuda), y
                // en fotos y gráficas el contexto empeoraba la ayuda.
                if (payload.type === "text" || payload.type === "table") {
                    payload.section = getSectionHeading(elementAtTrigger);
                }

                diagnosis = await analyzeWithBackend(payload, dwellTime / 1000);

                // No cachear errores transitorios de red/backend — si se
                // cacheara, un glitch puntual dejaría ese elemento sin
                // ayuda por el resto de la sesión.
                if (diagnosis && diagnosis.concept !== "Error") {
                    analysisCache.set(elementAtTrigger, diagnosis);
                }
            }

            if (!diagnosis || currentObservedElement !== elementAtTrigger) return;

            ExperimentSession.log("analysis", {
                el: elementId(elementAtTrigger),
                from_cache: Boolean(cachedBefore),
                complexity: diagnosis.complexity,
                difficulty_source: diagnosis.difficulty_source,
                inflesz: diagnosis.inflesz ?? null,
                llm_complexity: diagnosis.llm_complexity ?? null,
                action: diagnosis.action,
                help_blocked: diagnosis.help_blocked ?? null,
                section: getSectionHeading(elementAtTrigger),
                concept: diagnosis.concept,
                explanation: diagnosis.explanation,
                processing_time_s: cachedBefore ? 0 : diagnosis.processing_time ?? null
            });
            updateAnalysisPanel(diagnosis);

            if (ExperimentSession.onDemand && diagnosis.action === "tooltip" && diagnosis.explanation) {
                offerHelpButton(elementAtTrigger, diagnosis);
            }
            if (diagnosis.action === "tooltip" && diagnosis.explanation) {
                // El tooltip aparece cuando el dwell alcance el umbral que la
                // política de ayuda (backend/decision_engine.py) fija para
                // este nivel; puede ser ya mismo si ese tiempo ya pasó.
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

// ─── Fuente de coordenadas: mouse (pruebas) o Tobii 5 (real) ──
// Se decide UNA SOLA VEZ al arrancar el backend (variable de entorno
// GAZE_INPUT_SOURCE, ver app.py) y el frontend solo la lee de /config.
// No cambia en vivo: para pruebas de laboratorio es más seguro fijarla
// antes de correr la sesión que dejar un switch que alguien pueda tocar
// a mitad de la prueba. La IDT/dwell no sabe ni le importa de dónde
// vienen los puntos: solo consume gazePoints.
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

// Conexión por push (WebSocket) al backend: cada punto que el Tobii
// entrega (~90Hz) llega aquí en cuanto el bridge lo manda, en vez de que
// el frontend tenga que ir a preguntar cada 100ms y perderse casi todas
// las muestras entre una preguntada y la siguiente. Si el backend o el
// bridge de C++ todavía no están arriba, reintenta solo cada 2s.
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
            // Proporción de pantalla -> página (según este equipo y ventana) y
            // corrección de la comprobación de 5 puntos (gaze_mapping.js).
            const p = GazeMapping.applyCorrection(GazeMapping.normalizedToClient(data.nx, data.ny, window),
                                                  gazeCorrection);
            pushGazePoint(p.x, p.y, Date.now());
        } else if (data?.valid && typeof data.x === "number" && typeof data.y === "number") {
            pushGazePoint(data.x, data.y, Date.now());   // fuente sin proporción (simulate_gaze.py)
        } else {
            // Muestra inválida (parpadeo o pérdida de seguimiento): se
            // registra para medir la calidad del seguimiento por sesión.
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

// Lee la fuente configurada en el backend (fijada al arrancar app.py).
// Si el backend no responde, se queda en "mouse" por defecto.
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

// ─── Arranque ───────────────────────────────────────────────────
// ─── Registro de la página (solo con sesión experimental) ─────
const pageEnteredAt = Date.now();

function logElementExit() {
    if (!currentObservedElement || observationStartTime === null) return;
    const key = elementId(currentObservedElement);
    ExperimentSession.log("element_exit", {
        el: key,
        dwell_ms: Date.now() - observationStartTime,
        // Fijaciones (I-DT) en la visita: con datos del Tobii se verá qué
        // parte de la lectura detecta como fijación y si las fijaciones
        // largas anticipan lo que la persona marca como difícil.
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
            storePace(paceUpdate.new);
            ExperimentSession.log("pace_update", {
                el: key, old: Math.round(paceUpdate.old), new: Math.round(paceUpdate.new),
                observed: Math.round(paceUpdate.observed)
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
    // El layout se toma con la página ya cargada (las imágenes cambian
    // posiciones) y de nuevo si cambia el tamaño de la ventana.
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

// Indicador de sesión y condición en el panel de debug (si está visible).
function renderSessionIndicator() {
    const debugHeader = document.querySelector(".debug-header");
    if (!debugHeader) return;
    const indicator = document.createElement("div");
    indicator.className = "debug-section";
    const label = ExperimentSession.active
        ? `${ExperimentSession.session.participant} · ${ExperimentSession.condition === "sin_ayuda" ? "sin ayuda" : "con ayuda"}`
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

    // El loop ya NO mete datos cuando la fuente es Tobii: esos puntos
    // llegan solos y de inmediato por el WebSocket (connectTobiiSocket).
    // Este intervalo solo evalúa, cada 100ms, qué hacer con lo que ya
    // se acumuló en gazePoints (igual que antes).
    setInterval(() => {
        if (inputSource === "mouse") {
            sampleStationaryPointer();
        }
        processObservation();
    }, POLL_INTERVAL_MS);
})();