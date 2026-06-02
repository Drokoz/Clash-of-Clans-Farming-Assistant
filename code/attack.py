"""
Modo de ataque automatico para farmear estrellas/trofeos rapido.

Secuencia por base:
    1. Despliega valkirias en circulo alrededor de la base.
    2. Lanza los hechizos (ej. totem / rabia) al centro.
    3. Despliega los heroes y activa sus habilidades.
    4. Lee el % de destruccion con OCR y termina la batalla apenas llega a 50%.

================================  CALIBRACION  ================================
Casi todo aca son coordenadas de pantalla, propias de TU monitor (pensado para
1080p y Clash of Clans via Google Play Games for Windows, ventana maximizada).

Para conseguirlas:
    1. Abri el juego y entra a una batalla de practica/normal.
    2. Corre en otra terminal:   python click.py
    3. Mové el mouse sobre cada elemento (icono de valkiria, centro de la base,
       boton de terminar, etc.) y anotá los valores X / Y que imprime.
    4. Pegá esos numeros en el bloque CONFIG de abajo.

Si algo se despliega en el lugar equivocado, es casi siempre una coordenada mal
calibrada. Ajustá y reintentá.
==============================================================================
"""

import os
import re
import time
import math
import random
import warnings

import cv2
import easyocr
import pyautogui

from utils import screenshot

# La GTX 1650 no soporta cierto plan de cuDNN para easyOCR; usa un fallback y funciona
# igual. Silenciamos ese warning para no ensuciar la consola.
warnings.filterwarnings("ignore", message=".*cudnn.*")

# ============================= CONFIG (CALIBRAR) =============================

# --- Anillo verde de despliegue: 4 LINEAS (bordes del "diamante"), calibradas ---
# Cada linea es (inicio, fin). Valkirias y heroes se despliegan SOBRE estas lineas
# (zona verde, fuera de la roja). Hay huecos arriba-centro y abajo-centro (zonas de UI).
DEPLOY_LINES = [
    ((275, 482), (892, 49)),     # izquierda-superior
    ((1127, 51), (1749, 497)),   # derecha-superior
    ((1749, 497), (1230, 849)),  # derecha-inferior
    ((737, 856), (275, 482)),    # izquierda-inferior
]
# Valkirias: FUERZA BRUTA. Son siempre VALK_TOTAL; se reparten en las 4 lineas (zonas) y
# se tapean una por una, espaciadas a lo largo de cada linea (maxima area de ataque).
VALK_TOTAL = 37
VALK_TAP_PAUSE = 0.06       # seg entre cada tap (mas chico = mas rapido)

# --- Anti-script: aleatoriedad para no parecer un bot ---
# Variacion aleatoria (px) que se suma a CADA coordenada de despliegue.
RANDOM_JITTER = 18
# Variacion aleatoria (seg) que se suma a las pausas entre acciones.
RANDOM_PAUSE = 0.05

# Heroes: UNO por vertice del diamante (zona verde). Orden: Champion, Warden, Rey, Reina.
HERO_DEPLOY_POINTS = [(275, 482), (1127, 51), (1749, 497), (737, 856)]  # izq, arriba, der, abajo

# Centro de la base enemiga. Los totems SI se pueden tirar ADENTRO de la roja, asi que
# los repartimos en un circulo chico alrededor del centro (cubren mas area que apilados).
BASE_CENTER = (960, 430)
SPELL_RADIUS = 180          # radio donde repartir los totems (0 = todos en el centro)

# --- Barra de tropas (coordenada del icono de cada slot, segun tu ejercito) ---
# Fila de slots en Y=936 (valk calibrado por el usuario; resto con paso ~118px).
#   0 Valkirias | 1(Z) Asedio | 2(Q) Champion | 3(W) Warden | 4(E) Rey | 5(R) Reina | 6(A) Totems
VALKYRIE_SLOT = (421, 936)                                     # valkirias (calibrado)
SIEGE_SLOT    = (539, 936)                                     # maquina de asedio (None = no usar)
SPELL_SLOTS   = [(1129, 936)]                                  # hechizos de totem
SPELL_CHARGES = 11                                             # cantidad de totems (x11)
HERO_SLOTS    = [(657, 936), (775, 936), (893, 936), (1011, 936)]  # Champion, Warden, Rey, Reina

