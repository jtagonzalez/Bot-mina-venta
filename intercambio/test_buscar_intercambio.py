"""Diagnóstico: hace clic en el compañero (arriba o abajo) y busca
intercambiar.png en TODA la pantalla, reportando dónde encontró la mejor
coincidencia (aunque no pase el umbral). Guarda capturas para inspección.

Uso: python test_buscar_intercambio.py [arriba|abajo]
"""
import os
import sys
import time
import cv2
import numpy as np
import pyautogui as heart

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun

PUNTOS_CLIC_COMPAÑERO = {
    "arriba": (1261, 264),
    "abajo": (1257, 296),
}

# Mismo offset calibrado que usa emisor.py
_MENU_OFFSET_X = 1071 - 1261
_MENU_OFFSET_Y = 246 - 264
_MENU_ANCHO = 1279 - 1071
_MENU_ALTO = 692 - 246


def main():
    posicion = sys.argv[1] if len(sys.argv) > 1 else "abajo"
    x, y = PUNTOS_CLIC_COMPAÑERO.get(posicion, PUNTOS_CLIC_COMPAÑERO["abajo"])
    region = (max(0, x + _MENU_OFFSET_X), max(0, y + _MENU_OFFSET_Y), _MENU_ANCHO, _MENU_ALTO)

    print(f"En 3 segundos se hará clic en ({x},{y}) [{posicion}] — deja el juego visible...")
    time.sleep(3)
    heart.click(x, y)
    time.sleep(1)

    ss = heart.screenshot()
    img_bgr = cv2.cvtColor(np.array(ss), cv2.COLOR_RGB2BGR)
    ruta_completa = os.path.join(comun._DIR, "debug_menu_completo.png")
    cv2.imwrite(ruta_completa, img_bgr)
    print(f"Captura completa de pantalla guardada en: {ruta_completa}")

    ruta_region = os.path.join(comun._DIR, "debug_menu_region.png")
    rx, ry, rw, rh = region
    cv2.imwrite(ruta_region, img_bgr[ry:ry + rh, rx:rx + rw])
    print(f"Recorte de la región calibrada ({region}) guardado en: {ruta_region}")

    # ── comparación por imagen, en TODA la pantalla ──
    template_path = os.path.join(comun._DIR, "intercambiar.png")
    template = comun._leer_imagen(template_path)
    if template is None:
        print(f"⚠️ No se pudo leer {template_path}")
    else:
        haystack = cv2.cvtColor(np.array(ss), cv2.COLOR_RGB2GRAY)
        res = cv2.matchTemplate(haystack, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        th, tw = template.shape
        cx = max_loc[0] + tw // 2
        cy = max_loc[1] + th // 2
        print()
        print("=== Comparación por IMAGEN (intercambiar.png) en TODA la pantalla ===")
        print(f"  confianza = {max_val:.3f}  (umbral usado en emisor.py = 0.60)")
        print(f"  posición  = ({cx}, {cy})")
        print(f"  respecto al clic ({x},{y}): offset = ({cx - x}, {cy - y})")

        y0, y1 = max(0, max_loc[1] - 30), max_loc[1] + th + 30
        x0, x1 = max(0, max_loc[0] - 30), max_loc[0] + tw + 30
        recorte = img_bgr[y0:y1, x0:x1]
        ruta_recorte = os.path.join(comun._DIR, "debug_menu_recorte.png")
        cv2.imwrite(ruta_recorte, recorte)
        print(f"  recorte guardado en: {ruta_recorte}")

    # ── comparación por OCR, dentro de la región calibrada ──
    print()
    print("=== Comparación por OCR ('intercambio') en la región calibrada ===")
    import pytesseract
    img_gray = cv2.cvtColor(np.array(heart.screenshot(region=region)), cv2.COLOR_RGB2GRAY)
    img_zoom = cv2.resize(img_gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, img_th = cv2.threshold(img_zoom, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ruta_ocr = os.path.join(comun._DIR, "debug_menu_ocr.png")
    cv2.imwrite(ruta_ocr, img_th)
    texto_completo = pytesseract.image_to_string(img_th, config="--psm 6")
    print(f"  texto leído en la región:\n{texto_completo}")
    print(f"  imagen usada para OCR guardada en: {ruta_ocr}")
    resultado_ocr = comun.buscar_texto_en_region("intercambio", region)
    print(f"  resultado buscar_texto_en_region: {resultado_ocr}")


if __name__ == "__main__":
    main()
