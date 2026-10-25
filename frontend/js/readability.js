// ═══════════════════════════════════════════════════════════════
// Sílabas y nivel INFLESZ en el navegador: copia exacta de
// backend/analyzers/readability.py (tests/test_readability.js comprueba que
// coincidan). Permite al modelo de lectura conocer el párrafo sin esperar al
// análisis del backend.
// ═══════════════════════════════════════════════════════════════
(function (root) {
    const WORD_RE = /[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+/g;
    const SENTENCE_SPLIT_RE = /(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÑ¿¡(\[])/;
    const MIN_WORDS = 8;            // con menos, la fórmula es inestable (decide el modelo)
    const INFLESZ_LOW_MIN = 55;     // >= 55 normal o más fácil -> Low
    const INFLESZ_MEDIUM_MIN = 40;  // 40–55 algo difícil -> Medium; < 40 -> High

    const STRONG = new Set("aeoáéóàèò");
    const WEAK = new Set("iuü");
    const ACCENTED_WEAK = new Set("íú");
    const isVowel = ch => STRONG.has(ch) || WEAK.has(ch) || ACCENTED_WEAK.has(ch);

    // Sílabas de una palabra en español (diptongos y triptongos = una sílaba; hiatos, dos).
    function countSyllables(word) {
        let w = word.toLowerCase()
            .replace(/qu/g, "q")                 // la u de que/qui no suena
            .replace(/gu([eiéí])/g, "g$1");      // ni la de gue/gui (salvo ü)
        if (w.endsWith("y")) w = w.slice(0, -1) + "i";   // y final funciona como vocal débil
        let syllables = 0;
        let previous = null;
        for (const ch of w) {
            if (!isVowel(ch)) { previous = null; continue; }
            if (previous === null) {
                syllables++;
            } else if ((STRONG.has(previous) && STRONG.has(ch))
                       || ACCENTED_WEAK.has(previous) || ACCENTED_WEAK.has(ch)) {
                syllables++;                     // hiato
            }
            previous = ch;
        }
        return Math.max(syllables, 1);
    }

    function words(text) {
        return text.match(WORD_RE) || [];
    }

    function countTextSyllables(text) {
        return words(text).reduce((sum, w) => sum + countSyllables(w), 0);
    }

    // {inflesz, level, words, sentences} o null si el texto es muy corto.
    function computeReadability(text) {
        const ws = words(text);
        if (ws.length < MIN_WORDS) return null;
        const sentences = text.trim().split(SENTENCE_SPLIT_RE).filter(s => s.trim());
        const nSentences = Math.max(sentences.length, 1);
        const syllables = ws.reduce((sum, w) => sum + countSyllables(w), 0);
        const inflesz = 206.835 - 62.3 * (syllables / ws.length) - (ws.length / nSentences);
        const level = inflesz >= INFLESZ_LOW_MIN ? "Low" : inflesz >= INFLESZ_MEDIUM_MIN ? "Medium" : "High";
        return { inflesz: Math.round(inflesz * 10) / 10, level, words: ws.length, sentences: nSentences };
    }

    const api = { countSyllables, countTextSyllables, computeReadability };
    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    } else {
        root.Readability = api;
    }
})(typeof window !== "undefined" ? window : globalThis);
