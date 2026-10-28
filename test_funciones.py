"""
test_funciones.py — Prueba funciones del bot por separado.

Uso:
    python test_funciones.py

Descomenta la función que quieras testear en el bloque de abajo.
"""

# Importa todo desde el archivo principal (funciones, variables globales, imports)
import importlib.util, sys, os

# Carga el módulo principal sin ejecutar el loop
spec = importlib.util.spec_from_file_location(
    "botmina",
    os.path.join(os.path.dirname(__file__), "Minas-op.py")
)
botmina = importlib.util.module_from_spec(spec)
spec.loader.exec_module(botmina)

# Accesos directos a las funciones del bot
recnec             = botmina.recnec

esperar_sala       = botmina.esperar_sala
inter              = botmina.inter
reconectar         = botmina.reconectar
vent_pelea         = botmina.vent_pelea
ventana_nivel      = botmina.ventana_nivel
any_desk           = botmina.any_desk
reiniciar_juego    = botmina.reiniciar_juego
inventario         = botmina.inventario
ir_banco           = botmina.ir_banco
recolectar         = botmina.recolectar
minar              = botmina.minar
minero             = botmina.minero
sala               = botmina.sala
pelear2            = botmina.pelear2
pelear3            = botmina.pelear3
caminar3           = botmina.caminar3
caminar2           = botmina.caminar2
caminarMina        = botmina.caminarMina
caminarMinab       = botmina.caminarMinab
mapa1              = botmina.mapa1
mapab1             = botmina.mapab1
rutas              = botmina.rutas
caminar_dofus_inteligente = botmina.caminar_dofus_inteligente
detectar_enemigo_sala     = botmina.detectar_enemigo_sala
buscar_imagen_en_pantalla = botmina.buscar_imagen_en_pantalla
heart              = botmina.heart  # pyautogui alias

import time


# ─────────────────────────────────────────────
#  UTILIDADES DE TEST
# ─────────────────────────────────────────────

def ver_pixel(x, y, intervalo=0.5):
    """Muestra el color del pixel en (x, y) en tiempo real. Ctrl+C para detener."""
    print(f"Monitoreando pixel ({x}, {y}) — Ctrl+C para detener")
    try:
        while True:
            color = heart.pixel(x, y)
            print(f"  RGB: {color}")
            time.sleep(intervalo)
    except KeyboardInterrupt:
        print("Detenido.")


def ver_posicion_mouse(intervalo=0.5):
    """Muestra la posición del mouse en tiempo real. Ctrl+C para detener."""
    print("Posición del mouse — Ctrl+C para detener")
    try:
        while True:
            x, y = heart.position()
            color = heart.pixel(x, y)
            print(f"  Pos: ({x}, {y})  RGB: {color}")
            time.sleep(intervalo)
    except KeyboardInterrupt:
        print("Detenido.")


def esperar_segundos(n=3):
    """Pausa con cuenta regresiva antes de ejecutar el test."""
    for i in range(n, 0, -1):
        print(f"Iniciando en {i}...")
        time.sleep(1)


# ─────────────────────────────────────────────
#  TESTS — descomenta el que quieras probar
# ─────────────────────────────────────────────

if __name__ == "__main__":

    # --- Ver pixel en coordenada específica ---
    # ver_pixel(488, 722)

    # --- Ver posición y color del mouse en tiempo real ---
    # ver_posicion_mouse()

    # --- Reconexión ---
    # esperar_segundos(3)
    # recnec()

    # --- Reconexión alternativa ---
    # esperar_segundos(3)
    # recnec2()

    # --- Reiniciar juego completo --
    esperar_segundos(3)
    reiniciar_juego()

    # --- Verificar inventario lleno ---
    # esperar_segundos(3)
    # resultado = inventario()
    # print("Inventario lleno:", resultado)

    # --- Ir al banco ---
    # esperar_segundos(3)
    # ir_banco()

    # --- Minar lista de posiciones ---
    # posiciones_test = [(x1, y1), (x2, y2)]  # reemplaza con coordenadas reales
    # esperar_segundos(3)
    # minar(posiciones_test)

    # --- Recolectar en coordenada ---
    # esperar_segundos(3)
    # recolectar(500, 400)

    # --- Sala completa ---
    # esperar_segundos(3)
    # sala()

    # --- Combate pelear2 ---
    # esperar_segundos(3)
    # pelear2()

    # --- Combate pelear3 ---
    # esperar_segundos(3)
    # pelear3()

    # --- Caminar a mina ---
    # esperar_segundos(3)
    # caminarMina()

    # --- Ventana nivel ---
    # esperar_segundos(3)
    # ventana_nivel()

    # --- Detectar enemigo en pantalla ---
    # esperar_segundos(3)
    # pos = detectar_enemigo_sala("enemigo.png")
    # print("Enemigo en:", pos)

    # --- Test pixel de condición reconexión ---
    # ver_pixel(1043, 821)  # equipo minero (break de recnec)

    print("Sin test activo. Descomenta una función para probarla.")
