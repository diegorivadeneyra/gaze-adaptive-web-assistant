let mouseX = 0;
let mouseY = 0;
let currentObservedElement = null;
let observationStartTime = null;
let analysisTriggered = false;

const gazeInfo = document.getElementById("gaze-info");
const currentElementBox =
    document.getElementById("current-element");

const contentTypeBox =
    document.getElementById("content-type");

const dwellTimeBox =
    document.getElementById("dwell-time");

const contentInfoBox =
    document.getElementById("content-info");

const analysisResultBox =
    document.getElementById("analysis-result");

const assistantActionBox =
    document.getElementById("assistant-action");

const adaptiveTooltip =
    document.getElementById("adaptive-tooltip");

function classifyElement(element) {

    const tag = element.tagName;

    switch(tag) {

        case "P":
        case "SPAN":
        case "H1":
        case "H2":
        case "H3":
            return "Texto";

        case "IMG":
            return "Imagen";

        case "BUTTON":
            return "Botón";

        case "INPUT":
        case "TEXTAREA":
            return "Formulario";

        default:
            return "Otro";
    }
}

function extractContent(element) {

    if (!element)
        return "Sin contenido";

    const tag = element.tagName;

    switch(tag) {

        case "P":
        case "SPAN":
        case "H1":
        case "H2":
        case "H3":

            return {
                type: "text",
                value: element.innerText
            };

        case "IMG":
            return {
                type: "image",
                value: element.src
            };

        case "BUTTON":

            return {
                type: "text",
                value: element.textContent
            };

        default:

            return "Contenido no soportado";
    }
}

function showTooltip(message) {

    console.log("MOSTRANDO TOOLTIP");

    adaptiveTooltip.innerText = message;

    adaptiveTooltip.style.display = "block";
}

function hideTooltip() {

    adaptiveTooltip.style.display = "none";
}

async function analyzeWithBackend(content,dwellTime) {

    try {

        const response = await fetch(
            "http://127.0.0.1:5000/analyze",
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    content: content.value,
                    content_type: content.type,
                    dwell_time: dwellTime
                })
            }
        );

        const result = await response.json();

        return result;

    } catch(error) {

        console.error(error);

        return {
            concept: "Error",
            complexity: "Error",
            needs_assistance: false,
            explanation: "Error de conexión con el backend",
            action: "none"
        };
    }
}

async function processObservation() {

    if (!currentObservedElement)
        return;

    const contentType =
        classifyElement(currentObservedElement);

    let dwellTime = 0;

    if (observationStartTime) {

        dwellTime =
            (Date.now() - observationStartTime) / 1000;
    }

    gazeInfo.innerText =
        `X: ${mouseX} | Y: ${mouseY}`;

    currentElementBox.innerText =
        `Elemento: ${currentObservedElement.tagName}`;

    contentTypeBox.innerText =
        `Tipo: ${contentType}`;

    dwellTimeBox.innerText =
        `Dwell Time: ${dwellTime.toFixed(1)} s`;

    if (dwellTime >= 1.5 && !analysisTriggered) {

        analysisTriggered = true;

        const content =
            extractContent(currentObservedElement);

        if (content.type === "image") {

            console.log(
                "IMAGE URL:",
                content.value
            );
        }
        contentInfoBox.innerText =
            `Contenido:\n${content.value}`;

        const diagnosis =
            await analyzeWithBackend(content,dwellTime);
        console.log("RESPUESTA BACKEND:");
        console.log(diagnosis);

        console.log("ACTION:", diagnosis.action);
        console.log("EXPLANATION:", diagnosis.explanation);
        if (diagnosis.action === "tooltip") {

            showTooltip(
                diagnosis.explanation
            );
        }
        
        analysisResultBox.innerText =
        `
        Concepto:
        ${diagnosis.concept}

        Complejidad:
        ${diagnosis.complexity}

        Necesita ayuda:
        ${diagnosis.needs_assistance}
        `;
    }
}

document.addEventListener("mousemove", (event) => {

    mouseX = event.clientX;
    mouseY = event.clientY;

    const hoveredElement =
        document.elementFromPoint(mouseX, mouseY);

    if (hoveredElement !== currentObservedElement) {

        currentObservedElement = hoveredElement;

        observationStartTime = Date.now();

        analysisTriggered = false;

        hideTooltip();
    }
});

setInterval(() => {

    processObservation();

}, 100);