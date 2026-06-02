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

            return element.innerText;

        case "IMG":

            return element.src;

        case "BUTTON":

            return element.textContent;

        default:

            return "Contenido no soportado";
    }
}

function analyzeContent(content) {

    const text =
        content.toLowerCase();

    if (
        text.includes("criptografía") ||
        text.includes("seguridad") ||
        text.includes("cifrado")
    ) {

        return {
            topic: "Seguridad Informática",
            difficulty: "Media"
        };
    }

    if (
        text.includes("inteligencia artificial") ||
        text.includes("machine learning")
    ) {

        return {
            topic: "Inteligencia Artificial",
            difficulty: "Alta"
        };
    }

    return {
        topic: "Desconocido",
        difficulty: "Desconocida"
    };
}

document.addEventListener("mousemove", (event) => {

    // Actualizar coordenadas primero
    mouseX = event.clientX;
    mouseY = event.clientY;

    // Obtener elemento actual
    const hoveredElement =
        document.elementFromPoint(mouseX, mouseY);

    // Si cambió de elemento
    if (hoveredElement !== currentObservedElement) {

        currentObservedElement = hoveredElement;

        observationStartTime = Date.now();
        analysisTriggered = false;

    }

    // Calcular tipo
    const contentType =
        classifyElement(hoveredElement);

    // Calcular dwell
    let dwellTime = 0;

    if (observationStartTime) {
        console.log(observationStartTime);
        console.log(Date.now());
        dwellTime =
            (Date.now() - observationStartTime) / 1000;

    }

    // Actualizar paneles
    gazeInfo.innerText =
        `X: ${mouseX} | Y: ${mouseY}`;

    currentElementBox.innerText =
        `Elemento: ${hoveredElement.tagName}`;

    contentTypeBox.innerText =
        `Tipo: ${contentType}`;
    console.log(dwellTimeBox);
    console.log(contentTypeBox);
    console.log(currentElementBox);
    console.log(gazeInfo);
    dwellTimeBox.innerText =
        `Dwell Time: ${dwellTime.toFixed(1)} s`;

    // Umbral de activación
    if (dwellTime >= 1.5 && !analysisTriggered) {
        analysisTriggered = true;
        const content = extractContent(currentObservedElement);
        const diagnosis = analyzeContent(content);

        contentInfoBox.innerText =
            `Contenido:\n${content}`;

        analysisResultBox.innerText =
            `
            Tema: ${diagnosis.topic}

            Dificultad:
            ${diagnosis.difficulty}
            `;
    }

});