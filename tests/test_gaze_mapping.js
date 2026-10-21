// Pruebas de frontend/js/gaze_mapping.js (de la mirada del Tobii a la página).
// Uso: node tests/test_gaze_mapping.js
const assert = require("assert");
const M = require("../frontend/js/gaze_mapping.js");

let passed = 0;
function test(name, fn) { fn(); passed++; console.log(`  ok  ${name}`); }
const near = (a, b, tol = 0.5) => assert.ok(Math.abs(a - b) <= tol, `${a} ≉ ${b}`);

// Ventanas típicas (valores en px CSS, como los da el navegador).
const pcF11      = { screen: { width: 1920, height: 1080 }, screenX: 0, screenY: 0,
                     outerWidth: 1920, innerWidth: 1920, outerHeight: 1080, innerHeight: 1080 };
const pcVentana  = { screen: { width: 1920, height: 1080 }, screenX: 0, screenY: 0,
                     outerWidth: 1920, innerWidth: 1920, outerHeight: 1040, innerHeight: 937 };
// Laptop 1920×1080 con la escala de Windows al 125 %: el navegador ve 1536×864.
const laptop125  = { screen: { width: 1536, height: 864 }, screenX: 0, screenY: 0,
                     outerWidth: 1536, innerWidth: 1536, outerHeight: 824, innerHeight: 730 };

test("pantalla completa (F11): la página empieza en (0,0)", () => {
    const o = M.contentOrigin(pcF11);
    assert.deepStrictEqual(o, { left: 0, top: 0 });
    const p = M.normalizedToClient(0.5, 0.5, pcF11);
    near(p.x, 960); near(p.y, 540);
});

test("ventana con barras del navegador: se resta su altura (antes el punto caía ~103 px abajo)", () => {
    const o = M.contentOrigin(pcVentana);
    near(o.top, 103);
    const p = M.normalizedToClient(0.5, 0.5, pcVentana);
    near(p.x, 960); near(p.y, 540 - 103);
});

test("laptop con escala 125 %: se usa el tamaño de pantalla que ve el navegador", () => {
    const p = M.normalizedToClient(0.5, 0.5, laptop125);
    near(p.x, 768); near(p.y, 432 - 94);
});

test("ventana no maximizada (movida): se resta su posición", () => {
    const w = { ...pcVentana, screenX: 200, screenY: 100 };
    const p = M.normalizedToClient(0.5, 0.5, w);
    near(p.x, 960 - 200); near(p.y, 540 - 100 - 103);
});

test("corrección de 5 puntos: recupera un desfase y una escala", () => {
    const targets = [[128, 100], [1152, 100], [640, 400], [128, 700], [1152, 700]];
    // Mirada medida: 5 % más ancha, 100 px más abajo y 20 px a la derecha, con ruido.
    const noise = [[3, -2], [-2, 4], [1, 1], [-3, 2], [2, -3]];
    const points = targets.map(([x, y], i) => ({
        target: { x, y },
        measured: { x: x * 1.05 + 20 + noise[i][0], y: y + 100 + noise[i][1] }
    }));
    const fit = M.fitCorrection(points);
    assert.ok(fit.errorBeforePx > 90, `antes ${fit.errorBeforePx}`);
    assert.ok(fit.errorAfterPx <= 5, `después ${fit.errorAfterPx}`);
});

test("pendiente absurda (datos raros): solo se corrige el desfase", () => {
    const f = M.fitAxis([500, 501, 499, 500, 500], [100, 900, 500, 100, 900]);
    assert.strictEqual(f.a, 1);
});

test("mediana robusta a un punto suelto (parpadeo, salto)", () => {
    assert.strictEqual(M.median([10, 11, 12, 13, 900]), 12);
});

test("sin corrección guardada, el punto no cambia", () => {
    assert.deepStrictEqual(M.applyCorrection({ x: 5, y: 7 }, null), { x: 5, y: 7 });
});

console.log(`\n${passed} pruebas OK`);
