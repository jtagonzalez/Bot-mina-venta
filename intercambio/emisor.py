"""Bot emisor: al arrancar abre la ventana de configuración de la cola de
minerales a intercambiar; al confirmarla, saca esos minerales del banco y
los entrega por intercambio a otro personaje.

Uso: python emisor.py
"""
import os
import sys
import time
import pyautogui as heart

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun
import gui_cola

# Región donde aparece el ícono del mineral en la ventana de "recurso" del
# banco (mismo layout que REGION_BANCO en anu-ventas.py). Si la detección
# falla en la práctica, recalibrar estas coordenadas.
REGION_RECURSO_BANCO = (348, 344, 216, 131)

PUNTOS_INVENTARIO_VACIO = [(1053, 369), (1044, 367), (1054, 357), (1066, 368), (1053, 377)]


def _inventario_propio_tiene_recurso():
    """True si algún punto de referencia del slot ya no muestra el color de slot vacío."""
    return any(
        not heart.pixelMatchesColor(x, y, (190, 185, 152), tolerance=5)
        for x, y in PUNTOS_INVENTARIO_VACIO
    )


def _abrir_ventana_buho():
    heart.click(941, 284,button="right")
    time.sleep(0.3)
    heart.click(978,280,button="right")
    return comun.esperar_condicion(
        lambda: heart.pixelMatchesColor(376, 250, (255, 208, 102), tolerance=15),
        timeout=10, nombre="ventana del búho",
    )


def _abrir_pestaña_recurso():
    heart.click(421, 458)
    time.sleep(0.3)
    heart.click(1098, 300)
    time.sleep(0.3)
    heart.click(426, 299)
    return comun.esperar_condicion(
        lambda: heart.pixelMatchesColor(424, 291, (81, 74, 60), tolerance=15),
        timeout=10, nombre="pestaña de recurso",
    )


def sacar_recurso(mineral, cantidad):
    """Extrae `cantidad` unidades de `mineral` del banco al inventario del
    personaje. Ubica el mineral por imagen (banco_<mineral>.png) en vez de
    por posición fija, y espera dinámicamente cada paso en vez de sleeps fijos.
    Retorna True si el recurso quedó en el inventario, False si algo falló."""
    comun.recnec()
    if not comun.esperar_condicion(
        lambda: heart.pixelMatchesColor(441, 334, (129, 128, 33), tolerance=15),
        timeout=10, nombre="recinto del banco",
    ):
        print("[emisor] ⚠️ no se detecta el recinto del banco")
        return False

    print(f"[emisor] sacando {cantidad} de {mineral}...")
    if not _abrir_ventana_buho():
        print("[emisor] ⚠️ no se pudo abrir la ventana del búho")
        return False

    if not _abrir_pestaña_recurso():
        print("[emisor] ⚠️ no se pudo abrir la pestaña de recurso")
        return False

    resultado = comun.esperar_mineral_en_region(mineral, REGION_RECURSO_BANCO, timeout=8)
    if resultado is None:
        print(f"[emisor] ⚠️ {mineral} no encontrado en el banco")
        return False
    cx, cy, score = resultado
    print(f"[emisor] {mineral} encontrado en ({cx},{cy}) conf={score:.2f}")

    heart.moveTo(cx, cy)
    heart.mouseDown()
    heart.moveTo(1228, 416)
    heart.mouseUp()
    time.sleep(0.2)
    heart.write(str(cantidad), interval=0.05)
    time.sleep(0.2)
    heart.press("enter")

    if not comun.esperar_condicion(_inventario_propio_tiene_recurso, timeout=8,
                                    nombre="recurso en inventario"):
        print("[emisor] ⚠️ el recurso no llegó al inventario")
        return False

    print("[emisor] recurso en inventario — cerrando banco")
    heart.click(1250, 263)
    time.sleep(0.3)
    return True


PUNTOS_CLIC_COMPAÑERO = {
    "arriba": (1261, 264),
    "abajo": (1257, 296),
}


# Offset del recuadro del menú contextual respecto al punto de clic,
# calibrado con el menú real: 1071,246-1279,692 con clic en (1261,264).
_MENU_OFFSET_X = 1071 - 1261
_MENU_OFFSET_Y = 246 - 264
_MENU_ANCHO = 1279 - 1071
_MENU_ALTO = 692 - 246


def _abrir_menu_e_intercambiar(posicion, intentos=30):
    """Hace clic en el compañero (arriba o abajo, según posicion) y busca
    la opción 'Intercambio' del menú contextual por imagen (intercambiar.png).
    Retorna True si logró hacer clic en la opción."""
    x_click, y_click = PUNTOS_CLIC_COMPAÑERO.get(posicion, PUNTOS_CLIC_COMPAÑERO["abajo"])
    region = (
        max(0, x_click + _MENU_OFFSET_X),
        max(0, y_click + _MENU_OFFSET_Y),
        _MENU_ANCHO,
        _MENU_ALTO,
    )

    for intento in range(1, intentos + 1):
        heart.click(x_click, y_click)
        resultado = comun.esperar_imagen_en_region("intercambiar.png", region, timeout=0.5, umbral=0.6)
        if resultado is not None:
            cx, cy, score = resultado
            print(f"[emisor] opción 'Intercambio' encontrada en ({cx},{cy}) conf={score:.2f}")
            heart.click(cx, cy)
            return True
        print(f"[emisor] ⚠️ 'Intercambio' no encontrado cerca de ({x_click},{y_click}) — intento {intento}/{intentos}")
    return False


