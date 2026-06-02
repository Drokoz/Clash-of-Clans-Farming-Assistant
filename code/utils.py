import easyocr
import cv2
import pygetwindow
import pyautogui
from PIL import Image
from ahk import AHK
import re
import os
import sys
import shutil
import time
import numpy as np

# Carpeta de este script: guardamos los screenshots temporales aca,
# asi no hace falta hardcodear rutas absolutas por maquina.
_HERE = os.path.dirname(os.path.abspath(__file__))
CLOUDS_PNG = os.path.join(_HERE, "clouds.png")
VILLAGE_PNG = os.path.join(_HERE, "village.png")
RESOURCES_PNG = os.path.join(_HERE, "resources.png")

def find_window(name):
    window = pygetwindow.getWindowsWithTitle(name)[0]
    left, top = window.topleft
    right, bottom = window.bottomright

    if window:
        return [left, top, right, bottom]
    else:
        return -1
    
def _find_ahk_executable():
    # ahk[binary] instala AutoHotkey.exe en la carpeta Scripts del venv,
    # que solo esta en el PATH si el venv esta activado. Lo buscamos
    # explicitamente al lado del interprete para no depender de eso.
    exe = shutil.which("AutoHotkey.exe")
    if exe:
        return exe
    candidate = os.path.join(os.path.dirname(sys.executable), "AutoHotkey.exe")
    if os.path.exists(candidate):
        return candidate
    return None

def open_window(name):
    exe = _find_ahk_executable()
    ahk = AHK(executable_path=exe) if exe else AHK()
    win = ahk.win_get(title=name)

    if win:
        win.maximize()
        win.always_on_top = 'On'
    else:
        return -1
    
def screenshot(window_dimensions, file_path):
    img = pyautogui.screenshot(file_path, window_dimensions)
    return img
    
def preprocess_image(file_path):
    image = cv2.imread(file_path)
    original = image.copy()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    black_white = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)[1]

    images = {
        "original": original,
        "gray": gray,
        "black_white": black_white
    }

    return images

def read_values(image):
    reader = easyocr.Reader(['en'], gpu=True)

    result = reader.readtext(image, detail=0, paragraph=True)

    return result

def text_to_numbers(text):
    numbers = []

    for number in text:
        number = re.sub(r'[^0-9]', '', number)
        numbers.append(number)

    int_numbers = [int(number) for number in numbers]

    return int_numbers

def find_button(reference_image_path, village_image_path):
    next_button_img = cv2.imread(reference_image_path)
    village_img = cv2.imread(village_image_path)

    matches = cv2.matchTemplate(village_img, next_button_img, cv2.TM_CCOEFF_NORMED)
    min, max, min_loc, max_loc = cv2.minMaxLoc(matches)

def wait_for_base():
    """Espera a que se despejen las nubes del matchmaking y la base quede cargada.

    Devuelve las dimensiones de la ventana del juego.
    """
    dimensions = find_window("Clash of Clans")
    open_window("Clash of Clans")

    average_color = 151
    while (average_color > 150):
        print("Waiting for clouds...")
        clouds = screenshot(dimensions, CLOUDS_PNG)
        average_color_row = np.average(np.array(clouds), axis=0)
        average_color = np.average(average_color_row)
        # print(average_color)

    return dimensions


def find_base_with(gold, elixir, dark_elixir=0):
    dimensions = wait_for_base()

    print("Analyzing base...")
    screenshot(dimensions, VILLAGE_PNG)
    new_dimensions = [dimensions[0] + 72, dimensions[1] + 160, dimensions[0] + 170, dimensions[1] + 150]
    screenshot(new_dimensions, RESOURCES_PNG)

    images = preprocess_image(RESOURCES_PNG)
    string_values = read_values(images["black_white"])
    numbers = text_to_numbers(string_values)

    if numbers[0] >= gold and numbers[1] >= elixir and numbers[2] >= dark_elixir:
        return True
    else:
        return False
