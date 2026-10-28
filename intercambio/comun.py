"""Utilidades compartidas por emisor.py y receptor.py: reconexión,
espera dinámica por renderización, detección de minerales por imagen
y lectura/escritura de la configuración de la cola de intercambio."""
import os
import json
import time
import cv2
import numpy as np
import pyautogui as heart
import pytesseract

# Ruta por defecto del instalador de Tesseract-OCR en Windows. Solo se fija
# si existe ahí — si la máquina lo instaló en otra ubicación pero lo agregó
# al PATH del sistema (opción del instalador), pytesseract lo encuentra solo.
_TESSERACT_DEFAULT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(_TESSERACT_DEFAULT):
    pytesseract.pytesseract.tesseract_cmd = _TESSERACT_DEFAULT

_DIR = os.path.dirname(os.path.abspath(__file__))
_IMAGENES_DIR = os.path.dirname(_DIR)  # carpeta del bot, un nivel arriba de intercambio/

CONFIG_PATH = os.path.join(_DIR, "cola_config.json")

MINERALES_DISPONIBLES = [
    'manganeso', 'kovalto', 'bauxita', 'oro', 'cobre', 'hierro', 'plata', 'estano', 'bronce',
]


def recnec():
    """Detecta y resuelve la pantalla de desconexión del juego."""
    if (heart.pixelMatchesColor(772, 546, (255, 97, 0), tolerance=15)
            or heart.pixelMatchesColor(655, 448, (220, 129, 0), tolerance=15)
            or heart.pixelMatchesColor(767, 527, (255, 97, 0), tolerance=15)
            or heart.pixelMatchesColor(766, 556, (255, 97, 0), tolerance=15)
            or heart.pixelMatchesColor(848, 560, (250, 95, 0), tolerance=15)):
        print("[recnec] desconexión detectada — reconectando...")
        while True:
            if (heart.pixelMatchesColor(772, 546, (255, 97, 0), tolerance=15)
                    or heart.pixelMatchesColor(655, 448, (220, 129, 0), tolerance=15)
                    or heart.pixelMatchesColor(767, 527, (255, 97, 0), tolerance=15)):
                heart.click(767, 527)
                time.sleep(1)
                heart.click(772, 547)
                time.sleep(1)
                heart.click(655, 448)
            if heart.pixelMatchesColor(852, 562, (255, 97, 0), tolerance=15):
                while True:
                    if heart.pixelMatchesColor(852, 562, (255, 97, 0), tolerance=15):
                        heart.click(852, 562)
                        time.sleep(1)
                        heart.click(657, 448)
                    if (heart.pixelMatchesColor(702, 366, (41, 38, 31), tolerance=15)
                            and heart.pixelMatchesColor(690, 420, (6, 155, 216), tolerance=15)):
                        break
            if (heart.pixelMatchesColor(702, 366, (41, 38, 31), tolerance=15)
                    and heart.pixelMatchesColor(690, 420, (6, 155, 216), tolerance=15)):
                heart.moveTo(687, 429)
                heart.click(clicks=2, interval=0.1)
            if (heart.pixelMatchesColor(763, 709, (236, 142, 2), tolerance=15)
                    and heart.pixelMatchesColor(771, 667, (121, 111, 90), tolerance=15)):
                heart.moveTo(477, 495)
                heart.click(clicks=2, interval=0.1)
            if heart.pixelMatchesColor(864, 727, (216, 1, 1), tolerance=15):
                time.sleep(5)
                break
        print("[recnec] reconectado")


_ultimo_recnec = [0.0]


def _recnec_sondeo():
    """Versión de recnec() limitada a una vez cada 2s, para usar dentro de
    sondeos rápidos (esperar_condicion y similares). recnec() hace 5
    capturas de pantalla por llamada; invocarla en cada iteración de un
    sondeo de 0.3s multiplica el costo real muy por encima del timeout
    declarado. La desconexión no necesita detectarse con esa frecuencia."""
    ahora = time.time()
    if ahora - _ultimo_recnec[0] > 2:
        recnec()
        _ultimo_recnec[0] = ahora