# --- Fin de batalla ---
END_BATTLE_BTN = (216, 822)         # boton "Rendirse" para finalizar (calibrado)
END_BATTLE_CONFIRM = (1130, 700)    # confirmacion ("Okay") -- CALIBRAR si tu cliente la pide
RETURN_HOME_BTN = (975, 935)        # boton "Volver" en la pantalla de resultado

# --- Lectura del % de destruccion ---
# Region (izquierda, arriba, ancho, alto) que captura SOLO los digitos del % (sin el
# texto "Dano total" de arriba ni el signo "%" de la derecha, que ensucian el OCR).
# Validada con frames reales: lee bien 4, 25, 54.
PCT_REGION = (1712, 806, 116, 52)
# Umbral para cortar el ataque.
TARGET_PCT = 50
# Cuanto esperar como maximo (segundos) antes de cortar igual aunque no llegue al 50%.
ATTACK_TIMEOUT = 120

# --- Recursos propios: atacar hasta llenarlos (se leen en tu aldea, arriba-derecha) ---
# Region (izq, arriba, ancho, alto) del numero de cada recurso. Validadas con frame real.
GOLD_REGION   = (1575, 70, 205, 40)
ELIXIR_REGION = (1575, 144, 205, 40)
DARK_REGION   = (1575, 220, 205, 40)
# Objetivos: el bot ataca hasta que los 3 recursos lleguen a estos valores.
GOLD_TARGET   = 31_000_000
ELIXIR_TARGET = 31_000_000
DARK_TARGET   = 470_000        # max actual del deposito (subir a 500_000 si lo mejoras)

# --- Pausas (segundos) entre acciones ---
DEPLOY_PAUSE = 0.15
POLL_INTERVAL = 0.5         # cada cuanto leer el % (mas chico = corta mas cerca del 50%)

# ============================================================================

# Carpeta de este script: usamos archivos temporales relativos (sin rutas absolutas).
_HERE = os.path.dirname(os.path.abspath(__file__))
_PCT_TMP = os.path.join(_HERE, "destruction.png")

# El lector de easyOCR se crea una sola vez (cargar el modelo es lento).
_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        print("Cargando modelo OCR (una sola vez)...")
        _reader = easyocr.Reader(['en'], gpu=True)
    return _reader


def _select(slot):
    """Selecciona un slot de la barra de tropas."""
    pyautogui.click(slot)
    time.sleep(0.1)


def _jitter(x, y, amount=None):
    """Suma una variacion aleatoria a una coordenada (anti-script)."""
    a = RANDOM_JITTER if amount is None else amount
    if a <= 0:
        return x, y
    return x + random.randint(-a, a), y + random.randint(-a, a)


def _click_jit(x, y):
    """Click con jitter y una micro-pausa aleatoria."""
    jx, jy = _jitter(x, y)
    pyautogui.click(jx, jy)
    time.sleep(VALK_TAP_PAUSE + random.uniform(0, RANDOM_PAUSE))


def _ring_points():
    """Extremos de las 4 lineas del anillo verde (para mostrar en modo coords)."""
    pts = []
    for start, end in DEPLOY_LINES:
        pts.extend([start, end])
    return pts


def _valks_per_line():
    """Reparte VALK_TOTAL entre las 4 lineas (ej. 37 -> [10, 9, 9, 9])."""
    n = len(DEPLOY_LINES)
    base, extra = divmod(VALK_TOTAL, n)
    return [base + (1 if i < extra else 0) for i in range(n)]


