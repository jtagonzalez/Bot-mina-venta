"""
venta_pan.py — bot de venta de pan en el mercadillo
=====================================================
Adaptado de test_ir_mercado.py: mismo mecanismo de venta que usa Minas-op.py
para minerales (retirar lo ya listado → vender con precio_actual-1,
respetando un mínimo → repetir hasta llenar el almacén), pero:
  - sin ir al banco: el pan ya está en el inventario del personaje
  - sin navegación de mapas: el personaje siempre está parado en el mercadillo
  - la ventana del puesto se abre hablando (hablar → vender) en vez de los
    clics directos que usa el mercado público en Minas-op.py

Ciclo, cada INTERVALO_REVISION segundos:
  1. abrir el mercadillo (hablar → vender)
  2. revisar si hay elementos en venta
     2.1 si hay, retirarlos todos
  3. revisar espacios disponibles
  4. poner en venta pan hasta llenar el almacén o quedarse sin pan
  5. esperar 5 minutos
  6. repetir

Uso: python venta_pan.py
"""
import importlib.util
import re
import time
from pathlib import Path

import cv2
import numpy as np
import pyautogui as heart
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

BASE_DIR = Path(__file__).resolve().parent

# ── framework de seguridad reutilizado de Minas-op.py, sin correr su loop
# principal (mismo mecanismo que test_funciones.py) ──────────────────────
_spec = importlib.util.spec_from_file_location("botmina", BASE_DIR / "Minas-op.py")
_botmina = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_botmina)

recnec             = _botmina.recnec               # detecta desconexión/pantallas de carga y reconecta
any_desk           = _botmina.any_desk              # cierra la notificación de AnyDesk si tapa la pantalla
registrar_progreso = _botmina.registrar_progreso    # marca actividad para el watchdog de Minas-op.py

# NOTA: cargar Minas-op.py también arranca su hilo _watchdog en segundo
# plano (reinicia el juego si pasan 5 min sin registrar_progreso()). Como
# este bot solo actúa cada INTERVALO_REVISION y no cada pocos segundos como
# el bot de minería, loop_principal() sigue llamando registrar_progreso()
# en trozos cortos mientras espera, para que el watchdog no confunda
# "esperando su próximo ciclo" con "bot trabado".


# ─────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────
PRODUCTO = "pan"

CLIC_HABLAR = (633, 437)   # abre el diálogo del puesto
CLIC_VENDER = (681, 523)   # opción "Vender" del menú de diálogo

MAXIMO_SLOTS = 16   # espacios del puesto para este personaje

INTERVALO_REVISION = 5 * 60   # segundos entre revisiones (5 min)
PASO_ESPERA = 60              # registrar_progreso() cada 60s durante la espera

# Precio mínimo de venta — protección contra manipulación de precio (si
# alguien lista muy barato para forzar precio_actual-1 a un valor regalado).
# 0 = sin tope. Mismo criterio que PRECIO_MINIMO en Minas-op.py.
PRECIO_MINIMO_PAN = 0

# Cuántas unidades de pan entran en cada "lote" listado. Se deja en 100 (el
# mismo tamaño de lote que los minerales) porque todavía no se confirmó el
# valor real para pan — AJUSTAR si el mercadillo lista pan de a otra cantidad.
TAMANO_LOTE_PAN = 100

# ── calibrado en el mercadillo real (confirmado) ────────────────────────
REGION_ESPACIOS  = (516, 294, 80, 23)          # contador "en venta X/16" — ensanchada: la de 31px cortaba antes de "/16)" (ver debug_espacios_intento1.png: mostraba "(13," nada más)
PIXEL_HAY_PAN    = (359, 399)   # match → hay al menos un pan listado en ese slot
COLOR_HAY_PAN    = (121, 98, 62)

