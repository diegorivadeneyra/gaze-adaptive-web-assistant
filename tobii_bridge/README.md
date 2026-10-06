# tobii_bridge

Puente entre el Tobii 5 (SDK en C++) y el backend en Python (`backend/app.py`).
Es la única carpeta relacionada a Tobii que es parte del proyecto real — las
carpetas `tobii5/` y `tobiiCpp/` son solo ejemplos sueltos de prueba del SDK,
no se usan aquí.

## Cómo funciona

```
Tobii 5 --(SDK oficial)--> gaze_server.cpp --(socket TCP, puerto 5555)--> backend/app.py --(WebSocket, puerto 5600)--> frontend
```

`gaze_server.cpp` se conecta al eye tracker igual que el ejemplo de prueba,
pero en vez de imprimir a consola, manda cada punto de mirada por un socket
TCP como una línea de texto:

```
x_px,y_px,timestamp_us,valid\n
```

`backend/app.py` corre un hilo (`_tobii_socket_bridge`) que se conecta a ese
socket como cliente, lee esas líneas y reenvía cada punto de inmediato (push,
no polling) a todos los navegadores conectados por WebSocket
(`ws://127.0.0.1:5600`, ver `_run_websocket_server`/`_ws_broadcast` en
`app.py` y `connectTobiiSocket` en `frontend/js/gaze.js`). Antes el frontend
preguntaba por HTTP cada 100ms y se perdía casi todas las muestras del Tobii
(que entrega datos a ~90Hz) — con push se recibe cada una.

## Compilar — Visual Studio 2022 (recomendado)

El MinGW de esta máquina falla en silencio al compilar cualquier cosa (hasta
un "hola mundo" trivial) — es un problema de esa instalación, no del código.
Como Visual Studio 2022 sí compila el SDK de Tobii sin problema, usa el
proyecto ya armado:

1. Abre `gaze_server.sln` con Visual Studio 2022.
2. Verifica que la configuración de arriba diga **Debug** y **x86** (no x64
   ni ARM — las librerías en `lib/x86/` son de 32 bits).
3. Compila (Ctrl+Shift+B). El `.exe` queda en `Debug/gaze_server.exe`
   (o `Release/` si compilas en Release).
4. Copia `lib/x86/tobii_stream_engine.dll` a esa misma carpeta (`Debug/` o
   `Release/`) para que el `.exe` lo encuentre al ejecutarse.

El proyecto ya trae configurado el include de `include/`, la librería de
`lib/x86/tobii_stream_engine.lib` y `ws2_32.lib` (Winsock) — no hace falta
tocar nada más en las propiedades del proyecto.

## Compilar — MinGW (alternativa, si consigues arreglar esa instalación)

Las librerías en `lib/x86/` son de **32 bits**. Si tu `g++` por defecto es
el de 64 bits (`x86_64-w64-mingw32`), el link falla con
`skipping incompatible ... cannot find -ltobii_stream_engine` — hay que usar
el compilador de 32 bits (`i686-w64-mingw32`) explícitamente:

```bash
C:\msys64\mingw32\bin\g++.exe gaze_server.cpp -o gaze_server.exe -Iinclude -Llib/x86 -ltobii_stream_engine -lws2_32
```

Copia `lib/x86/tobii_stream_engine.dll` junto al `.exe` para que pueda
cargarlo en tiempo de ejecución.

## Correr

El orden en que arrancas los dos procesos no importa: `app.py` reintenta
conectarse cada 3s hasta que `gaze_server.exe` esté escuchando, y
`gaze_server.exe` se queda esperando en `accept()` hasta que `app.py` se
conecte. Así que puedes arrancar cualquiera primero.

1. Conecta el Tobii 5 y corre:
   ```powershell
   .\gaze_server.exe
   ```
   Debe imprimir la resolución detectada y quedar esperando la conexión de Python
   (o conectarse enseguida si `app.py` ya estaba corriendo).

2. En `backend/app.py`, pon:
   ```python
   GAZE_INPUT_SOURCE = INPUT_SOURCE_TOBII
   ```
   y corre el backend normalmente:
   ```bash
   python app.py
   ```
   Debería imprimir `[TOBII] Conectando a gaze_server.exe...` y luego `Conectado.`.

3. Abre cualquier página (`facil.html`, `intermedio.html`, `avanzado.html`) y
   verifica en el panel de debug que diga "👁️ Tobii 5".

## Limitación conocida (pendiente de calibración)

`gaze_server.cpp` convierte el punto normalizado (0–1) que entrega el SDK a
píxeles usando la resolución de pantalla completa (`GetSystemMetrics`). Esto
asume que el navegador está en **pantalla completa real** (F11, sin barra de
título/pestañas/barra de tareas visible) en el monitor principal, empezando
en (0,0) — "maximizado" (doble clic en la barra de título) **no es lo mismo**:
maximizado sigue restando pixeles de la barra de título, pestañas y la barra
de tareas de Windows, así que las coordenadas quedarían desalineadas del
contenido web aunque la ventana ocupe "toda la pantalla" visualmente. Con
más de un monitor, tampoco está resuelto. Esto requeriría un paso de
calibración aparte, que no está hecho todavía.
