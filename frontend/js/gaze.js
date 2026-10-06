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
const TOOLTIP_HOLD_MS       = 2500;

// ─── Estado ──────────────────────────────────────────────────
let mouseX                  = 0;
let mouseY                  = 0;
let lastValidGazeAt         = null;
let pointerActive            = false;
let gazePoints              = [];   // buffer de puntos para IDT
let currentFixation         = null; // fijación activa actual
let currentObservedElement  = null;
let pendingElement          = null; // candidato a nuevo elemento (aún sin confirmar)
let pendingElementSince     = null; // desde cuándo se viene viendo ese candidato
let previousHighlighted     = null;
let observationStartTime    = null;
let analysisTriggered       = false;
let isAnalyzing             = false;
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
if (new URLSearchParams(window.location.search).get("debug") === "0") {
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

// Nivel diseñado de una figura (atributo data-design-level en ella o en su
// contenedor). Si existe, el backend lo usa en vez del juicio del modelo.
// (No es data-level: ese ya lo usa <body> para el estilo de la página.)
function getDesignLevel(element) {
    return element.closest("[data-design-level]")?.dataset.designLevel || "";
}

// El resultado puede tener type: "text" | "image" | "chart".
// "chart" se resuelve a una imagen (base64) solo al disparar el análisis,
// para no re-renderizar el SVG en cada tick del polling.
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
                 designLevel: getDesignLevel(element) };
    }

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
            designLevel: content.designLevel }
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

function showTooltip(message, mode, element) {
    if (!message || !adaptiveTooltip) return;
    // Si había un ocultamiento pendiente (de un hideTooltipSoon anterior),
    // se cancela: este tooltip nuevo manda.
    if (tooltipHideTimer) {
        clearTimeout(tooltipHideTimer);
        tooltipHideTimer = null;
    }
    const icon = mode === "summary" ? "📋" : "💡";
    adaptiveTooltip.innerText = `${icon} ${message}`;
    adaptiveTooltip.style.display = "block";

    if (element) {
        const rect = element.getBoundingClientRect();
        const top  = rect.bottom + window.scrollY + 10;
        const left = Math.min(
            Math.max(rect.left + window.scrollX, 12),
            window.innerWidth - 320
        );
        adaptiveTooltip.style.top  = `${top}px`;
        adaptiveTooltip.style.left = `${left}px`;
    }
}

function hideTooltip() {
    if (tooltipHideTimer) {
        clearTimeout(tooltipHideTimer);
        tooltipHideTimer = null;
    }
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

function isPointInsideTooltip(point) {
    if (!adaptiveTooltip || adaptiveTooltip.style.display === "none") {
        return false;
    }

    const rect = adaptiveTooltip.getBoundingClientRect();
    return point.x >= rect.left && point.x <= rect.right
        && point.y >= rect.top && point.y <= rect.bottom;
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
                design_level: content.designLevel || ""
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

function offerPendingHelp(dwellTime) {
    if (!pendingHelp || pendingHelp.element !== currentObservedElement) return;
    const { diagnosis } = pendingHelp;
    const required = (currentIsRevisit
        ? diagnosis.revisit_min_dwell_ms
        : diagnosis.min_dwell_ms) ?? 0;
    if (dwellTime < required) return;

    showTooltip(diagnosis.explanation, diagnosis.mode, currentObservedElement);
    pendingHelp = null;
}

// ─── Proceso principal ────────────────────────────────────────
async function processObservation() {
    const idt = runIDT(gazePoints);

    if (gazeInfo)
        gazeInfo.innerText = idt.isFixation
            ? `Fijación · (${idt.centroid?.x}, ${idt.centroid?.y})`
            : `Movimiento · dispersión: ${idt.dispersion?.toFixed(0)}px`;

    // Obtener elemento actual independientemente de si hay fijación
    // Si hay fijación usamos el centroide, si no usamos última posición conocida
    const referencePoint = idt.isFixation
        ? idt.centroid
        : { x: mouseX, y: mouseY };

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
    const candidateElement = isReadingTooltip
        ? currentObservedElement
        : getContentElement(rawElement);

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
        activeRequestController?.abort();
        currentObservedElement      = fixatedElement;
        observationStartTime        = Date.now();
        analysisTriggered           = false;
        isAnalyzing                 = false;
        hadFixationOnCurrentElement = false;  // ← línea nueva
        pendingHelp                 = null;

        // Relectura: volver a un elemento ya mirado (regresión) es una señal
        // conocida de dificultad de lectura; adelanta la ayuda de nivel Medium.
        if (fixatedElement) {
            const visits = (elementVisits.get(fixatedElement) || 0) + 1;
            elementVisits.set(fixatedElement, visits);
            currentIsRevisit = visits >= 2;
        } else {
            currentIsRevisit = false;
        }
        // En modo Tobii se da tiempo de lectura en vez de ocultar de golpe;
        // en modo mouse se deja el comportamiento original (inmediato).
        if (inputSource === "tobii") {
            hideTooltipSoon();
        } else {
            hideTooltip();
        }
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
        isAnalyzing       = true;
        setStatus("analyzing");

        const elementAtTrigger = currentObservedElement;

        try {
            let diagnosis = analysisCache.get(elementAtTrigger);

            if (!diagnosis) {
                const payload = await resolveContentPayload(content);

                if (!payload || currentObservedElement !== elementAtTrigger) return;

                diagnosis = await analyzeWithBackend(payload, dwellTime / 1000);

                // No cachear errores transitorios de red/backend — si se
                // cacheara, un glitch puntual dejaría ese elemento sin
                // ayuda por el resto de la sesión.
                if (diagnosis && diagnosis.concept !== "Error") {
                    analysisCache.set(elementAtTrigger, diagnosis);
                }
            }

            if (!diagnosis || currentObservedElement !== elementAtTrigger) return;

            updateAnalysisPanel(diagnosis);

            if (diagnosis.action === "tooltip" && diagnosis.explanation) {
                // El tooltip aparece cuando el dwell alcance el umbral que la
                // política de ayuda (backend/decision_engine.py) fija para
                // este nivel; puede ser ya mismo si ese tiempo ya pasó.
                pendingHelp = { element: elementAtTrigger, diagnosis };
                offerPendingHelp(Date.now() - observationStartTime);
            }
        } finally {
            isAnalyzing = false;
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
const CONFIG_URL = "http://127.0.0.1:5000/config";
const GAZE_WS_URL = "ws://127.0.0.1:5600";

function pushGazePoint(x, y, timestamp) {
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
        if (data?.valid && typeof data.x === "number" && typeof data.y === "number") {
            pushGazePoint(data.x, data.y, Date.now());
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
        }
    } catch (error) {
        console.warn("[gaze] No se pudo leer /config; usando 'mouse' por defecto.");
    }
    renderInputSourceIndicator();
}

// ─── Arranque ───────────────────────────────────────────────────
(async function init() {
    await loadInputSourceConfig();

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