# Guía para hacer las pruebas con participantes

Paso a paso, desde una computadora nueva (por ejemplo, la laptop de las pruebas)
hasta tener los resultados. Pensada para seguirla en orden.

---

## Parte 1 · Instalación (una sola vez por computadora)

### 1.1 Programas que hay que instalar

| Programa | Para qué | Dónde |
|---|---|---|
| **Python 3.9 o más nuevo** | Corre el sistema | https://www.python.org/downloads/ (al instalar, marcar **"Add Python to PATH"**) |
| **Git** | Descargar el proyecto | https://git-scm.com/download/win |
| **Ollama** | Los modelos de IA, locales y gratuitos | https://ollama.com/download |
| **Tobii Experience** | Driver y calibración del Tobii 5 | Al conectar el Tobii, Windows Update instala el driver y la app (Microsoft Store). Si no pasa: https://gaming.tobii.com/getstarted/ → Tobii Eye Tracker 5 → *Download Driver* |
| **Google Chrome** | Navegador para las páginas | https://www.google.com/chrome/ |

No hace falta Visual Studio: el puente del Tobii ya viene compilado en
`tobii_bridge/bin/`.

### 1.2 Descargar el proyecto

Abrir una terminal (PowerShell o "Símbolo del sistema") y ejecutar:

```bash
git clone https://github.com/diegorivadeneyra/gaze-adaptive-web-assistant.git
```

```bash
cd gaze-adaptive-web-assistant
```

Crear la carpeta donde se guardan los Excel respondidos (`data/` no viene con
el proyecto: tiene datos de participantes y no se sube a GitHub):

```bash
mkdir dataespuestas
```

### 1.3 Instalar las librerías de Python

```bash
pip install -r backend/requirements.txt
```

### 1.4 Primera ejecución: descarga de los modelos de IA

**Con internet**, la primera vez:

```bash
cd backend
```

```bash
python app.py
```

- Descarga solo `phi3` y `qwen2.5vl:3b` (~5.5 GB en total). Puede tardar.
- Cuando aparezca **`[WARMUP] Modelos listos.`** ya está. Cerrar con **Ctrl + C**.
- Desde ahí funciona **sin internet**.
- **GPU necesaria:** NVIDIA con 6 GB o más (probado: RTX 3070 Ti de 8 GB y RTX
  3050 de 6 GB en laptop; una MX130 de 4 GB no alcanza). Con 6 GB los dos modelos
  no caben juntos: es normal que `ollama ps` muestre solo `phi3` (Qwen se carga
  solo al mirar una gráfica y luego phi3 vuelve a cargarse solo).

### 1.5 Activar el Tobii

Abrir `backend/app.py` con cualquier editor y dejar esta línea así:

```python
GAZE_INPUT_SOURCE = INPUT_SOURCE_TOBII
```

(Con `INPUT_SOURCE_MOUSE` el sistema usa el mouse en vez de la mirada: sirve
para probar sin el Tobii.)

### 1.6 Ajustes de la computadora

- **Zoom del navegador al 100 %** (Ctrl + 0).
- El navegador en la **misma pantalla donde está el Tobii**. En una laptop, sin
  monitor externo, o con el Tobii en el monitor que se usará.
- Desactivar notificaciones y actualizaciones automáticas durante las sesiones.

---

## Parte 2 · Antes de cada participante (~5 min)

1. **Conectar el Tobii** y abrir **Tobii Experience**. **Calibrar a la persona**
   (sentada como va a leer, a 50–80 cm de la pantalla, con buena luz).
2. **Arrancar el sistema** en una terminal, desde la carpeta del proyecto:

   ```bash
   cd backend
   ```

   ```bash
   python app.py
   ```

   - Se abre **sola** otra ventana: el puente del Tobii (`gaze_server.exe`).
     **No cerrarla** durante la sesión.
   - Esperar **`[WARMUP] Modelos listos.`** (~20 s) y **`[TOBII] Conectado`**.
3. **Preparar el Excel:** copiar `evaluation/cuestionarios_participante.xlsx` y
   guardar la copia como **`data/respuestas/P01.xlsx`** (con el código del
   participante). Dejarlo abierto, sin mostrarlo todavía.
4. Abrir Chrome en **`http://127.0.0.1:5000`**.

---

## Parte 3 · La sesión

### 3.1 Iniciar (lo hace el investigador)

1. En la página de inicio, escribir el **código del participante** (P01 … P06,
   **en orden**: el primero que viene es P01, el segundo P02…).
2. Revisar que diga **"Sorteo previo: P0X tiene el orden y los métodos fijados"**
   y el orden, por ejemplo: *1. Intermedio (automática) → 2. Avanzado (a pedido) →
   3. Fácil (a pedido)*. No se puede cambiar: el sorteo se hizo antes del piloto
   para que cada método tenga la misma cantidad de lecturas
   (`evaluation/asignacion_participantes.csv`). Un código fuera de la lista (p. ej.
   `PRUEBA`) se sortea al momento: úsalo solo para probar.
3. Dejar marcado **"Ocultar panel de monitoreo"**.
4. Pulsar **Iniciar sesión**. Aparece la **pantalla de bienvenida**, que tapa
   la configuración. Desde aquí, la computadora es del participante.

