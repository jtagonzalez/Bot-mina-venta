"""
test_ir_mercado.py — prueba aislada del flujo mercado / banco
=============================================================
Modos de ejecución (pasar como argumento):
  python test_ir_mercado.py diag          → muestra colores de mapas y píxeles clave
  python test_ir_mercado.py retirar       → prueba solo retirar_minerales()
  python test_ir_mercado.py vaciar        → prueba solo _vaciar_inventario_en_banco()
  python test_ir_mercado.py limite        → prueba solo _vaciar_banco_y_reabrir_comercio()
  python test_ir_mercado.py inventario    → prueba solo leer_inventario()
  python test_ir_mercado.py run           → flujo completo ir_mercado() (default)

Requisito: el juego debe estar visible y el personaje en mapa1, 2 o 3.
"""
import os
import sys
import time
import re
import cv2
import numpy as np
import pyautogui as heart
import pytesseract
from pathlib import Path

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

BASE_DIR = Path(__file__).resolve().parent

# ── configuración ─────────────────────────────────────────────────────────────
MAXIMO_SLOTS        = 17   # slots máximos del almacén de la tienda
CAPACIDAD_INVENTARIO = 17  # máximo de lotes que caben en el inventario del personaje

MINERALES_ORDEN = [
    ('hierro',    'hierro'),
    ('plata',     'plata'),
    ('manganeso', 'manganeso'),
    ('kovalto',   'kovalto'),
    ('bauxita',   'bauxita'),
    ('oro',       'oro'),
    ('cobre',     'cobre'),
    
    ('estaño',    'estano'),
]

REGION_BANCO = (348, 344, 216, 131)   # región calibrada del banco con filtro Mineral

# ─────────────────────────────────────────────────────────────────
# PRECIO MÍNIMO DE VENTA POR MINERAL — protección contra manipulación
# de precio (alguien lista muy barato para que el bot haga precio_base-1
# y termine regalando el mineral). Si el precio detectado es MENOR a
# este valor, el mineral NO se pone a la venta esa vuelta.
# Poné 0 para desactivar el chequeo de ese mineral (sin tope).
# Mantené esto sincronizado con PRECIO_MINIMO en el bot principal.
# ─────────────────────────────────────────────────────────────────
PRECIO_MINIMO = {
    'manganeso': 0,
    'kovalto':   0,
    'bauxita':   0,
    'cobre':     0,
    'estano':    0,
    'hierro':    500000,
    'plata':     200,
    'bronce':    0,
    'oro':       0,
}

# Minerales rechazados por precio manipulado: {clave: timestamp del rechazo}.
# Se mantiene ENTRE llamadas a ir_mercado() porque el precio del mercado no
# cambia de un viaje al siguiente.
_BLOQUEADOS_POR_PRECIO = {}
BLOQUEO_VIGENCIA_SEG = 3600   # tras 1 hora se vuelve a intentar el mineral

def _precio_minimo_de(nombre):
    """Busca el precio mínimo configurado para `nombre`, tolerando errores
    de OCR (ej. 'Estaiio' en vez de 'Estaño') comparando el inicio del
    nombre contra las claves de PRECIO_MINIMO. Retorna (minimo, clave)."""
    n = nombre.strip().lower()
    for clave, minimo in PRECIO_MINIMO.items():
        if n[:4] == clave[:4]:
            return minimo, clave
    return 0, n

# ── utilidades ────────────────────────────────────────────────────────────────

def recnec():
    pass  # sin reconexión en el test

def _ruta_imagen(nombre):
    path = Path(nombre)
    if path.is_absolute():
        return path
    for c in [BASE_DIR / path, Path.cwd() / path]:
        if c.exists():
            return c
    return BASE_DIR / path

def _leer_imagen(path):
    ruta = _ruta_imagen(path)
    if ruta is None:
        return None
    data = np.fromfile(str(ruta), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)

def _leer_portapapeles():
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        texto = root.clipboard_get()
        root.destroy()
        return texto
    except Exception:
        return ''

# ── detección de mapas ───────────────────────────────────────────────────────

def _es_mapa1():
    return (heart.pixelMatchesColor(1027, 235, (249, 238, 204), tolerance=15)
            and heart.pixelMatchesColor(1185, 362, (205,  71,   2), tolerance=15))

def _es_mapa2():
    return (heart.pixelMatchesColor(988, 180, (233, 197,   9), tolerance=15)
            and heart.pixelMatchesColor(1250, 334, (243, 227, 158), tolerance=15))

def _es_mapa3():
    return (heart.pixelMatchesColor(815, 455, ( 55,  41,  13), tolerance=15)
            and heart.pixelMatchesColor(872, 467, (180, 152,  82), tolerance=15))

def _esperar_mapa(nombre, check_fn, timeout=15):
    """Espera a que check_fn() sea verdadero. Al detectarlo, vuelve a
    confirmar tras una breve espera (debounce) para descartar falsos
    positivos de un frame de transición (ej. animación al entrar a un
    edificio) que cambia de color antes de estabilizarse."""
    t0 = time.time()
    while True:
        recnec()
        if check_fn():
            time.sleep(0.5)
            if check_fn():
                print(f"[nav] mapa detectado: {nombre}")
                return True
            print(f"[nav] {nombre}: detección transitoria descartada — reintentando...")
        if time.time() - t0 > timeout:
            print(f"[nav] ⚠️ timeout esperando {nombre} ({timeout}s)")
            for x, y in [(1027,235),(1185,362),(988,180),(1250,334),(815,455),(872,467)]:
                print(f"    ({x},{y}) -> RGB{heart.pixel(x, y)}")
            return False
        time.sleep(0.3)