# ── el resto son las mismas coordenadas que vender_mineral()/retirar_
# minerales()/leer_inventario() en test_ir_mercado.py — posiciones fijas
# del panel de comercio, reutilizadas tal cual como punto de partida.
# PENDIENTE de confirmar si son idénticas en la ventana del mercadillo o
# hace falta recalibrarlas (solo REGION_ESPACIOS y PIXEL_HAY_PAN arriba
# están confirmadas hoy). ──────────────────────────────────────────────
X_ITEM_LISTADO, Y_ITEM_LISTADO       = 358, 401    # slot del elemento ya listado (para retirar)
X_RETIRAR, Y_RETIRAR                 = 385, 633    # botón "retirar"
X_ITEM_INVENTARIO, Y_ITEM_INVENTARIO = 1177, 393   # slot del inventario propio (para vender)
REGION_PRECIO                        = (872, 440, 138, 33)   # precio de referencia mostrado al vender
X_CAMPO_PRECIO, Y_CAMPO_PRECIO       = 910, 612
X_CONFIRMAR, Y_CONFIRMAR             = 738, 614
X_ACEPTAR, Y_ACEPTAR                 = 748, 688
REGION_INVENTARIO                    = (1009, 379, 251, 234)  # panel de inventario propio (para leer cuánto pan hay)
CLIC_ABRIR_INVENTARIO                = (1095 , 338)


def abrir_puesto():
    """Habla con el puesto y entra a la opción de vender."""
    print(f"[{PRODUCTO}] abriendo puesto: hablar → vender")
    heart.click(*CLIC_HABLAR)
    time.sleep(0.5)
    heart.click(*CLIC_VENDER)
    time.sleep(2)


