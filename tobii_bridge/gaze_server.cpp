// gaze_server.cpp: lee el Tobii 5 (SDK Stream Engine) y envía cada punto por
// TCP (puerto 5555) a backend/app.py, que lo reenvía al navegador.
//
// Protocolo: una línea por punto, "x_px,y_px,timestamp_us,valid\n" (valid 1/0),
// en píxeles de pantalla. app.py lo pasa a proporción y el navegador lo ajusta
// a la página (gaze_mapping.js + comprobación de 5 puntos).
//
// Compilar con Visual Studio 2022, x86 (gaze_server.sln); ver tobii_bridge/README.md.
// app.py abre este puente solo en modo Tobii.

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

    // ── Tobii ──
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

    // Reenvía cada punto mientras Python siga conectado. Acepta una sola
    // conexión: si se cae, app.py abre un puente nuevo.
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
