import cv2
import numpy as np
import os
import re
import time
import pyautogui as heart

_DIR = os.path.dirname(os.path.abspath(__file__))

# Región exacta del banco (de la calibración del usuario)
REGION_BANCO = (348, 344, 216, 131)   # x, y, ancho, alto

MINERALES = [
    ('manganeso', 'manganeso'),
    ('kovalto',   'kovalto'),
    ('bauxita',   'bauxita'),
    ('oro',       'oro'),
    ('cobre',     'cobre'),
    ('hierro',    'hierro'),
    ('plata',     'plata'),
    ('estaño',    'estano'),
]

# ─────────────────────────────────────────────────────────────────────────────
def _leer_imagen(path):
    data = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)


def buscar_todos_minerales(haystack_gray):
    """
    Busca todos los minerales a la vez.

    Construye una matriz de scores  [n_minerales × n_candidatos]  con numpy:
    cada celda (i, j) = similitud del template i en la posición candidata j.

    Luego ordena todas las celdas de mayor a menor y asigna greedily:
    - cada mineral recibe solo 1 posición
    - cada posición es tomada por solo 1 mineral
    → elimina confusiones entre minerales parecidos.

    Devuelve dict { nombre_archivo → (cx, cy, score) }
    """
    n = len(MINERALES)
    nombres_disp  = [nd for nd, _  in MINERALES]
    nombres_arch  = [na for _,  na in MINERALES]

    # ── 1. Calcular mapa de similitudes para cada mineral ────────────────────
    mmaps = {}   # nombre_archivo → (mmap_np, th, tw)
    for na in nombres_arch:
        path = os.path.join(_DIR, f"banco_{na}.png")
        if not os.path.exists(path):
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

    # ── 2. Recopilar candidatos de posición: 1 pico por mineral ─────────────
    # Un solo pico por mineral evita que picos falsos bloqueen posiciones
    # de otros minerales (ej. bauxita 3er pico bloqueaba a plata).
    candidatos = []   # lista de (r, c) en coords del mapa de resultados
    DIST_MIN   = 18   # píxeles mínimos entre candidatos distintos

    for na, (mmap, th, tw) in mmaps.items():
        _, max_val, _, max_loc = cv2.minMaxLoc(mmap)
        if max_val < 0.60:
            continue
        r, c = max_loc[1], max_loc[0]
        if all(abs(r - er) > DIST_MIN or abs(c - ec) > DIST_MIN
               for er, ec in candidatos):
            candidatos.append((r, c))

    if not candidatos:
        return {}

    n_cand = len(candidatos)

    # ── 3. Matriz de scores con numpy  [n_minerales × n_candidatos] ──────────
    scores = np.zeros((n, n_cand), dtype=np.float32)

    for i, na in enumerate(nombres_arch):
        if na not in mmaps:
            continue
        mmap, th, tw = mmaps[na]
        h_map, w_map = mmap.shape
        for j, (r, c) in enumerate(candidatos):
            if 0 <= r < h_map and 0 <= c < w_map:
                scores[i, j] = mmap[r, c]

    # ── 4. Asignación óptima greedy por score descendente ────────────────────
    # Ordenar TODOS los pares (mineral, candidato) de mayor a menor score
    orden = np.dstack(
        np.unravel_index(np.argsort(scores.ravel())[::-1], scores.shape)
    )[0]   # shape (n*n_cand, 2)  → cada fila = (i_mineral, j_candidato)

    asignaciones    = {}   # nombre_archivo → (cx, cy, score)
    candidatos_usados = set()

    for i, j in orden:
        score = float(scores[i, j])
        if score < 0.60:
            break
        na = nombres_arch[i]
        if na in asignaciones:
            continue   # mineral ya asignado
        if j in candidatos_usados:
            continue   # posición ya tomada

        r, c = candidatos[j]
        _, th, tw = mmaps[na]
        cx = REGION_BANCO[0] + c + tw // 2
        cy = REGION_BANCO[1] + r + th // 2
        asignaciones[na] = (cx, cy, score)
        candidatos_usados.add(j)

    return asignaciones