def _esperar_mapa_conocido(timeout=10):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _es_mapa1() or _es_mapa2() or _es_mapa3():
            return True
        time.sleep(1)
    print(f"[nav] ⚠️ mapa no reconocido tras {timeout}s")
    for x, y in [(1027,235),(1185,362),(988,180),(1250,334),(815,455),(872,467)]:
        print(f"    ({x},{y}) -> RGB{heart.pixel(x, y)}")
    return False

def _cambiar_mapa(click_x, click_y, nombre, check_fn, max_intentos=4, timeout=15):
    for i in range(max_intentos):
        print(f"[nav] clic ({click_x},{click_y}) → {nombre} (intento {i+1}/{max_intentos})")
        heart.click(555, 555)
        time.sleep(1.5)
        heart.click(click_x, click_y, clicks=2, interval=.2)
        heart.moveTo(150, 400)
        if _esperar_mapa(nombre, check_fn, timeout=timeout):
            return True
        if i < max_intentos - 1:
            print(f"[nav] mapa no cambió — reintentando en 2s")
            time.sleep(2)
    print(f"[nav] ⚠️ no se pudo llegar a {nombre} tras {max_intentos} intentos")
    return False

# ── navegación banco ↔ mercado ────────────────────────────────────────────────

def _navegar_a_mercado():
    MAX_CICLOS = 6
    for ciclo in range(MAX_CICLOS):
        if _es_mapa3():
            print("[nav→mercado] ✅ en mercado")
            return True
        if _es_mapa1():
            print(f"[nav→mercado] ciclo {ciclo+1}: en banco → yendo a mapa exterior")
            _cambiar_mapa(535, 571, "mapa exterior", _es_mapa2)
            time.sleep(0.5)
            continue
        if _es_mapa2():
            print(f"[nav→mercado] ciclo {ciclo+1}: en mapa exterior → yendo al mercado")
            _cambiar_mapa(1264, 556, "mercado", _es_mapa3)
            time.sleep(0.5)
            continue
        print(f"[nav→mercado] ciclo {ciclo+1}: mapa no reconocido — esperando...")
        _esperar_mapa_conocido(timeout=8)
        time.sleep(1)
    print("[nav→mercado] ⚠️ no se pudo llegar al mercado")
    return False

def _ir_banco_venta():
    print("[ir_banco_venta] cerrando ventana de venta...")
    heart.press('escape')
    time.sleep(1.5)   # esperar que el mapa se estabilice tras cerrar ventana
    MAX_CICLOS = 6
    for ciclo in range(MAX_CICLOS):
        if _es_mapa1():
            print("[ir_banco_venta] ✅ llegó al banco")
            return True
        if _es_mapa3():
            print(f"[ir_banco_venta] ciclo {ciclo+1}: en mercado → yendo a mapa exterior")
            _cambiar_mapa(359, 401, "exterior jardín", _es_mapa2)
            time.sleep(0.5)
            continue
        if _es_mapa2():
            print(f"[ir_banco_venta] ciclo {ciclo+1}: en mapa exterior → yendo al banco")
            _cambiar_mapa(844, 341, "banco/sala interior", _es_mapa1)
            time.sleep(1.5)   # margen extra: entrar al edificio tarda más en estabilizarse
            continue
        print(f"[ir_banco_venta] ciclo {ciclo+1}: mapa no reconocido — esperando...")
        # Mostrar píxeles actuales para calibración
        for x, y in [(1027,235),(1185,362),(988,180),(1250,334),(815,455),(872,467)]:
            print(f"    ({x},{y}) -> RGB{heart.pixel(x, y)}")
        _esperar_mapa_conocido(timeout=8)
        time.sleep(1)
    print("[ir_banco_venta] ⚠️ no se pudo llegar al banco")
    return False

# ── comercio: leer estado ─────────────────────────────────────────────────────

def obtener_elementos_en_venta():
    def _ocr_region(region, zoom=3, whitelist=True):
        ss = heart.screenshot(region=region)
        raw = cv2.cvtColor(np.array(ss), cv2.COLOR_RGB2GRAY)
        img = cv2.resize(raw, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_CUBIC)
        _, img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        cfg = '--psm 7 -c tessedit_char_whitelist=0123456789()/' if whitelist else '--psm 7'
        return pytesseract.image_to_string(img, config=cfg), raw, img

    texto, img_raw, img_proc = _ocr_region((505, 283, 120, 36), whitelist=True)
    print(f"[OCR] texto leído: '{texto.strip()}'")

    m = re.search(r'\(?(\d{1,2})/', texto)
    if not m:
        texto2, _, _ = _ocr_region((333, 283, 290, 36), whitelist=False)
        t2 = re.sub(r'[Oo]', '0', texto2)
        print(f"[OCR] fallback: '{texto2.strip()}'")
        m = re.search(r'\(?(\d{1,2})/', t2)

    if m:
        en_venta = int(m.group(1))
        espacios = MAXIMO_SLOTS - en_venta
        print(f"[OCR] en venta: {en_venta}/{MAXIMO_SLOTS} — espacios disponibles: {espacios}")
        return en_venta, MAXIMO_SLOTS, espacios
    return None, None, None

# ── detección de inventario lleno ─────────────────────────────────────────────

