"""
Farmea atacando con valkirias: por cada base, despliega valkirias en circulo,
lanza hechizos, suelta heroes (con habilidad) y corta al llegar al 50%.

Uso:
    python coc_base_finder.py            # ataca bases sin parar (Ctrl-C para cortar)
    python coc_base_finder.py --bases 10 # ataca 10 bases y termina

Antes de usarlo, calibra las coordenadas en el bloque CONFIG de attack.py
(usando  python click.py  para leer los X/Y de tu pantalla).
"""

import time
from argparse import ArgumentParser

import pyautogui

from utils import open_window, wait_for_base
from attack import (valkyrie_attack, resources_full, set_profile, PROFILES,
                    setup_pause, wait_if_paused)

parser = ArgumentParser(description='Farmea atacando con valkirias hasta llenar tus recursos.')
parser.add_argument('--bases', type=int, default=0,
                    help='Tope de bases a atacar (0 = sin tope; igual para al llenar recursos).')
parser.add_argument('--profile', '--perfil', default='normal', choices=list(PROFILES),
                    help='Perfil de barra de tropas (cambia segun haya evento activo).')
parser.add_argument('--no-ability', action='store_true',
                    help='No activar las habilidades de los heroes.')
parser.add_argument('--ignore-resources', action='store_true',
                    help='No chequear recursos; atacar hasta el tope --bases (o Ctrl-C).')
args = parser.parse_args()

set_profile(args.profile)
setup_pause()
open_window("Clash of Clans")
print("Iniciando farmeo con valkirias (F8 = pausa/reanuda, Ctrl-C = cortar)...")

attacked = 0
try:
    while args.bases == 0 or attacked < args.bases:
        wait_if_paused()
        # Estamos en la aldea: chequear si ya estan llenos los recursos.
        if not args.ignore_resources:
            print("\nChequeando recursos...")
            if resources_full():
                print("Recursos LLENOS. Termino el farmeo.")
                break

        print(f"=== Base #{attacked + 1} ===")
        pyautogui.click(x=221, y=936)    # 1) Atacar (aldea)
        time.sleep(1.5)
        pyautogui.click(x=351, y=731)    # 2) Buscar batalla
        time.sleep(1.5)
        pyautogui.click(x=1612, y=880)   # 3) Atacar (menu de preparacion) -> matchmaking
        wait_for_base()                  # espera que se despejen las nubes
        valkyrie_attack(activate_ability=not args.no_ability)
        attacked += 1
        print(f"Base #{attacked} terminada.")
        time.sleep(2)
except KeyboardInterrupt:
    print("\nCortado por el usuario.")

print(f"\nListo. Ataque {attacked} base(s).")
