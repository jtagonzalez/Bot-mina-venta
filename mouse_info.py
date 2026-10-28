import pyautogui
import time

print("Mostrando posición y RGB en tiempo real. Ctrl+C para salir.\n")

x, y, r, g, b = 0, 0, 0, 0, 0

try:
    while True:
        x, y = pyautogui.position()
        r, g, b = pyautogui.pixel(x, y)
        print(f"Pos: ({x:4}, {y:4})  |  RGB: ({r:3}, {g:3}, {b:3})", end="\r")
        time.sleep(0.1)
except KeyboardInterrupt:
    print(f"\n\n--- Último valor capturado ---")
    print(f"Posición : ({x}, {y})")
    print(f"RGB      : ({r}, {g}, {b})")
    print(f"pyautogui: heart.pixelMatchesColor({x}, {y}, ({r}, {g}, {b}), tolerance=10)")
