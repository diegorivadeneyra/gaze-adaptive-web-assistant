"""Simula el envio de coordenadas de mirada al backend (POST /gaze-latest),
util para probar el modo Tobii (GAZE_INPUT_SOURCE=tobii) sin el hardware
conectado todavia. El backend reenvia cada punto recibido aqui por el mismo
WebSocket (ws://127.0.0.1:5600) que usa el bridge real de gaze_server.cpp,
asi que el frontend lo recibe igual que si viniera del Tobii de verdad.

Uso:
    python simulate_gaze.py [x] [y] [duracion_segundos]

Ejemplo (fija la mirada simulada en x=500, y=300 durante 3 segundos):
    python simulate_gaze.py 500 300 3
"""
import sys
import time
import requests

URL = "http://127.0.0.1:5000/gaze-latest"
INTERVAL_S = 0.08  # orden de magnitud razonable para simular una fijación


def main():
    x = float(sys.argv[1]) if len(sys.argv) > 1 else 500
    y = float(sys.argv[2]) if len(sys.argv) > 2 else 300
    duration_s = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0

    print(f"Enviando ({x}, {y}) a {URL} durante {duration_s}s... Ctrl+C para detener.")
    start = time.time()
    sent = 0
    while time.time() - start < duration_s:
        try:
            requests.post(URL, json={"x": x, "y": y, "valid": True}, timeout=1)
            sent += 1
        except requests.exceptions.RequestException as e:
            print(f"Error al enviar: {e}")
        time.sleep(INTERVAL_S)

    print(f"Listo. {sent} puntos enviados.")


if __name__ == "__main__":
    main()