def deploy_valkyries_circle():
    """Despliega las 37 valkirias por fuerza bruta: las reparte en las 4 lineas y tapea
    una por una, espaciadas a lo largo de cada linea para cubrir la mayor area.
    Aleatoriza el lado de arranque, el espaciado y cada coordenada (anti-script)."""
    _select(VALKYRIE_SLOT)
    reparto = _valks_per_line()
    lineas = list(zip(DEPLOY_LINES, reparto))
    random.shuffle(lineas)              # arrancar desde un lado aleatorio, orden mezclado
    for ((x1, y1), (x2, y2)), cantidad in lineas:
        for k in range(cantidad):
            # espaciado a lo largo de la linea + variacion aleatoria
            t = (k + 0.5 + random.uniform(-0.35, 0.35)) / cantidad
            t = min(max(t, 0.02), 0.98)
            x = int(x1 + (x2 - x1) * t)
            y = int(y1 + (y2 - y1) * t)
            _click_jit(x, y)
    print(f"  {VALK_TOTAL} valkirias desplegadas ({reparto} por linea).", flush=True)


def _spell_points():
    """Puntos donde tirar los totems: repartidos en un circulo chico sobre la base."""
    if SPELL_RADIUS <= 0:
        return [BASE_CENTER] * SPELL_CHARGES
    cx, cy = BASE_CENTER
    pts = []
    for i in range(SPELL_CHARGES):
        a = 2 * math.pi * i / SPELL_CHARGES
        pts.append((int(cx + SPELL_RADIUS * math.cos(a)),
                    int(cy + SPELL_RADIUS * math.sin(a))))
    return pts


def cast_spells():
    """Reparte los totems alrededor del centro de la base (se pueden tirar en zona roja)."""
    for slot in SPELL_SLOTS:
        _select(slot)
        puntos = _spell_points()
        random.shuffle(puntos)
        for x, y in puntos:
            _click_jit(x, y)


def _hero_points():
    """Puntos (vertices del diamante) donde cae cada heroe, uno por vertice."""
    return HERO_DEPLOY_POINTS


def deploy_siege():
    """Suelta la maquina de asedio en un vertice verde (con jitter)."""
    if SIEGE_SLOT is None:
        return
    _select(SIEGE_SLOT)
    _click_jit(*random.choice(_hero_points()))


def deploy_heroes(activate_ability=True):
    """Despliega cada heroe en un vertice distinto (aleatorio) y activa su habilidad."""
    pts = list(_hero_points())
    random.shuffle(pts)                 # cada heroe a un vertice aleatorio
    for i, slot in enumerate(HERO_SLOTS):
        _select(slot)
        _click_jit(*pts[i % len(pts)])
        time.sleep(0.3 + random.uniform(0, RANDOM_PAUSE))
    if activate_ability:
        # Con el heroe ya en el campo, tocar su slot de nuevo activa la habilidad.
        for slot in HERO_SLOTS:
            pyautogui.click(slot)
            time.sleep(0.2)


def _ocr_number(region, threshold=None):
    """Captura una region, la agranda 3x y lee un entero con OCR. None si no hay digitos.
    Con threshold binariza (mejor para el % blanco); sin threshold lee mejor numeros grandes."""
    screenshot(region, _PCT_TMP)
    img = cv2.imread(_PCT_TMP)
    if img is None:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    if threshold is not None:
        gray = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)[1]
    result = _get_reader().readtext(gray, detail=0, paragraph=True, allowlist='0123456789')
    digits = re.sub(r'[^0-9]', '', ''.join(result))
    return int(digits) if digits else None


def read_destruction_pct():
    """Lee el % de destruccion de la pantalla con OCR. Devuelve int (0-100) o None."""
    val = _ocr_number(PCT_REGION, threshold=160)
    return val if (val is not None and 0 <= val <= 100) else None


def read_resources():
    """Lee (oro, elixir, oscuro) de tu aldea. Cada uno puede ser None si no se pudo leer."""
    return (_ocr_number(GOLD_REGION),
            _ocr_number(ELIXIR_REGION),
            _ocr_number(DARK_REGION))


def resources_full():
    """True si los 3 recursos llegaron a su objetivo (debe estar en la aldea propia)."""
    g, e, d = read_resources()
    print(f"  Recursos -> oro:{g}  elixir:{e}  oscuro:{d}", flush=True)
    return (g is not None and g >= GOLD_TARGET and
            e is not None and e >= ELIXIR_TARGET and
            d is not None and d >= DARK_TARGET)


