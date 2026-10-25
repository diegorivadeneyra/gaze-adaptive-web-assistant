// Comprueba que frontend/js/readability.js (navegador) calcula EXACTAMENTE lo
// mismo que backend/analyzers/readability.py: sílabas, INFLESZ y nivel de
// todos los textos de las 3 páginas (evaluation/assets/bloques_lectura.json)
// y de palabras con diptongos, hiatos, qu/gu/ü e "y" final.
//
// Uso: node tests/test_readability.js

const assert = require("assert");
const path = require("path");
const fs = require("fs");
const { execFileSync } = require("child_process");
const { countSyllables, countTextSyllables, computeReadability } = require("../frontend/js/readability.js");

const ROOT = path.resolve(__dirname, "..");
const BLOCKS = JSON.parse(fs.readFileSync(path.join(ROOT, "evaluation/assets/bloques_lectura.json"), "utf8")).bloques;
const WORDS = ["cuando", "planeta", "caliente", "guerra", "pingüino", "querer", "hoy", "muy", "río", "país",
               "aéreo", "océano", "ciudad", "huir", "Uruguay", "radiativo", "antropogénico", "CO", "El", "Niño"];
const TEXTS = [...BLOCKS.map(b => b.text), "Hola mundo.", "Uno. Dos tres cuatro cinco seis siete ocho nueve."];

// Referencia: lo que calcula el backend para los mismos textos.
const input = JSON.stringify({ words: WORDS, texts: TEXTS });
const reference = JSON.parse(execFileSync("python", ["-c",
    "import json,sys; sys.path.insert(0,'backend'); "
    + "from analyzers.readability import count_syllables, count_text_syllables, compute_readability; "
    + "d = json.loads(sys.stdin.buffer.read().decode('utf-8')); "
    + "print(json.dumps({'words': [count_syllables(w) for w in d['words']], "
    + "'texts': [{'syl': count_text_syllables(t), 'r': compute_readability(t)} for t in d['texts']]}))"],
    { cwd: ROOT, input }).toString());

let passed = 0;
function test(name, fn) {
    fn();
    passed++;
    console.log(`  ok  ${name}`);
}

test("sílabas por palabra: iguales al backend", () => {
    WORDS.forEach((w, i) => assert.strictEqual(countSyllables(w), reference.words[i], w));
});

test(`sílabas, INFLESZ y nivel de ${TEXTS.length} textos: iguales al backend`, () => {
    TEXTS.forEach((t, i) => {
        const ref = reference.texts[i];
        assert.strictEqual(countTextSyllables(t), ref.syl, `sílabas: ${t.slice(0, 40)}`);
        const r = computeReadability(t);
        if (ref.r === null) return assert.strictEqual(r, null, `debería ser corto: ${t.slice(0, 40)}`);
        assert.strictEqual(r.level, ref.r.level, `nivel: ${t.slice(0, 40)}`);
        assert.strictEqual(r.words, ref.r.words);
        assert.strictEqual(r.sentences, ref.r.sentences, `oraciones: ${t.slice(0, 40)}`);
        assert.ok(Math.abs(r.inflesz - ref.r.inflesz) <= 0.051, `INFLESZ ${r.inflesz} vs ${ref.r.inflesz}`);
    });
});

console.log(`\n${passed} pruebas OK`);