def _invitacion_disponible():
    """True si la ventana de invitación de intercambio quedó visible, o si
    directamente ya se habilitó la ventana operativa (aceptación inmediata)."""
    return (
        heart.pixelMatchesColor(852, 465, (255, 97, 0), tolerance=15)
        or heart.pixelMatchesColor(1018, 408, (255, 255, 255), tolerance=15)
        or heart.pixelMatchesColor(1209, 225, (255, 255, 255), tolerance=15)
    )


def _enviar_invitacion(posicion, intentos=120):
    """Abre el menú del compañero y selecciona 'Intercambio', comprobando a
    los 0.5s si la ventana de invitación quedó disponible. Si no, reintenta
    el envío en vez de esperar un timeout largo — cubre el caso en que el
    compañero está ocupado (p.ej. depositando en el banco) y la invitación
    se pierde sin abrir ninguna ventana. Retorna True apenas se confirma
    disponible."""
    for intento in range(1, intentos + 1):
        if not _abrir_menu_e_intercambiar(posicion):
            print(f"[emisor] ⚠️ no se pudo abrir el menú de intercambio (intento {intento}/{intentos})")
            continue
        time.sleep(0.5)
        if _invitacion_disponible():
            print(f"[emisor] invitación disponible (intento {intento}/{intentos})")
            return True
        print(f"[emisor] ventana de invitación no apareció — reintentando ({intento}/{intentos})")
    return False


def intercambio(mineral, posicion="abajo"):
    """Abre una ventana de intercambio con el compañero, ubica `mineral` por
    imagen en la zona de objetos a intercambiar y lo pasa al trato, y acepta.
    Retorna True si se completó."""
    if not _enviar_invitacion(posicion):
        print("[emisor] ⚠️ no se pudo enviar la invitación de intercambio")
        return False

    if not heart.pixelMatchesColor(1209, 225, (255, 255, 255), tolerance=15):
        print("[emisor] invitación enviada — esperando que el compañero acepte...")
        if not comun.esperar_condicion(
            lambda: heart.pixelMatchesColor(1209, 225, (255, 255, 255), tolerance=15),
            timeout=5, nombre="aceptación del compañero",
        ):
            print("[emisor] ⚠️ el compañero no aceptó el intercambio a tiempo")
            return False

    # abrir la pestaña de recursos del inventario propio antes de pasar el
    # mineral — el inventario solo tiene este mineral (recién extraído del
    # banco), así que el punto fijo (885,346) es su posición una vez ahí.
    heart.click(925, 274)
    if not comun.esperar_condicion(
        lambda: heart.pixelMatchesColor(932, 267, (81, 74, 60), tolerance=15),
        timeout=8, nombre="pestaña de recursos activa en el intercambio",
    ):
        print("[emisor] ⚠️ no se pudo activar la pestaña de recursos en el intercambio")
        return False

    logrado = False
    for intento in range(1, 11):
        heart.moveTo(885, 346)
        heart.keyDown("ctrl")
        heart.click(clicks=2, interval=0.2)
        heart.keyUp("ctrl")
        time.sleep(0.3)
        if not heart.pixelMatchesColor(901, 556, (190, 185, 152), tolerance=15):
            logrado = True
            break
    if not logrado:
        print(f"[emisor] ⚠️ no se pudo pasar {mineral} al intercambio")
        return False

    if not comun.esperar_condicion(
        lambda: heart.pixelMatchesColor(1233, 654, (255, 97, 0), tolerance=15),
        timeout=10, nombre="botón de aceptar intercambio",
    ):
        print("[emisor] ⚠️ no apareció el botón de aceptar")
        return False
    heart.click(1138, 654)

    if not comun.esperar_condicion(
        lambda: not heart.pixelMatchesColor(1200, 223, (255, 255, 255), tolerance=15),
        timeout=10, nombre="cierre de ventana de intercambio",
    ):
        print("[emisor] ⚠️ la ventana de intercambio no se cerró")
        return False

    print("[emisor] ✅ intercambio completado")
    return True


def procesar_cola():
    config = comun.cargar_config()
    capacidad = config.get("capacidad_inventario", 0)
    posicion = config.get("posicion_companero", "abajo")
    cola = config.get("cola", [])

    if capacidad <= 0:
        print("[emisor] ⚠️ capacidad_inventario inválida en la configuración — abortando")
        return
    if not cola:
        print("[emisor] ⚠️ la cola está vacía — nada que hacer")
        return

    for item in cola:
        mineral = item["mineral"]
        pendiente = item["cantidad"]
        print(f"[emisor] === procesando {mineral}: {pendiente} unidades pendientes ===")

        while pendiente > 0:
            a_extraer = min(pendiente, capacidad)
            if not sacar_recurso(mineral, a_extraer):
                print(f"[emisor] ⚠️ no se pudo sacar {mineral} del banco — pasando al siguiente mineral")
                break

            # El recurso ya quedó en el inventario tras sacar_recurso().
            # Si el intercambio falla, se reintenta solo el intercambio
            # (no hay que volver a extraer del banco lo que ya se tiene).
            entregado = False
            for intento_trade in range(1, 4):
                if intercambio(mineral, posicion):
                    entregado = True
                    break
                print(f"[emisor] reintentando entrega de {mineral} (intento {intento_trade + 1}/3)")
                time.sleep(0.05)
            if not entregado:
                print(f"[emisor] ⚠️ no se pudo entregar {mineral} tras varios intentos — pasando al siguiente mineral")
                break

            pendiente -= a_extraer
            print(f"[emisor] {mineral}: {pendiente} unidades pendientes restantes")

    print("[emisor] ✅ cola completada")


if __name__ == "__main__":
    if gui_cola.abrir_gui():
        procesar_cola()
    else:
        print("[emisor] configuración cancelada — no se inició el intercambio")
