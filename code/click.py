"""
Calibrador de coordenadas.

- Muestra la posicion del mouse EN VIVO.
- Ctrl + click  -> guarda esa coordenada (la imprime y la agrega a coords.txt).
- Esc           -> salir.

Util para calibrar el bloque CONFIG / PROFILES de attack.py: pone el juego en pantalla,
manten Ctrl y clickea cada elemento (slot de tropa, vertice de despliegue, boton, etc.).
Cada Ctrl+click queda anotado en coords.txt y en la consola.
"""

import time
import pyautogui
from pynput import keyboard, mouse

_CTRL_KEYS = {keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}
_ctrl_down = False
_saved = []
OUT_FILE = "coords.txt"


def _on_press(key):
    global _ctrl_down
    if key in _CTRL_KEYS:
        _ctrl_down = True
    if key == keyboard.Key.esc:
        return False            # detiene el listener de teclado -> termina el programa


def _on_release(key):
    global _ctrl_down
    if key in _CTRL_KEYS:
        _ctrl_down = False


def _on_click(x, y, button, pressed):
    if pressed and _ctrl_down:
        _saved.append((x, y))
        line = f"x{x} y{y}"
        with open(OUT_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(f"\nGUARDADO -> {line}   (total {len(_saved)})", flush=True)


print("Calibrador activo.")
print("  - Move el mouse para ver X/Y.")
print("  - Ctrl + click  = guardar coordenada (se anota en coords.txt).")
print("  - Esc           = salir.\n")

kb_listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
mouse_listener = mouse.Listener(on_click=_on_click)
kb_listener.start()
mouse_listener.start()

try:
    while kb_listener.running:
        x, y = pyautogui.position()
        print(f"X: {str(x).rjust(4)}  Y: {str(y).rjust(4)}   (Ctrl+click para guardar)   ",
              end="\r", flush=True)
        time.sleep(0.05)
except KeyboardInterrupt:
    pass
finally:
    mouse_listener.stop()

print(f"\n\nGuardadas {len(_saved)} coordenadas en {OUT_FILE}")
for i, (x, y) in enumerate(_saved):
    print(f"  {i}: x{x} y{y}")