def obtener_elementos_en_venta(max_intentos=3, debug=True):
    """OCR del contador 'en venta X/MAXIMO_SLOTS'. Devuelve (en_venta, espacios)
    o (None, None) si no se pudo leer tras max_intentos."""
    for intento in range(max_intentos):
        ss = heart.screenshot(region=REGION_ESPACIOS)
        raw = cv2.cvtColor(np.array(ss), cv2.COLOR_RGB2GRAY)
        img = cv2.resize(raw, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        _, img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        texto = pytesseract.image_to_string(img, config='--psm 7 -c tessedit_char_whitelist=0123456789()/')
        print(f"[{PRODUCTO}] región={REGION_ESPACIOS} captura={ss.size} OCR(whitelist)={texto!r}")

        if debug:
            texto_libre = pytesseract.image_to_string(img, config='--psm 7')
            print(f"[{PRODUCTO}] OCR(sin whitelist)={texto_libre!r}")
            try:
                debug_path = BASE_DIR / f"debug_espacios_intento{intento + 1}.png"
                cv2.imwrite(str(debug_path), img)
                print(f"[{PRODUCTO}] captura de depuración guardada en {debug_path}")
            except Exception as e:
                print(f"[{PRODUCTO}] no se pudo guardar captura de depuración: {e}")

        m = re.search(r'\(?(\d{1,2})/', texto)
        if m:
            en_venta = int(m.group(1))
            espacios = MAXIMO_SLOTS - en_venta
            print(f"[{PRODUCTO}] en venta: {en_venta}/{MAXIMO_SLOTS} — espacios libres: {espacios}")
            return en_venta, espacios
        if intento < max_intentos - 1:
            print(f"[{PRODUCTO}] OCR no leyó número con '/' — reintentando en 2s")
            time.sleep(2)
    print(f"[{PRODUCTO}] ⚠️ no se pudo leer el contador de espacios")
    return None, None


def hay_pan_en_venta(debug=False):
    """True si el slot de referencia del listado muestra un pan puesto en
    venta (pixel calibrado en el juego: match → hay elemento)."""
    color_actual = heart.pixel(*PIXEL_HAY_PAN)
    hay = heart.pixelMatchesColor(*PIXEL_HAY_PAN, COLOR_HAY_PAN, tolerance=15)
    if debug:
        print(f"[{PRODUCTO}] hay_pan_en_venta: pixel{PIXEL_HAY_PAN}={color_actual} esperado={COLOR_HAY_PAN} → {'HAY pan listado' if hay else 'vacío'}")
    return hay


def retirar_pan():
    """Retira todos los elementos listados, uno por uno, hasta que no quede
    ninguno. Mismo patrón que retirar_minerales() en test_ir_mercado.py
    (slot fijo que se asume auto-compactado tras cada retiro)."""
    LIMITE_RETIRADAS = MAXIMO_SLOTS + 1
    retirados = 0
    print(f"[{PRODUCTO}] retirando elementos ya listados...")
    while hay_pan_en_venta(debug=True):
        if retirados >= LIMITE_RETIRADAS:
            print(f"[{PRODUCTO}] ⚠️ límite alcanzado ({retirados}/{LIMITE_RETIRADAS}) — pausando")
            return False, retirados
        heart.click(X_ITEM_LISTADO, Y_ITEM_LISTADO)
        time.sleep(0.5)
        heart.click(X_RETIRAR, Y_RETIRAR)
        time.sleep(1)
        retirados += 1
        print(f"[{PRODUCTO}] {retirados} retirado(s) — verificando lista...")
    print(f"[{PRODUCTO}] ✅ lista vacía tras {retirados} retirada(s)")
    return True, retirados


def leer_precio_actual():
    ss = heart.screenshot(region=REGION_PRECIO)
    raw = cv2.cvtColor(np.array(ss), cv2.COLOR_RGB2GRAY)
    img = cv2.resize(raw, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    _, img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    texto = pytesseract.image_to_string(img, config='--psm 7 -c tessedit_char_whitelist=0123456789')
    numero = re.sub(r'\D', '', texto.strip())
    if numero:
        precio = int(numero)
        print(f"[{PRODUCTO}] precio actual: {precio}")
        return precio
    print(f"[{PRODUCTO}] ⚠️ precio no detectado, texto='{texto.strip()}'")
    return None


def leer_cantidad_pan():
    """OCR del panel de inventario propio para saber cuánto pan hay.
    Mismo mecanismo que leer_inventario() en test_ir_mercado.py."""
    heart.click(*CLIC_ABRIR_INVENTARIO)
    time.sleep(0.5)
    ss = heart.screenshot(region=REGION_INVENTARIO)
    raw = cv2.cvtColor(np.array(ss), cv2.COLOR_RGB2GRAY)
    img = cv2.resize(raw, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    texto = pytesseract.image_to_string(img, config='--psm 6')
    print(f"[{PRODUCTO}] inventario OCR:\n{texto.strip()}")
    for linea in texto.splitlines():
        m = re.search(r'(\d{1,})\s+[Pp]an', linea)
        if m:
            cantidad = int(m.group(1))
            print(f"[{PRODUCTO}] pan en inventario: {cantidad}")
            return cantidad
    print(f"[{PRODUCTO}] ⚠️ no se detectó pan en el inventario")
    return 0


def vender_pan(lotes):
    """Vende `lotes` de pan, con precio_actual-1 (respetando PRECIO_MINIMO_PAN).
    Mismo patrón que vender_mineral() en test_ir_mercado.py."""
    print(f"[{PRODUCTO}] vendiendo {lotes} lote(s) de {TAMANO_LOTE_PAN}")
    heart.click(X_ITEM_INVENTARIO, Y_ITEM_INVENTARIO)
    time.sleep(1)
    precio_base = None
    for intento in range(1, 4):
        precio_base = leer_precio_actual()
        if precio_base is not None:
            break
        print(f"[{PRODUCTO}] precio no leído (intento {intento}/3) — reintentando...")
        time.sleep(1)
    if precio_base is None:
        print(f"[{PRODUCTO}] ⚠️ precio no leído tras 3 intentos — abortando venta")
        return False

    nuevo_precio = precio_base - 1
    if PRECIO_MINIMO_PAN > 0 and nuevo_precio < PRECIO_MINIMO_PAN:
        print(f"[{PRODUCTO}] 🚫 precio {precio_base} (→{nuevo_precio}) por debajo del mínimo ({PRECIO_MINIMO_PAN}) — no se vende")
        return 'bloqueado'

    print(f"[{PRODUCTO}] precio base: {precio_base} → {nuevo_precio}")
    for i in range(lotes):
        if i > 0:
            heart.click(X_ITEM_INVENTARIO, Y_ITEM_INVENTARIO)
            time.sleep(1)
        print(f"[{PRODUCTO}] lote {i + 1}/{lotes}")
        heart.click(X_CAMPO_PRECIO, Y_CAMPO_PRECIO)
        time.sleep(0.2)
        heart.hotkey('ctrl', 'a')
        heart.typewrite(str(nuevo_precio), interval=0.04)
        heart.click(X_CONFIRMAR, Y_CONFIRMAR)
        time.sleep(0.3)
        heart.click(X_ACEPTAR, Y_ACEPTAR)
        time.sleep(0.3)
        heart.press('enter')
        time.sleep(0.3)
        heart.press('enter')
        time.sleep(1)
    print(f"[{PRODUCTO}] ✅ completado — precio final: {nuevo_precio}")
    return True


def revisar_mercadillo():
    """Un ciclo completo: abre el puesto, retira lo que ya estaba listado y
    vende pan hasta llenar el almacén o quedarse sin pan."""
    recnec()
    any_desk()
    abrir_puesto()

    en_venta, espacios = obtener_elementos_en_venta()
    if en_venta is None:
        print(f"[{PRODUCTO}] ⚠️ no se pudo leer el puesto — se reintenta en el próximo ciclo")
        heart.press('escape')
        return

    if en_venta > 0:
        print(f"[{PRODUCTO}] hay {en_venta} elemento(s) sin vender — retirando todos")
        retirar_pan()
        en_venta, espacios = obtener_elementos_en_venta()

    if espacios and espacios > 0:
        cantidad_pan = leer_cantidad_pan()
        lotes_disponibles = cantidad_pan // TAMANO_LOTE_PAN
        lotes_a_vender = min(lotes_disponibles, espacios)
        if lotes_a_vender > 0:
            print(f"[{PRODUCTO}] {espacios} espacio(s) libre(s), {cantidad_pan} pan en inventario — vendiendo {lotes_a_vender} lote(s)")
            vender_pan(lotes_a_vender)
        else:
            print(f"[{PRODUCTO}] no hay suficiente pan para armar un lote de {TAMANO_LOTE_PAN} — nada para listar esta vuelta")

    heart.press('escape')
    time.sleep(0.5)
    print(f"[{PRODUCTO}] ciclo de revisión completado")


def loop_principal():
    print(f"[{PRODUCTO}] bot de venta iniciado — revisión cada {INTERVALO_REVISION}s")
    while True:
        try:
            revisar_mercadillo()
        except Exception as e:
            print(f"[{PRODUCTO}] ⚠️ error en el ciclo de revisión: {e}")
        restante = INTERVALO_REVISION
        while restante > 0:
            time.sleep(min(PASO_ESPERA, restante))
            restante -= PASO_ESPERA
            registrar_progreso()


if __name__ == "__main__":
    import sys

    modo = sys.argv[1] if len(sys.argv) > 1 else "run"
    print(f"Modo: {modo} — modos disponibles: diag | espacios | retirar | vender | run (default)")

    if modo == "diag":
        # Solo lee estado, no hace clics de retirar/vender — seguro para
        # correr con el mercadillo abierto y ver qué detecta el bot.
        print("=== DIAGNÓSTICO ===")
        print(f"hay_pan_en_venta(): {hay_pan_en_venta(debug=True)}")
        en_venta, espacios = obtener_elementos_en_venta()
        print(f"en_venta={en_venta} espacios={espacios}")

    elif modo == "espacios":
        abrir_puesto()
        en_venta, espacios = obtener_elementos_en_venta()
        print(f"en_venta={en_venta} espacios={espacios}")

    elif modo == "retirar":
        # Prueba solo retirar_pan() — el mercadillo debe estar ya abierto
        # con la ventana de vender visible y elementos listados.
        print("=== TEST retirar_pan() ===")
        ok, retirados = retirar_pan()
        print(f"Resultado: {'✅ lista vacía' if ok else '⚠️ límite alcanzado'} — {retirados} retirada(s)")

    elif modo == "vender":
        # Prueba solo vender_pan(1) — un lote — con la ventana de vender
        # abierta y pan disponible en el inventario.
        print("=== TEST vender_pan(1) ===")
        resultado = vender_pan(1)
        print(f"Resultado: {resultado}")

    else:
        loop_principal()
