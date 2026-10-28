"""Bot receptor: acepta intercambios entrantes y deposita en el banco
lo que recibe, en un ciclo indefinido.

Uso: python receptor.py
"""
import os
import sys
import time
import pyautogui as heart

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun


def meter_recurso():
    """Deposita en el banco lo que el personaje acaba de recibir por
    intercambio. El inventario se auto-compacta, así que basta con repetir
    el Ctrl+Doble-Click sobre el slot de referencia hasta que quede vacío
    (mismo mecanismo validado en botmina/anu-ventas)."""
    comun.recnec()
    if not comun.esperar_condicion(
        lambda: heart.pixelMatchesColor(441, 334, (129, 128, 33), tolerance=15),
        timeout=10, nombre="recinto del banco",
    ):
        print("[receptor] ⚠️ no se detecta el recinto del banco")
        return False

    heart.click(941, 284,button="right")
    time.sleep(0.3)
    heart.click(978, 280,button="right")

    heart.click(976,282)
    time.sleep(0.3)
    heart.click(999,287)
    if not comun.esperar_condicion(
        lambda: (heart.pixelMatchesColor(376, 250, (255, 208, 102), tolerance=15)
                 or heart.pixelMatchesColor(1227, 249, (255, 255, 255), tolerance=15)),
        timeout=10, nombre="ventana del banco",
    ):
        print("[receptor] ⚠️ no se pudo abrir la ventana del banco")
        return False

    if heart.pixelMatchesColor(376, 250, (255, 208, 102), tolerance=15):
        heart.click(421, 458, clicks=2, interval=0.2)
        comun.esperar_condicion(
            lambda: not heart.pixelMatchesColor(376, 250, (255, 208, 102), tolerance=15),
            timeout=6, nombre="cierre ventana búho",
        )

    heart.click(426, 299)
    time.sleep(0.3)
    heart.click(1098, 300)
    if not comun.esperar_condicion(
        lambda: heart.pixelMatchesColor(424, 291, (81, 74, 60), tolerance=15),
        timeout=8, nombre="pestaña de recurso",
    ):
        print("[receptor] ⚠️ no se pudo abrir la pestaña de recurso")
        return False

    # confirmar la pestaña de recursos del inventario propio antes de
    # depositar — evita falsos positivos si el clic anterior no la activó
    heart.click(1099, 301)
    if not comun.esperar_condicion(
        lambda: heart.pixelMatchesColor(1101, 292, (81, 74, 60), tolerance=15),
        timeout=8, nombre="pestaña de recursos activa antes de depositar",
    ):
        print("[receptor] ⚠️ no se pudo activar la pestaña de recursos antes de depositar")
        return False

    SX, SY = 1049, 364
    MAX_INTENTOS = 15
    intentos = 0
    while intentos < MAX_INTENTOS and not heart.pixelMatchesColor(1053, 369, (190, 185, 152), tolerance=5):
        comun.recnec()
        intentos += 1
        heart.moveTo(SX, SY, duration=0.1)
        time.sleep(0.2)
        heart.keyDown("ctrl")
        heart.click(clicks=2, interval=0.2)
        heart.keyUp("ctrl")
        time.sleep(0.4)

    if intentos == 0:
        print("[receptor] no había recurso pendiente de depositar")
    elif intentos >= MAX_INTENTOS:
        print(f"[receptor] ⚠️ no se pudo confirmar el depósito tras {MAX_INTENTOS} intentos")
    else:
        print(f"[receptor] recurso depositado en {intentos} intento(s)")

    heart.click(1249, 267)
    time.sleep(0.3)
    heart.click(1250, 263)
    time.sleep(0.3)
    return True


def aceptar_intercambio():
    """Espera una invitación de intercambio entrante, la acepta, recibe el
    recurso y lo deposita en el banco."""
    while True:
        comun.recnec()
        print("[receptor] esperando invitación de intercambio...")

        if heart.pixelMatchesColor(1024, 404, (255, 255, 255), tolerance=5):
            time.sleep(0.3)
            heart.click(771, 444)

        if not heart.pixelMatchesColor(1259, 274, (255, 255, 255), tolerance=5):
            time.sleep(0.5)
            continue

        print("[receptor] ventana de intercambio detectada")
        if not comun.esperar_condicion(
            lambda: not heart.pixelMatchesColor(405, 553, (190, 185, 152), tolerance=5),
            timeout=30, nombre="recurso recibido",
        ):
            print("[receptor] ⚠️ no llegó ningún recurso — cancelando este intercambio")
            continue

        print("[receptor] recurso detectado — esperando poder aceptar")
        if not comun.esperar_condicion(
            lambda: heart.pixelMatchesColor(1238, 648, (255, 97, 0), tolerance=15),
            timeout=15, nombre="botón de aceptar disponible",
        ):
            print("[receptor] ⚠️ no se habilitó el botón de aceptar")
            continue
        heart.click(1245, 651, clicks=2, interval=0.2)

        if not comun.esperar_condicion(
            lambda: not heart.pixelMatchesColor(853, 306, (255, 255, 255), tolerance=5),
            timeout=10, nombre="cierre ventana de intercambio",
        ):
            print("[receptor] ⚠️ la ventana de intercambio no se cerró")
            continue

        time.sleep(0.3)
        meter_recurso()
        return


if __name__ == "__main__":
    while True:
        time.sleep(1)
        print("[receptor] === inicia ciclo ===")
        aceptar_intercambio()
        print("[receptor] === ciclo terminado ===")
