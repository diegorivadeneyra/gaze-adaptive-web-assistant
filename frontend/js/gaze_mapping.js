// ═══════════════════════════════════════════════════════════════
// De la mirada del Tobii (proporción de pantalla, 0–1) a un punto de la página:
// se pasa a píxeles del navegador y se resta dónde empieza la página (ventana y
// barras). El error restante lo corrige la comprobación de 5 puntos
// (calibracion.html): una recta por eje, x' = ax·x + bx, por persona.
// Módulo puro: lo usan gaze.js, calibracion.js y tests/test_gaze_mapping.js.
// ═══════════════════════════════════════════════════════════════
(function (root) {
    const CORRECTION_KEY = "gazeCorrection";

    // Dónde empieza el área de la página dentro de la pantalla (px CSS).
    function contentOrigin(win) {
        const border = Math.max(0, (win.outerWidth - win.innerWidth) / 2);
        return {
            left: win.screenX + border,
            top: win.screenY + Math.max(0, win.outerHeight - win.innerHeight - border)
        };
    }

    // Proporción de pantalla (0–1) -> punto de la página, sin corrección.
    function normalizedToClient(nx, ny, win) {
        const origin = contentOrigin(win);
        return { x: nx * win.screen.width - origin.left, y: ny * win.screen.height - origin.top };
    }

    function applyCorrection(point, c) {
        if (!c) return point;
        return { x: c.ax * point.x + c.bx, y: c.ay * point.y + c.by };
    }

    // Recta por mínimos cuadrados target = a·measured + b. Si la pendiente es
    // poco creíble (pocos puntos o datos raros), solo se corrige el desfase.
    function fitAxis(measured, target) {
        const n = measured.length;
        const mean = arr => arr.reduce((s, v) => s + v, 0) / arr.length;
        const mx = mean(measured), my = mean(target);
        let sxy = 0, sxx = 0;
        for (let i = 0; i < n; i++) {
            sxy += (measured[i] - mx) * (target[i] - my);
            sxx += (measured[i] - mx) ** 2;
        }
        let a = sxx > 0 ? sxy / sxx : 1;
        if (!(a >= 0.8 && a <= 1.25)) a = 1;      // solo desfase
        return { a, b: my - a * mx };
    }

    // points: [{ target: {x,y}, measured: {x,y} }] -> corrección y errores (px).
    function fitCorrection(points) {
        const fx = fitAxis(points.map(p => p.measured.x), points.map(p => p.target.x));
        const fy = fitAxis(points.map(p => p.measured.y), points.map(p => p.target.y));
        const correction = { ax: fx.a, bx: fx.b, ay: fy.a, by: fy.b };
        const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
        const before = points.reduce((s, p) => s + dist(p.measured, p.target), 0) / points.length;
        const after = points.reduce((s, p) => s + dist(applyCorrection(p.measured, correction), p.target), 0) / points.length;
        return { correction, errorBeforePx: Math.round(before), errorAfterPx: Math.round(after) };
    }

    // Mediana de los últimos windowMs: quita el temblor del Tobii (20–40 px).
    function smoothPoint(points, now, windowMs) {
        const recent = points.filter(p => p.timestamp >= now - windowMs);
        if (!recent.length) return null;
        return { x: median(recent.map(p => p.x)), y: median(recent.map(p => p.y)) };
    }

    // ¿El punto está dentro del rectángulo ampliado en `margin` px por lado?
    function insideRect(rect, p, margin = 0) {
        return p.x >= rect.left - margin && p.x <= rect.right + margin
            && p.y >= rect.top - margin && p.y <= rect.bottom + margin;
    }

    function median(values) {
        const v = [...values].sort((a, b) => a - b);
        const m = Math.floor(v.length / 2);
        return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
    }

    function loadCorrection(storage) {
        try { return JSON.parse(storage.getItem(CORRECTION_KEY)); } catch (error) { return null; }
    }

    function saveCorrection(storage, c) {
        try { c ? storage.setItem(CORRECTION_KEY, JSON.stringify(c)) : storage.removeItem(CORRECTION_KEY); }
        catch (error) { /* sin almacenamiento: se usa sin corrección */ }
    }

    const api = { contentOrigin, normalizedToClient, applyCorrection, fitAxis, fitCorrection, median,
                  smoothPoint, insideRect,
                  loadCorrection, saveCorrection, CORRECTION_KEY };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else root.GazeMapping = api;
})(typeof window !== "undefined" ? window : globalThis);
