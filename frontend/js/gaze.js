let mouseX = 0;
let mouseY = 0;
let currentObservedElement = null;
let observationStartTime = null;

const gazeInfo = document.getElementById("gaze-info");
const currentElementBox =
    document.getElementById("current-element");

const contentTypeBox =
    document.getElementById("content-type");

const dwellTimeBox =
    document.getElementById("dwell-time");

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
    if (dwellTime >= 2) {

        console.log("ACTIVAR ANALISIS");

    }

});