def wait_until_pct(target=TARGET_PCT, timeout=ATTACK_TIMEOUT):
    """Sondea el % hasta llegar a 'target' o agotar 'timeout'. Devuelve el maximo % leido.

    La destruccion solo SUBE, asi que usamos el maximo acumulado: una lectura mas baja
    que el maximo es un error de OCR y se ignora.
    """
    start = time.time()
    best = 0
    while time.time() - start < timeout:
        pct = read_destruction_pct()
        if pct is not None:
            if pct > best:
                best = pct
            print(f"Destruccion leida: {pct}%  (max {best}%)")
            if best >= target:
                return best
        time.sleep(POLL_INTERVAL)
    print(f"Timeout: corto con {best}% (no llego a {target}%).")
    return best


def end_battle():
    """Termina la batalla y vuelve a la aldea."""
    pyautogui.click(END_BATTLE_BTN)
    time.sleep(1)
    pyautogui.click(END_BATTLE_CONFIRM)
    time.sleep(3)
    pyautogui.click(RETURN_HOME_BTN)
    time.sleep(2)


def valkyrie_attack(activate_ability=True):
    """Ejecuta el ataque completo sobre la base ya cargada en pantalla."""
    print("Desplegando valkirias...")
    deploy_valkyries_circle()

    print("Lanzando hechizos de totem...")
    cast_spells()

    print("Desplegando maquina de asedio...")
    deploy_siege()

    print("Desplegando heroes...")
    deploy_heroes(activate_ability=activate_ability)

    print(f"Esperando llegar al {TARGET_PCT}%...")
    pct = wait_until_pct()

    print(f"Terminando batalla a {pct}%.")
    end_battle()
    return pct


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "full"

    if mode == "ocr":
        # Lee el % UNA vez y lo imprime. No hace clicks -> seguro.
        # Util para calibrar PCT_REGION: entra a una batalla y corre esto.
        print(f"Leyendo % en la region {PCT_REGION} ...", flush=True)
        print(f"Lei: {read_destruction_pct()}", flush=True)

    elif mode == "res":
        # Lee TUS recursos una vez (parate en tu aldea). No hace clicks -> seguro.
        g, e, d = read_resources()
        print(f"Oro:    {g}  (objetivo {GOLD_TARGET})", flush=True)
        print(f"Elixir: {e}  (objetivo {ELIXIR_TARGET})", flush=True)
        print(f"Oscuro: {d}  (objetivo {DARK_TARGET})", flush=True)
        print(f"Llenos?: {resources_full()}", flush=True)

    elif mode == "coords":
        # Muestra DONDE clickearia, sin clickear -> seguro.
        print("Lineas del anillo de valkirias (inicio -> fin):", flush=True)
        for start, end in DEPLOY_LINES:
            print(f"  {start} -> {end}", flush=True)
        print(f"Heroes (uno por vertice): {_hero_points()}", flush=True)
        print(f"Totems repartidos en: {_spell_points()}", flush=True)
        print(f"Valkiria: {VALKYRIE_SLOT}  Asedio: {SIEGE_SLOT}", flush=True)
        print(f"Hechizos: {SPELL_SLOTS}  Heroes: {HERO_SLOTS}", flush=True)

    elif mode == "deploy":
        # Solo despliega (sin leer % ni terminar). Entra a una base primero.
        print("Desplegando en 4 segundos (pone una base en pantalla)...", flush=True)
        time.sleep(4)
        deploy_valkyries_circle()
        cast_spells()
        deploy_siege()
        deploy_heroes()
        print("Despliegue terminado.", flush=True)

    else:
        # Ataque completo. Precarga el OCR antes de la cuenta regresiva.
        print("Cargando OCR (la 1ra vez descarga el modelo, ~64MB)...", flush=True)
        _get_reader()
        print("Listo. Ataque completo en 4 segundos (pone una base en pantalla)...", flush=True)
        time.sleep(4)
        valkyrie_attack()
