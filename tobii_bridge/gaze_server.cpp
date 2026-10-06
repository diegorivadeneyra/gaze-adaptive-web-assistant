// gaze_server.cpp
//
// Se conecta al Tobii 5 con el SDK oficial (igual que el ejemplo de prueba)
// y reenvia cada punto de mirada por un socket TCP a Python (backend/app.py),
// que lo lee y lo deja disponible en GET /gaze-latest para el frontend.
//
// Protocolo (una linea de texto por punto, separada por coma):
//   x_px,y_px,timestamp_us,valid\n
// valid es 1 o 0. Las coordenadas se mandan ya convertidas a pixeles de
// pantalla (no normalizadas 0-1 como las entrega el SDK), asumiendo que el
// navegador corre en pantalla completa en el monitor principal — si no está
// en pantalla completa, x/y quedaran desalineadas del contenido web (esto
// queda como calibracion pendiente, no lo resuelve este bridge).
//
// Build (MinGW, mismo patron que tobiiCpp/leeme.txt):
//   g++ gaze_server.cpp -o gaze_server.exe -Iinclude -Llib/x86 -ltobii_stream_engine -lws2_32
//
// Uso:
//   1. .\gaze_server.exe                    (deja el Tobii listo y espera a Python)
//   2. python app.py  (con GAZE_INPUT_SOURCE = INPUT_SOURCE_TOBII en app.py)

#include <stdio.h>
#include <assert.h>
#include <string.h>
#include <winsock2.h>
#include <windows.h>

#include "include/tobii/tobii.h"
#include "include/tobii/tobii_streams.h"

#pragma comment(lib, "ws2_32.lib")

#define GAZE_SERVER_PORT 5555

static SOCKET g_client_socket = INVALID_SOCKET;
static int g_screen_w = 1920;
static int g_screen_h = 1080;

void send_line(const char* line)
{
    if (g_client_socket == INVALID_SOCKET) return;
    int sent = send(g_client_socket, line, (int)strlen(line), 0);
    if (sent == SOCKET_ERROR)
    {
        printf("[gaze_server] Python se desconecto.\n");
        closesocket(g_client_socket);
        g_client_socket = INVALID_SOCKET;
    }
}

void gaze_point_callback(tobii_gaze_point_t const* gaze_point, void* /* user_data */)
{
    char line[128];

    if (gaze_point->validity == TOBII_VALIDITY_VALID)
    {
        // El SDK entrega position_xy normalizado en [0,1] respecto a la
        // pantalla; se convierte a pixeles antes de mandarlo.
        float pixel_x = gaze_point->position_xy[0] * g_screen_w;
        float pixel_y = gaze_point->position_xy[1] * g_screen_h;
        snprintf(line, sizeof(line), "%f,%f,%lld,1\n",
            pixel_x, pixel_y, (long long)gaze_point->timestamp_us);
    }
    else
    {
        snprintf(line, sizeof(line), "0,0,%lld,0\n", (long long)gaze_point->timestamp_us);
    }

    send_line(line);
    printf("%s", line);
}

void url_receiver(char const* url, void* user_data)
{
    char* buffer = (char*)user_data;
    if (*buffer != '\0') return; // only keep first value
    if (strlen(url) < 256)
        strcpy(buffer, url);
}

int main()
{
    g_screen_w = GetSystemMetrics(SM_CXSCREEN);
    g_screen_h = GetSystemMetrics(SM_CYSCREEN);
    printf("[gaze_server] Resolucion detectada: %dx%d\n", g_screen_w, g_screen_h);

    // ── Winsock: levantar el socket servidor ──
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0)
    {
        printf("[gaze_server] Error inicializando Winsock\n");
        return 1;
    }

    SOCKET listen_socket = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    assert(listen_socket != INVALID_SOCKET);

    sockaddr_in service;
    service.sin_family = AF_INET;
    service.sin_addr.s_addr = inet_addr("127.0.0.1");
    service.sin_port = htons(GAZE_SERVER_PORT);

    if (bind(listen_socket, (SOCKADDR*)&service, sizeof(service)) == SOCKET_ERROR)
    {
        printf("[gaze_server] Error en bind (puerto %d ocupado?)\n", GAZE_SERVER_PORT);
        closesocket(listen_socket);
        WSACleanup();
        return 1;
    }

    if (listen(listen_socket, 1) == SOCKET_ERROR)
    {
        printf("[gaze_server] Error en listen\n");
        closesocket(listen_socket);
        WSACleanup();
        return 1;
    }

    printf("[gaze_server] Esperando conexion de Python en 127.0.0.1:%d...\n", GAZE_SERVER_PORT);
    g_client_socket = accept(listen_socket, NULL, NULL);
    assert(g_client_socket != INVALID_SOCKET);
    printf("[gaze_server] Python conectado.\n");

    // ── Tobii: exactamente el mismo flujo que main.cpp ──
    tobii_api_t* api = NULL;
    tobii_error_t result = tobii_api_create(&api, NULL, NULL);
    assert(result == TOBII_ERROR_NO_ERROR);

    char url[256] = { 0 };
    result = tobii_enumerate_local_device_urls(api, url_receiver, url);
    assert(result == TOBII_ERROR_NO_ERROR);
    if (*url == '\0')
    {
        printf("[gaze_server] Error: no se encontro el dispositivo Tobii\n");
        return 1;
    }

    tobii_device_t* device = NULL;
    result = tobii_device_create(api, url, TOBII_FIELD_OF_USE_INTERACTIVE, &device);
    assert(result == TOBII_ERROR_NO_ERROR);

    result = tobii_gaze_point_subscribe(device, gaze_point_callback, NULL);
    assert(result == TOBII_ERROR_NO_ERROR);

    // Bucle principal: mientras Python siga conectado, reenvia cada punto.
    // Si Python se desconecta, este proceso sigue leyendo del Tobii pero
    // deja de enviar (send_line no hace nada con socket invalido) — hay que
    // reiniciar gaze_server.exe para que vuelva a aceptar una conexion.
    while (true)
    {
        result = tobii_wait_for_callbacks(1, &device);
        assert(result == TOBII_ERROR_NO_ERROR || result == TOBII_ERROR_TIMED_OUT);
        result = tobii_device_process_callbacks(device);
        assert(result == TOBII_ERROR_NO_ERROR);
    }

    tobii_gaze_point_unsubscribe(device);
    tobii_device_destroy(device);
    tobii_api_destroy(api);
    if (g_client_socket != INVALID_SOCKET) closesocket(g_client_socket);
    closesocket(listen_socket);
    WSACleanup();
    return 0;
}