def _inventario_lleno():
    """Detecta si el inventario está lleno buscando la imagen accion_cancelada.png
    en la parte inferior de la pantalla donde aparece el aviso del juego."""
    path = _ruta_imagen('accion_cancelada.png')
    if not path or not path.exists():
        print("[inv] ⚠️ accion_cancelada.png no encontrado — no se puede detectar inv lleno")
        return False
    template = _leer_imagen(path)
    if template is None:
        return False
    # Buscar solo en la franja inferior donde aparece el aviso (más rápido)
    region = (0, 850, 1280, 174)
    ss = heart.screenshot(region=region)
    haystack = cv2.cvtColor(np.array(ss), cv2.COLOR_RGB2GRAY)
    if template.shape[0] >= haystack.shape[0] or template.shape[1] >= haystack.shape[1]:
        return False
    res = cv2.matchTemplate(haystack, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(res)
    print(f"[inv] accion_cancelada conf={max_val:.3f}")
    return max_val >= 0.75

def _lista_vacia():
    return heart.pixelMatchesColor(355, 395, (180, 172, 141), tolerance=15)

# ── retirar minerales de la tienda ───────────────────────────────────────────

def retirar_minerales():
    """Retira todos los minerales de los slots de venta.
    Retorna (True, retirados) si la lista quedó vacía, (False, retirados)
    si el inventario alcanzó el límite de capacidad antes de vaciar la lista
    (conteo de retiradas, no depende de detectar la imagen de aviso del juego).
    El conteo de retirados se usa luego para saber cuántos slots del
    inventario del personaje hay que revisar al vaciar en el banco."""
    X_MINERAL, Y_MINERAL = 358, 401
    X_RETIRAR, Y_RETIRAR = 385, 633
    LIMITE_RETIRADAS = CAPACIDAD_INVENTARIO + 1
    retirados = 0
    print("[retirar] iniciando retirada hasta lista vacía...")
    while not _lista_vacia():
        if retirados >= LIMITE_RETIRADAS:
            print(f"[retirar] ⚠️ límite de inventario alcanzado ({retirados}/{LIMITE_RETIRADAS} retiradas) — pausando")
            return False, retirados
        heart.click(X_MINERAL, Y_MINERAL)
        time.sleep(0.5)
        heart.click(X_RETIRAR, Y_RETIRAR)
        time.sleep(1)
        retirados += 1
        print(f"[retirar] {retirados} retirado(s) — verificando lista...")
    print(f"[retirar] ✅ lista vacía tras {retirados} retirada(s)")
    return True, retirados

# ── banco: abrir y filtrar ────────────────────────────────────────────────────

def _clic_filtro_mineral(intentos=5, espera=1.5):
    template_path = _ruta_imagen('mineral_filtro.png')
    if not template_path or not template_path.exists():
        print("[banco] ⚠️ mineral_filtro.png no encontrado — omitiendo filtro")
        return False
    template = _leer_imagen(template_path)
    if template is None:
        return False
    region = (350, 300, 400, 350)
    for intento in range(1, intentos + 1):
        ss = heart.screenshot(region=region)
        haystack = cv2.cvtColor(np.array(ss), cv2.COLOR_RGB2GRAY)
        res = cv2.matchTemplate(haystack, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val >= 0.75:
            th, tw = template.shape
            cx = region[0] + max_loc[0] + tw // 2
            cy = region[1] + max_loc[1] + th // 2
            print(f"[banco] 'Mineral' encontrado en ({cx},{cy}) intento {intento}")
            heart.click(cx, cy)
            return True
        print(f"[banco] 'Mineral' no visible (max={max_val:.2f}) — espera {espera}s...")
        time.sleep(espera)
    print("[banco] ⚠️ 'Mineral' no encontrado")
    return False

def abrir_banco():
    print("[banco] abriendo banco...")
    time.sleep(2.5)
    heart.moveTo(947, 294, duration=0.5)
    time.sleep(0.5)
    heart.rightClick(947, 294)
    time.sleep(2.5)
    heart.click(467, 450)
    time.sleep(5.0)
    heart.click(421, 303)
    time.sleep(2.5)
    heart.click(476, 335)
    time.sleep(2.0)
    _clic_filtro_mineral(intentos=5, espera=1.5)
    time.sleep(1.5)
    print("[banco] filtro mineral activo")

# ── vaciar inventario en banco ────────────────────────────────────────────────

def _vaciar_inventario_en_banco(cantidad_items=None):
    """
    Abre el banco y deposita todos los minerales del inventario.

    El inventario del personaje se auto-compacta: al depositar el mineral
    que ocupa el slot de referencia (1045,371), el siguiente mineral (si lo
    hay) se corre automáticamente a esa misma posición. Por eso NO hace
    falta recorrer varios slots — basta con repetir el Ctrl+Doble-Click
    sobre esa única posición hasta que quede vacía de verdad.

    cantidad_items: cantidad de minerales retirados (si se conoce), usada
    solo para dimensionar el margen de intentos totales (algunos minerales
    necesitan más de un ctrl+doble-click para depositarse). Si es None se
    usa un margen genérico.

    Offsets relativos derivados del slot de referencia (1045,371):
      (1056,369) → (+11,-2)
      (1053,357) → (+8,-14)
      (1054,377) → (+9,+6)
    """
    print("[depositar] abriendo banco para vaciar inventario...")
    abrir_banco()
    time.sleep(1.0)
    heart.click(1099, 303)   # ver inventario del personaje dentro del banco
    time.sleep(1)

    SX, SY = 1045, 371
    CHECK  = [(11, -2), (8, -14), (9, 6)]
    MAX_INTENTOS = (cantidad_items if cantidad_items is not None else 15) * 3 + 2

    heart.moveTo(SX, SY, duration=0.1)
    time.sleep(0.2)

    intentos = 0
    while intentos < MAX_INTENTOS and (
        not heart.pixelMatchesColor(SX + CHECK[0][0], SY + CHECK[0][1], (190, 185, 152), tolerance=15) or
        not heart.pixelMatchesColor(SX + CHECK[1][0], SY + CHECK[1][1], (190, 185, 152), tolerance=15) or
        not heart.pixelMatchesColor(SX + CHECK[2][0], SY + CHECK[2][1], (190, 185, 152), tolerance=15)
    ):
        intentos += 1
        print(f"[depositar] intento {intentos}/{MAX_INTENTOS} — ctrl+doble-click en ({SX},{SY})...")
        time.sleep(0.4)
        heart.keyDown('ctrl')
        heart.click(clicks=2, interval=0.1)
        heart.keyUp('ctrl')

    if intentos == 0:
        print("[depositar] inventario ya estaba vacío")
    elif intentos >= MAX_INTENTOS:
        print(f"[depositar] ⚠️ no se pudo confirmar inventario vacío tras {MAX_INTENTOS} intentos")
    else:
        print(f"[depositar] ✅ inventario vaciado en {intentos} intento(s)")

    print("[depositar] cerrando banco")
    heart.press('escape')
    time.sleep(0.5)

def _vaciar_banco_y_reabrir_comercio(cantidad_items=None):
    """
    Se llama cuando retirar_minerales() alcanza el límite de capacidad del
    inventario (CAPACIDAD_INVENTARIO + 1 retiradas) antes de vaciar la lista
    de venta. Aísla todo el ciclo: cerrar la ventana de comercio, ir al banco,
    depositar el inventario y volver al mercado con la ventana de comercio
    reabierta, lista para que retirar_minerales() continúe donde quedó.

    cantidad_items: cantidad de minerales realmente retirados (se pasa a
    _vaciar_inventario_en_banco para revisar solo esos slots del inventario
    y no perder tiempo reintentando en slots que nunca tuvieron nada).

    Retorna True si el ciclo completo tuvo éxito, False si se quedó
    atascado en algún paso (navegación al banco o de vuelta al mercado).
    """
    print("[límite] inventario cerca del límite — cerrando comercio para ir al banco")
    if not _ir_banco_venta():
        print("[límite] ⚠️ no se pudo llegar al banco")
        return False

    _vaciar_inventario_en_banco(cantidad_items)

    print("[límite] volviendo al mercado para continuar retirada")
    if not _navegar_a_mercado():
        print("[límite] ⚠️ no se pudo volver al mercado")
        return False

    _reabrir_comercio()
    return True

# ── banco: detectar y extraer minerales ──────────────────────────────────────

def _buscar_todos_minerales_banco(haystack_gray):
    """Detecta todos los minerales a la vez con matriz de scores — 1 pico por mineral."""
    nombres_arch = [na for _, na in MINERALES_ORDEN]
    mmaps = {}
    for na in nombres_arch:
        path = _ruta_imagen(f"banco_{na}.png")
        if not path or not path.exists():
            continue
        tmpl = _leer_imagen(path)
        if tmpl is None:
            continue
        if tmpl.shape[0] >= haystack_gray.shape[0] or tmpl.shape[1] >= haystack_gray.shape[1]:
            continue
        th, tw = tmpl.shape
        mmap = cv2.matchTemplate(haystack_gray, tmpl, cv2.TM_CCOEFF_NORMED)
        mmaps[na] = (mmap, th, tw)

    if not mmaps:
        return {}

    DIST_MIN   = 18
    candidatos = []
    for na, (mmap, th, tw) in mmaps.items():
        _, max_val, _, max_loc = cv2.minMaxLoc(mmap)
        if max_val < 0.60:
            continue
        r, c = max_loc[1], max_loc[0]
        if all(abs(r-er) > DIST_MIN or abs(c-ec) > DIST_MIN for er, ec in candidatos):
            candidatos.append((r, c))

    if not candidatos:
        return {}

    n      = len(MINERALES_ORDEN)
    n_cand = len(candidatos)
    scores = np.zeros((n, n_cand), dtype=np.float32)
    for i, na in enumerate(nombres_arch):
        if na not in mmaps:
            continue
        mmap, th, tw = mmaps[na]
        h_map, w_map = mmap.shape
        for j, (r, c) in enumerate(candidatos):
            if 0 <= r < h_map and 0 <= c < w_map:
                scores[i, j] = mmap[r, c]

    orden = np.dstack(np.unravel_index(np.argsort(scores.ravel())[::-1], scores.shape))[0]
    asignaciones     = {}
    candidatos_usados = set()
    for i, j in orden:
        score = float(scores[i, j])
        if score < 0.60:
            break
        na = nombres_arch[i]
        if na in asignaciones or j in candidatos_usados:
            continue
        r, c = candidatos[j]
        _, th, tw = mmaps[na]
        cx = REGION_BANCO[0] + c + tw // 2
        cy = REGION_BANCO[1] + r + th // 2
        asignaciones[na] = (cx, cy, score)
        candidatos_usados.add(j)

    return asignaciones

def _leer_cantidad_drag(mineral_cx, mineral_cy, nombre):
    DRAG_DESTINO = (1053, 368)
    CLICK_CAMPO  = (903,  352)
    CLICK_CERRAR = (946,  665)

    heart.moveTo(mineral_cx, mineral_cy, duration=0.5)
    time.sleep(0.3)
    heart.mouseDown(button='left')
    time.sleep(0.3)
    heart.moveTo(*DRAG_DESTINO, duration=0.7)
    time.sleep(0.2)
    heart.mouseUp(button='left')
    time.sleep(0.7)

    heart.click(*CLICK_CAMPO)
    time.sleep(0.5)
    heart.hotkey('ctrl', 'a')
    time.sleep(0.3)
    heart.hotkey('ctrl', 'c')
    time.sleep(0.4)

    texto = _leer_portapapeles()
    nums  = re.findall(r'\d+', texto)
    print(f"    [portapapeles {nombre}] texto={repr(texto)} nums={nums}")

    resultado = int(max(nums, key=len)) if nums else 0

    for _ in range(3):
        heart.click(*CLICK_CERRAR)
        time.sleep(0.5)
    time.sleep(0.8)

    return resultado

def sacar_minerales_banco(espacios_libres, minerales_bloqueados=None):
    """minerales_bloqueados: set() opcional con claves de PRECIO_MINIMO que
    se rechazaron esta sesión por precio manipulado — se saltan al elegir
    qué sacar del banco, para no repetir el ciclo con el mismo mineral."""
    abrir_banco()
    lotes_a_traer = min(espacios_libres, CAPACIDAD_INVENTARIO)
    lotes_restantes = lotes_a_traer
    print(f"[banco] espacios libres: {espacios_libres} — extrayendo máx {lotes_a_traer} lote(s)")

    ss       = heart.screenshot(region=REGION_BANCO)
    haystack = cv2.cvtColor(np.array(ss), cv2.COLOR_RGB2GRAY)
    asignaciones = _buscar_todos_minerales_banco(haystack)
    print(f"[banco] detectados: {[(n, f'{s:.2f}') for n,(x,y,s) in asignaciones.items()]}")

    for nombre_display, nombre_archivo in MINERALES_ORDEN:
        if lotes_restantes <= 0:
            break
        if minerales_bloqueados and nombre_archivo in minerales_bloqueados:
            print(f"[banco] {nombre_display}: en lista negra esta sesión (precio manipulado) — omitiendo")
            continue
        if nombre_archivo not in asignaciones:
            print(f"[banco] {nombre_display}: no detectado — omitiendo")
            continue

        cx, cy, score = asignaciones[nombre_archivo]
        print(f"[banco] {nombre_display}: pos=({cx},{cy}) conf={score:.2f}")

        cantidad = _leer_cantidad_drag(cx, cy, nombre_archivo)
        if cantidad < 100:
            print(f"[banco] {nombre_display}: {cantidad} unidades — insuficiente")
            continue

        lotes_posibles  = cantidad // 100
        lotes_a_extraer = min(lotes_posibles, lotes_restantes)
        a_extraer       = lotes_a_extraer * 100
        print(f"[banco] {nombre_display}: extrayendo {a_extraer} ({lotes_a_extraer} lote(s))")

        try:
            heart.moveTo(cx, cy, duration=0.5)
            time.sleep(0.3)
            heart.mouseDown(button='left')
            time.sleep(0.3)
            heart.moveTo(1178, 535, duration=1.0)
            time.sleep(0.3)
            heart.mouseUp(button='left')
            time.sleep(1.0)
            heart.hotkey('ctrl', 'a')
            time.sleep(0.3)
            heart.typewrite(str(a_extraer), interval=0.08)
            time.sleep(0.3)
            heart.press('enter')
            time.sleep(1.0)
            lotes_restantes -= lotes_a_extraer
        except Exception as e:
            print(f"[banco] ⚠️ error extrayendo {nombre_display}: {e}")

    extraidos  = lotes_a_traer - lotes_restantes
    faltantes  = espacios_libres - lotes_a_traer
    msg = f"[banco] ✅ extracción completa — {extraidos} lote(s) extraídos"
    if faltantes > 0:
        msg += f" — quedan {faltantes} lote(s) faltantes por capacidad de inventario (otro viaje)"
    print(msg)
    heart.press('escape')
    time.sleep(0.5)
    return extraidos

# ── inventario y venta ────────────────────────────────────────────────────────

def leer_inventario(abrir_pestana=True):
    """abrir_pestana=False omite el clic (1117,338) que abre la pestaña del
    inventario. Se usa al releer el inventario varias veces seguidas dentro de
    la misma ronda de venta: repetir ese clic podría funcionar como toggle y
    ocultar el panel."""
    region = (1009, 379, 251, 234)
    if abrir_pestana:
        heart.click(1117, 338)
    time.sleep(0.5)
    ss = heart.screenshot(region=region)
    img_raw = cv2.cvtColor(np.array(ss), cv2.COLOR_RGB2GRAY)
    img = cv2.resize(img_raw, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    texto = pytesseract.image_to_string(img, config='--psm 6')
    print(f"[inventario] texto leído:\n{texto.strip()}")
    minerales = {}
    for linea in texto.splitlines():
        m = re.search(r'(\d{2,})\s+([A-Za-záéíóúÁÉÍÓÚñÑ]{3,})', linea)
        if m:
            minerales[m.group(2)] = int(m.group(1))
    print(f"[inventario] detectado: {minerales}")
    return minerales

def leer_precio_actual():
    region = (872, 440, 138, 33)
    ss = heart.screenshot(region=region)
    img_raw = cv2.cvtColor(np.array(ss), cv2.COLOR_RGB2GRAY)
    img = cv2.resize(img_raw, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    _, img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    texto = pytesseract.image_to_string(img, config='--psm 7 -c tessedit_char_whitelist=0123456789')
    numero = re.sub(r'\D', '', texto.strip())
    if numero:
        precio = int(numero)
        print(f"[precio] {precio}")
        return precio
    print(f"[precio] ⚠️ no detectado, texto='{texto.strip()}'")
    return None

def vender_mineral(nombre, lotes):
    print(f"[vender] {nombre}: {lotes} lote(s) de 100")
    heart.click(1177, 393)
    time.sleep(1)
    precio_base = None
    for intento in range(1, 4):
        precio_base = leer_precio_actual()
        if precio_base is not None:
            break
        print(f"[vender] {nombre}: precio no leído (intento {intento}/3) — reintentando...")
        time.sleep(1)
    if precio_base is None:
        print(f"[vender] ⚠️ precio no leído tras 3 intentos — abortando {nombre}")
        return False
    nuevo_precio = precio_base - 1

    minimo, clave = _precio_minimo_de(nombre)
    if minimo > 0 and nuevo_precio < minimo:
        print(f"[vender] 🚫 {nombre}: precio detectado {precio_base} (→{nuevo_precio}) está por debajo del mínimo configurado ({minimo}) — posible manipulación, NO se pone a la venta")
        # NO usar escape acá: cierra la ventana de comercio entera, no solo el
        # diálogo de precio, y el bot se queda abriendo y cerrando el mercadillo
        # sin vender nada. Del diálogo que queda abierto se encarga
        # poner_todos_en_venta() reabriendo la ventana de comercio.
        return 'bloqueado'

    print(f"[vender] precio base: {precio_base} → {nuevo_precio}")
    for i in range(lotes):
        if i > 0:
            heart.click(1177, 393)
            time.sleep(1)
        print(f"[vender] lote {i+1}/{lotes}")
        heart.click(910, 612)
        time.sleep(0.2)
        heart.hotkey('ctrl', 'a')
        heart.typewrite(str(nuevo_precio), interval=0.04)
        heart.click(738, 614)
        time.sleep(0.3)
        heart.click(748, 688)
        time.sleep(0.3)
        heart.press('enter')
        time.sleep(0.3)
        heart.press('enter')
        time.sleep(1)
    print(f"[vender] ✅ {nombre} completado — precio: {nuevo_precio}")
    return True

def poner_todos_en_venta(inventario, minerales_bloqueados=None):
    """Pone en venta los minerales del inventario, de arriba hacia abajo.

    IMPORTANTE: el clic (1177,393) de vender_mineral() selecciona SIEMPRE el
    primer renglón de la lista de inventario del panel de venta — no el
    mineral que se le pase por nombre. Por eso hay que releer el inventario
    en cada vuelta y trabajar siempre con su primer renglón: ese es el
    mineral cuyo precio realmente lee leer_precio_actual(). Recorrer el dict
    completo pasando nombres distintos hacía que todos los minerales se
    evaluaran con el precio del primero (todos daban el mismo número) y se
    bloquearan/blacklistearan por error.

    Retorna True si quedaron minerales sin vender en el inventario.
    """
    if not inventario:
        print("[vender] inventario vacío")
        return False

    vendidos = 0
    for vuelta in range(len(MINERALES_ORDEN) + 2):
        # La pestaña del inventario ya la abrió la lectura previa del caller;
        # no repetir el clic para no cerrarla.
        inv = leer_inventario(abrir_pestana=False)
        if not inv:
            print(f"[vender] ✅ inventario vacío — {vendidos} mineral(es) puestos en venta")
            return False

        # Primer renglón = el que selecciona el clic de vender_mineral()
        nombre, cantidad = next(iter(inv.items()))
        lotes = cantidad // 100
        if lotes == 0:
            print(f"[vender] {nombre}: {cantidad} unidades — no alcanza lote de 100; "
                  f"al ser el primer renglón no se puede llegar a los de abajo, cortando ronda")
            return True

        resultado = vender_mineral(nombre, lotes)

        if resultado == 'bloqueado':
            if minerales_bloqueados is not None:
                _, clave = _precio_minimo_de(nombre)
                minerales_bloqueados.add(clave)
                _BLOQUEADOS_POR_PRECIO[clave] = time.time()
            otros = [f"{n} x{c}" for n, c in list(inv.items())[1:]]
            if otros:
                print(f"[vender] {nombre} bloqueado y ocupa el primer renglón — no se puede llegar a "
                      f"{', '.join(otros)}; vuelven al banco y se reintentan sin {nombre}")
            else:
                print(f"[vender] {nombre} bloqueado — cortando ronda de venta")
            # El diálogo de precio quedó abierto y tapa la región del contador
            # que lee obtener_elementos_en_venta(). Hay que cerrar la ventana de
            # comercio y reabrirla: con escape se cerraba de más y el bot no
            # vendía nada, y clickear el NPC sin cerrarla antes no hace nada
            # porque la propia ventana tapa esas coordenadas.
            _reabrir_comercio(cerrar_primero=True)
            return True

        if resultado is not True:
            print(f"[vender] ⚠️ {nombre}: no se pudo vender — cortando ronda de venta")
            return True

        vendidos += 1
        time.sleep(0.5)

    print(f"[vender] ✅ ronda terminada — {vendidos} mineral(es) puestos en venta")
    return True

def _reabrir_comercio(cerrar_primero=False):
    """Abre la ventana de comercio del mercadillo estando en mapa3.

    cerrar_primero=True cuando la ventana YA está abierta y hay que dejarla en
    un estado limpio (ej. quedó encima el diálogo de 'poner a la venta' tras un
    bloqueo por precio, que tapa el contador y rompe el OCR). Sin cerrarla, los
    clics de apertura caen sobre la propia ventana en vez de sobre el NPC del
    mapa y no hacen nada.
    """
    if cerrar_primero:
        heart.click(1257, 304)   # X de la ventana de comercio
        time.sleep(1.5)
    time.sleep(0.5)
    heart.click(525, 464)
    time.sleep(0.5)
    heart.click(568, 504)
    time.sleep(2)

def _abrir_ventana_comercio():
    _reabrir_comercio()
    en_venta, maximo, espacios = obtener_elementos_en_venta()
    if en_venta is None:
        print("[mercado] ⚠️ no se pudo leer el contador de elementos")
        return None
    print(f"[mercado] en venta: {en_venta}/{maximo} — espacios libres: {espacios}")
    return espacios

# ── flujo principal ───────────────────────────────────────────────────────────

def ir_mercado():
    # Minerales rechazados por precio manipulado. Arranca con los bloqueos de
    # viajes anteriores (el precio del mercado no cambia de un viaje al
    # siguiente) y descarta los que ya vencieron.
    _ahora = time.time()
    for _clave, _ts in list(_BLOQUEADOS_POR_PRECIO.items()):
        if _ahora - _ts > BLOQUEO_VIGENCIA_SEG:
            del _BLOQUEADOS_POR_PRECIO[_clave]
    minerales_bloqueados = set(_BLOQUEADOS_POR_PRECIO)
    if minerales_bloqueados:
        print(f"[ir_mercado] bloqueados por precio de viajes anteriores: {sorted(minerales_bloqueados)}")
    print("[ir_mercado] iniciando navegación al mercado")

    if not _navegar_a_mercado():
        print("[ir_mercado] ⚠️ mapa actual no reconocido")
        return False

    print("[ir_mercado] ✅ en mercado — abriendo ventana de comercio")
    espacios = _abrir_ventana_comercio()
    if espacios is None:
        return True

    # Retirar lo ya listado SOLO si el almacén está lleno: ahí no queda dónde
    # poner mineral nuevo y hay que rearmar la lista con precios frescos.
    # Antes la condición era `espacios < MAXIMO_SLOTS` (o sea: con que hubiera
    # algo listado), así que en cada visita retiraba los mismos lotes y los
    # volvía a listar al mismo precio exacto — ~45s tirados por viaje.
    if espacios == 0:
        print("[ir_mercado] almacén lleno — retirando todo para relistar con precios frescos")
        ok, retirados = retirar_minerales()
        while not ok:
            print("[ir_mercado] inventario lleno durante retirada — yendo al banco a depositar")
            if not _vaciar_banco_y_reabrir_comercio(retirados):
                print("[ir_mercado] ⚠️ no se pudo completar el ciclo banco→mercado")
                break
            ok, retirados = retirar_minerales()
    elif espacios < MAXIMO_SLOTS:
        print(f"[ir_mercado] {MAXIMO_SLOTS - espacios} lote(s) ya listados y {espacios} espacio(s) libre(s) — se dejan como están")

    quedo_sin_vender = False
    inv = leer_inventario()
    if inv:
        print(f"[ir_mercado] inventario: {inv}")
        quedo_sin_vender = poner_todos_en_venta(inv, minerales_bloqueados)
    else:
        print("[ir_mercado] ⚠️ inventario vacío o no detectado")

    # Loop banco → mercado hasta llenar el almacén
    MAX_VUELTAS = 12   # tope de seguridad: cada vuelta cuesta la tasa del banco
    vueltas = 0
    while True:
        vueltas += 1
        if vueltas > MAX_VUELTAS:
            print(f"[ir_mercado] ⚠️ {MAX_VUELTAS} vueltas banco↔mercado — cortando por seguridad")
            break

        time.sleep(4)
        en_venta, _, espacios = obtener_elementos_en_venta()
        if en_venta is None:
            # Un diálogo abierto (ej. el de "poner a la venta" tras un bloqueo
            # por precio) tapa la región del contador y el OCR sale vacío.
            print("[ir_mercado] ⚠️ OCR falló — cerrando y reabriendo ventana de comercio")
            _reabrir_comercio(cerrar_primero=True)
            en_venta, _, espacios = obtener_elementos_en_venta()
            if en_venta is None:
                print("[ir_mercado] ⚠️ OCR falló tras reabrir — terminando")
                break
        print(f"[ir_mercado] espacios libres: {espacios}")

        if espacios == 0:
            print("[ir_mercado] almacén lleno — terminando")
            break

        if len(minerales_bloqueados) >= len(MINERALES_ORDEN):
            print("[ir_mercado] todos los minerales están bloqueados por precio — terminando")
            break

        print(f"[ir_mercado] {espacios} espacios libres — yendo al banco (vuelta {vueltas}/{MAX_VUELTAS})")

        if not _ir_banco_venta():
            print("[ir_mercado] ⚠️ no se pudo llegar al banco")
            break

        # Vaciar SIEMPRE el inventario antes de mirar qué hay en el banco.
        # sacar_minerales_banco() calcula cuántos lotes puede traer asumiendo
        # que el inventario está vacío (min(espacios_libres, CAPACIDAD_INVENTARIO));
        # si quedó mineral sin vender adentro, ese cálculo queda mal y no logra
        # traer los lotes. No se puede condicionar a una bandera: si el OCR del
        # inventario falla y devuelve {}, la bandera queda en falso aunque el
        # inventario esté lleno. Cuando ya está vacío es un no-op barato.
        if quedo_sin_vender:
            print("[ir_mercado] quedó mineral sin vender en el inventario — depositando antes de retirar otro")
        else:
            print("[ir_mercado] vaciando inventario antes de revisar el banco")
        _vaciar_inventario_en_banco()
        quedo_sin_vender = False

        extraidos = sacar_minerales_banco(espacios, minerales_bloqueados)
        if not extraidos:
            # Sin esto el bot volvía al mercado con el inventario vacío, no
            # detectaba avance y arrancaba otro viaje al banco, pagando la tasa
            # de acceso cada vez sin vender nada.
            print("[ir_mercado] el banco no tiene minerales vendibles (agotados o bloqueados) — terminando")
            break

        print("[ir_mercado] volviendo al mercado")
        if not _navegar_a_mercado():
            print("[ir_mercado] ⚠️ no se pudo volver al mercado")
            break

        # Ventana cerrada al ir al banco — abrirla de nuevo
        _reabrir_comercio()

        inv = leer_inventario()
        if inv:
            print(f"[ir_mercado] poniendo en venta: {inv}")
            quedo_sin_vender = poner_todos_en_venta(inv, minerales_bloqueados)
        else:
            print("[ir_mercado] ⚠️ inventario vacío tras extracción del banco")
            quedo_sin_vender = False

    # Clic en el botón de cerrar la ventana de comercio en vez de escape —
    # si algún paso anterior falló y la ventana ya no está, este clic no
    # hace nada dañino, mientras que escape abriría el menú de
    # configuración del juego y dejaría esa ventana bloqueando el bot.
    time.sleep(1)
    heart.click(1257, 304)
    time.sleep(2)

    # Si se corta el ciclo con mineral sin vender encima (ej. bloqueado por
    # precio, u OCR que no se recupera), depositarlo antes de volver a la mina.
    if quedo_sin_vender:
        print("[ir_mercado] queda mineral sin vender — depositándolo en el banco antes de volver a la mina")
        if _ir_banco_venta():
            _vaciar_inventario_en_banco()
        else:
            print("[ir_mercado] ⚠️ no se pudo llegar al banco para depositar lo que quedó")
    return True

# ── diagnóstico ───────────────────────────────────────────────────────────────

def diagnostico():
    print("=== DIAGNÓSTICO DE MAPAS ===")
    print(f"  mapa1 (banco)   : {_es_mapa1()}")
    print(f"  mapa2 (exterior): {_es_mapa2()}")
    print(f"  mapa3 (mercado) : {_es_mapa3()}")
    print(f"  inventario lleno: {_inventario_lleno()}")
    print(f"  lista vacía     : {_lista_vacia()}")
    puntos = [
        (1027, 235, "mapa1 punto 1"),
        (1185, 362, "mapa1 punto 2"),
        (988, 180, "mapa2 punto 1"),
        (1250, 334, "mapa2 punto 2"),
        (815, 455, "mapa3 punto 1"),
        (872, 467, "mapa3 punto 2"),
        (355, 395, "lista vacía"),
    ]
    print("\n  Colores actuales:")
    for x, y, desc in puntos:
        c = heart.pixel(x, y)
        print(f"    ({x:4d},{y:3d}) {desc:35s} → RGB{c}")
    print("============================\n")

# ── ejecución ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "run"

    print(f"Modo: {modo} — tienes 3 segundos para poner el juego en pantalla...")
    time.sleep(3)

    if modo == "diag":
        diagnostico()

    elif modo == "retirar":
        # Prueba solo retirar_minerales() — el juego debe tener la tienda abierta
        print("=== TEST retirar_minerales() ===")
        ok, retirados = retirar_minerales()
        print(f"Resultado: {'✅ lista vacía' if ok else '⚠️ inventario lleno'} — {retirados} retirada(s)")

    elif modo == "vaciar":
        # Prueba solo _vaciar_inventario_en_banco() — personaje en mapa1
        print("=== TEST _vaciar_inventario_en_banco() ===")
        _vaciar_inventario_en_banco()

    elif modo == "limite":
        # Prueba solo _vaciar_banco_y_reabrir_comercio() — personaje en mercado
        # con la ventana de comercio abierta, simulando límite de inventario alcanzado
        print("=== TEST _vaciar_banco_y_reabrir_comercio() ===")
        ok = _vaciar_banco_y_reabrir_comercio()
        print(f"Resultado: {'✅ ciclo completo' if ok else '⚠️ falló en algún paso'}")

    elif modo == "inventario":
        # Prueba solo leer_inventario() — ventana de comercio abierta
        print("=== TEST leer_inventario() ===")
        inv = leer_inventario()
        print(f"Inventario detectado: {inv}")

    else:
        # Flujo completo
        diagnostico()
        resultado = ir_mercado()
        print(f"\nResultado final: {'✅ éxito' if resultado else '❌ falló'}")