def esperar_condicion(check_fn, timeout=15, intervalo=0.3, nombre="condición"):
    """Espera dinámica: sondea check_fn() hasta que sea verdadero o venza el timeout.
    Reemplaza los time.sleep(N) fijos por espera basada en lo que realmente se renderiza."""
    t0 = time.time()
    while True:
        _recnec_sondeo()
        if check_fn():
            return True
        if time.time() - t0 > timeout:
            print(f"[esperar] ⚠️ timeout esperando {nombre} ({timeout}s)")
            return False
        time.sleep(intervalo)


def esperar_recinto_banco(timeout=10):
    """Espera a estar dentro del recinto del banco (pixel de referencia)."""
    return esperar_condicion(
        lambda: heart.pixelMatchesColor(441, 334, (129, 128, 33), tolerance=15),
        timeout=timeout, nombre="recinto del banco",
    )


def abrir_ventana_buho():
    """Hace clic en el búho del banco y espera a que se abra su ventana de
    diálogo. Usado tanto para sacar como para meter recursos."""
    heart.click(941, 284)
    time.sleep(0.3)
    heart.click(973, 297)
    return esperar_condicion(
        lambda: heart.pixelMatchesColor(376, 250, (255, 208, 102), tolerance=15),
        timeout=10, nombre="ventana del búho",
    )


def abrir_pestaña_recurso():
    """Navega desde la ventana del búho hasta la pestaña de recurso del
    banco (avanza el diálogo y selecciona la categoría de recursos)."""
    heart.click(421, 458)
    time.sleep(0.3)
    heart.click(1098, 300)
    time.sleep(0.3)
    heart.click(426, 299)
    return esperar_condicion(
        lambda: heart.pixelMatchesColor(424, 291, (81, 74, 60), tolerance=15),
        timeout=10, nombre="pestaña de recurso",
    )


def _leer_imagen(path):
    data = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)