### 3.2 Lo que hace el participante

1. **Bienvenida:** lee las instrucciones y pulsa **Iniciar**.
2. **Comprobación de la mirada:** mira 5 puntos rojos (~12 s).
   - Al final, el investigador mira el **error medio**. Aceptable: **≤ 60 px**.
   - Si sale mayor, pulsar **Repetir**; si sigue alto, recalibrar en Tobii
     Experience. **Anotar el error** (queda guardado de todas formas).
3. **Para cada una de las 3 páginas web:**
   1. Lee la página con calma.
   2. Pulsa **"Terminé esta página"** y **marca** con clics los párrafos que le
      costó entender (puede no marcar ninguno). Pulsa **Continuar**.
   3. **Descanso de 1.5 minutos:** el texto queda tapado, hay una cuenta regresiva y
      **no se le pide nada** (no hay botones; no se registra nada). Al terminar,
      la siguiente página se abre sola. Tras la tercera página no hay descanso.
4. **Cierre:** al terminar la tercera página aparece *"¡Gracias!"*. Responde en
   el Excel, en orden, las hojas **«Comprensión»** (escribe lo que entendió de cada página, sin volver a
   las páginas), **«NASA-TLX»** (una sola vez, sobre toda la tarea), **«SUS»** y
   **«Post-experimento»**.

### 3.3 Terminar (lo hace el investigador)

1. En la pantalla de cierre, pulsar **"Investigador: ver sesión"** y luego
   **Finalizar sesión**.
2. **Guardar el Excel** (`data/respuestas/P01.xlsx`).
3. **Copiar la carpeta `data/`** a un USB o a la nube. No está en git: si se daña
   la computadora, se pierde.
4. Para el siguiente participante, se puede dejar `python app.py` encendido
   (calibrar a la nueva persona en Tobii Experience y volver a la Parte 2,
   paso 3). Para apagar: **Ctrl + C** en la terminal (cierra también el puente).

---

## Parte 4 · Revisar los datos

Desde la carpeta del proyecto (no hace falta que el sistema esté encendido):

```bash
python evaluation/analyze_sessions.py
```

```bash
python evaluation/puntuar_cuestionarios.py
```

Los resultados quedan en `data/sessions/resumen/`:

| Archivo | Contenido |
|---|---|
| `paginas.csv` | Por participante y página: condición, orden, tiempo de lectura, pausa, ayudas, acierto y cobertura |
| `visitas.csv` | Cada visita a un párrafo, tabla o figura (tiempo, relecturas, fijaciones) |
| `ayudas.csv` | Cada ayuda: cuándo, por qué, si se pidió, cuánto se miró, texto (columna `calificacion` para calificar a mano) |
| `comprension_textos.csv` | Lo que cada persona escribió de cada página; columnas `ideas_correctas`, `ideas_incorrectas` y `notas` para calificar a mano (se conservan al volver a correr el script) |
| `nasa_tlx.csv` | NASA-TLX de toda la tarea (bruto y ponderado, con los pesos) |
| `sus.csv`, `post_experimento.csv`, `post_metodos.csv` | SUS y cuestionario post-experimento |
| `avisos.txt` | Respuestas vacías o incoherentes en los Excel: revisarlo después de cada participante |

**Conviene correr ambos después de cada participante**: si algo no se guardó, se
detecta ese mismo día.

---

## Parte 5 · Problemas frecuentes

| Mensaje o síntoma | Causa | Qué hacer |
|---|---|---|
| `[TOBII] Sin conexión con gaze_server.exe … Reintentando` | El puente no abrió o se cerró | Revisar que el Tobii esté conectado y Tobii Experience abierto; el sistema lo reabre solo. Si sigue, cerrar con Ctrl + C y volver a correr `python app.py` |
| La ventana del puente dice `no se encontro el dispositivo Tobii` | Tobii desconectado o sin driver | Reconectar el USB, abrir Tobii Experience |
| `[OLLAMA] No se pudo conectar con Ollama` | Ollama no está corriendo | Abrir Ollama (menú Inicio) y volver a correr `python app.py` |
| La primera ayuda dice *"Este contenido usa conceptos…"* | Se empezó antes de que cargaran los modelos | Esperar siempre **`[WARMUP] Modelos listos.`** |
| La comprobación dice "No se detectó la mirada" | El Tobii no ve los ojos | Acomodar a la persona (distancia, luz, lentes con reflejo) y **Repetir** |
| El error de la comprobación es mayor a 60 px | Calibración mala | Recalibrar en Tobii Experience y repetir la comprobación |
| `PermissionError` al guardar el Excel o al generar resultados | El archivo está abierto en Excel | Cerrar el Excel y repetir |
| `Error en bind` en la ventana del puente | Quedó otro puente abierto | Cerrar todas las ventanas de `gaze_server.exe` y correr `python app.py` de nuevo |

**Probar sin el Tobii:** poner `GAZE_INPUT_SOURCE = INPUT_SOURCE_MOUSE` en
`backend/app.py`; el cursor hace de mirada (la comprobación de 5 puntos se
salta sola).

---

Más detalle del sistema: [`RESUMEN_DEL_SISTEMA.md`](RESUMEN_DEL_SISTEMA.md)
(cada componente con sus pruebas) y [`README.md`](README.md).