# ─────────────────────────────────────────────────────────────────────────────
def _leer_portapapeles():
    """Lee el portapapeles con tkinter (sin dependencias extra)."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        texto = root.clipboard_get()
        root.destroy()
        return texto
    except Exception:
        return ''


def leer_cantidad_drag(mineral_cx, mineral_cy, nombre):
    DRAG_DESTINO = (1053, 368)
    CLICK_CAMPO  = (903,  352)
    CLICK_CERRAR = (946,  665)
    REGION_CAMPO = (930, 336, 110, 30)

    # 1. Arrastrar mineral al slot de venta
    heart.moveTo(mineral_cx, mineral_cy, duration=0.5)
    time.sleep(0.3)
    heart.mouseDown(button='left')
    time.sleep(0.3)
    heart.moveTo(*DRAG_DESTINO, duration=0.7)
    time.sleep(0.2)
    heart.mouseUp(button='left')
    time.sleep(0.7)

    # 2. Activar el campo y copiar al portapapeles
    heart.click(*CLICK_CAMPO)
    time.sleep(0.5)
    heart.hotkey('ctrl', 'a')
    time.sleep(0.3)
    heart.hotkey('ctrl', 'c')
    time.sleep(0.4)

    # 3. Leer del portapapeles
    texto = _leer_portapapeles()
    nums  = re.findall(r'\d+', texto)
    print(f"    [Portapapeles {nombre}] texto={repr(texto)} nums={nums}")

    # Guardar debug visual
    ss     = heart.screenshot(region=REGION_CAMPO)
    img    = cv2.cvtColor(np.array(ss), cv2.COLOR_RGB2GRAY)
    img_3x = cv2.resize(img, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    img_pad = cv2.copyMakeBorder(img_3x, 15, 15, 15, 15, cv2.BORDER_CONSTANT, value=255)
    cv2.imwrite(os.path.join(_DIR, f"debug_cant_{nombre}_campo.png"), img_pad)

    resultado = int(max(nums, key=len)) if nums else 0

    # 4. Cerrar formulario — 3 clics con pausa
    for _ in range(3):
        heart.click(*CLICK_CERRAR)
        time.sleep(0.5)
    time.sleep(0.8)

    return (resultado, "portapapeles") if resultado else (0, "no leído")


# ═════════════════════════════════════════════════════════════════════════════
print("=== TEST DETECCIÓN Y CANTIDAD DE MINERALES EN BANCO ===")
print(f"Región banco: {REGION_BANCO}")
print()
print("Pon el banco abierto con filtro Mineral activo y presiona Enter...")
input()

# Limpiar imágenes debug de corridas anteriores
for f in os.listdir(_DIR):
    if f.startswith('debug_') and f.endswith('.png'):
        try:
            os.remove(os.path.join(_DIR, f))
        except OSError:
            pass

# Captura única del banco
ss_banco    = heart.screenshot(region=REGION_BANCO)
haystack    = cv2.cvtColor(np.array(ss_banco), cv2.COLOR_RGB2GRAY)
img_region  = cv2.cvtColor(np.array(ss_banco), cv2.COLOR_RGB2BGR)
cv2.imwrite(os.path.join(_DIR, "debug_region_banco.png"), img_region)
print("Screenshot guardado: debug_region_banco.png")
print()

# Búsqueda simultánea con matriz de scores
asignaciones = buscar_todos_minerales(haystack)

for nombre_display, nombre_archivo in MINERALES:
    if nombre_archivo not in asignaciones:
        print(f"  {nombre_display:12s}: ❌ no encontrado")
        continue

    cx, cy, score = asignaciones[nombre_archivo]
    estado = "✅ ENCONTRADO" if score >= 0.80 else "⚠ confianza baja"
    cantidad, fuente = leer_cantidad_drag(cx, cy, nombre_archivo)
    lotes = cantidad // 100
    print(f"  {nombre_display:12s}: {estado} conf={score:.2f} pos=({cx},{cy})"
          f" | cantidad={cantidad} → {lotes} lote(s)  [{fuente}]")

print()
print("=== FIN ===")
print("Revisa debug_cant_*_orig.png y debug_region_banco.png para inspección.")