def _buscar_imagen_por_ruta(path, region, umbral):
    """Busca la imagen en `path` dentro de region=(x,y,w,h) de la pantalla.
    Retorna (cx, cy, score) o None si no existe el archivo o no aparece
    con suficiente confianza."""
    if not os.path.exists(path):
        print(f"[buscar] ⚠️ no existe la imagen {path}")
        return None
    template = _leer_imagen(path)
    if template is None:
        return None
    ss = heart.screenshot(region=region)
    haystack = cv2.cvtColor(np.array(ss), cv2.COLOR_RGB2GRAY)
    if template.shape[0] >= haystack.shape[0] or template.shape[1] >= haystack.shape[1]:
        return None
    res = cv2.matchTemplate(haystack, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val < umbral:
        return None
    th, tw = template.shape
    cx = region[0] + max_loc[0] + tw // 2
    cy = region[1] + max_loc[1] + th // 2
    return (cx, cy, max_val)


def clic_filtro_mineral(intentos=5, espera=1.5, region=(350, 300, 400, 350), umbral=0.75):
    """Busca la palabra 'Mineral' (mineral_filtro.png) en la ventana del
    banco y le da clic — mismo mecanismo que _clic_filtro_mineral() en
    anu-ventas.py, para asegurar el filtro correcto antes de buscar un
    mineral específico."""
    path = os.path.join(_IMAGENES_DIR, "mineral_filtro.png")
    for intento in range(1, intentos + 1):
        resultado = _buscar_imagen_por_ruta(path, region, umbral)
        if resultado is not None:
            cx, cy, score = resultado
            print(f"[banco] 'Mineral' encontrado en ({cx},{cy}) intento {intento} conf={score:.2f}")
            heart.click(cx, cy)
            return True
        print(f"[banco] 'Mineral' no visible (intento {intento}/{intentos}) — espera {espera}s...")
        time.sleep(espera)
    print("[banco] ⚠️ 'Mineral' no encontrado tras todos los intentos")
    return False


def buscar_mineral_en_region(nombre_mineral, region, umbral=0.6):
    """Busca banco_<mineral>.png (carpeta del bot) dentro de region=(x,y,w,h).
    Retorna (cx, cy, score) o None si no aparece con suficiente confianza."""
    path = os.path.join(_IMAGENES_DIR, f"banco_{nombre_mineral}.png")
    return _buscar_imagen_por_ruta(path, region, umbral)


def esperar_mineral_en_region(nombre_mineral, region, timeout=15, umbral=0.6):
    """Espera dinámicamente hasta que el mineral aparezca en la región dada.
    Retorna (cx, cy, score) o None si venció el timeout."""
    t0 = time.time()
    while True:
        _recnec_sondeo()
        resultado = buscar_mineral_en_region(nombre_mineral, region, umbral=umbral)
        if resultado is not None:
            return resultado
        if time.time() - t0 > timeout:
            print(f"[buscar] ⚠️ timeout esperando {nombre_mineral} en pantalla ({timeout}s)")
            return None
        time.sleep(0.3)


def buscar_imagen_en_region(nombre_archivo, region, umbral=0.7):
    """Busca una imagen guardada en la carpeta intercambio/ (ej. intercambiar.png,
    el menú contextual) dentro de region=(x,y,w,h). Retorna (cx, cy, score) o None."""
    path = os.path.join(_DIR, nombre_archivo)
    return _buscar_imagen_por_ruta(path, region, umbral)


def esperar_imagen_en_region(nombre_archivo, region, timeout=10, umbral=0.7):
    """Espera dinámicamente hasta que la imagen aparezca en la región dada.
    Retorna (cx, cy, score) o None si venció el timeout."""
    t0 = time.time()
    while True:
        _recnec_sondeo()
        resultado = buscar_imagen_en_region(nombre_archivo, region, umbral=umbral)
        if resultado is not None:
            return resultado
        if time.time() - t0 > timeout:
            print(f"[buscar] ⚠️ timeout esperando {nombre_archivo} en pantalla ({timeout}s)")
            return None
        time.sleep(0.3)


def buscar_texto_en_region(texto, region, zoom=2):
    """Busca `texto` (insensible a mayúsculas, coincidencia parcial) dentro
    de region=(x,y,w,h) usando OCR. No depende de colores/resaltados como
    la comparación de imagen, así que sirve para menús donde una fila puede
    verse resaltada o no según el mouse. Retorna (cx, cy) del centro del
    texto encontrado, o None si no aparece."""
    ss = heart.screenshot(region=region)
    img_raw = cv2.cvtColor(np.array(ss), cv2.COLOR_RGB2GRAY)
    img = cv2.resize(img_raw, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_CUBIC)
    _, img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    datos = pytesseract.image_to_data(img, config="--psm 6", output_type=pytesseract.Output.DICT)
    objetivo = texto.strip().lower()
    n = len(datos["text"])
    for i in range(n):
        palabra = datos["text"][i].strip()
        if not palabra or objetivo not in palabra.lower():
            continue
        x, y, w, h = datos["left"][i], datos["top"][i], datos["width"][i], datos["height"][i]
        cx = region[0] + (x + w // 2) // zoom
        cy = region[1] + (y + h // 2) // zoom
        return (cx, cy)
    return None


def esperar_texto_en_region(texto, region, timeout=10):
    """Espera dinámicamente hasta que `texto` aparezca (por OCR) en la
    región dada. Retorna (cx, cy) o None si venció el timeout."""
    t0 = time.time()
    while True:
        _recnec_sondeo()
        resultado = buscar_texto_en_region(texto, region)
        if resultado is not None:
            return resultado
        if time.time() - t0 > timeout:
            print(f"[buscar] ⚠️ timeout esperando texto '{texto}' en pantalla ({timeout}s)")
            return None
        time.sleep(0.3)


def cargar_config():
    if not os.path.exists(CONFIG_PATH):
        return {"capacidad_inventario": 0, "posicion_companero": "abajo", "cola": []}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
