import os
import sys
import site

# --- ZAČÁTEK OPRAVY PRO cuDNN ---
# Tohle najde cestu k 'site-packages' uvnitř tvého .venv-gpu
try:
    # Standardní cesta ve venv
    venv_path = sys.prefix
    cudnn_bin_path = os.path.join(venv_path, 'Lib', 'site-packages', 'nvidia', 'cudnn', 'bin')

    if not os.path.exists(cudnn_bin_path):
        # Záložní cesta (pokud by to bylo nainstalováno pro uživatele)
        user_site_packages = site.getusersitepackages()
        cudnn_bin_path = os.path.join(user_site_packages, 'nvidia', 'cudnn', 'bin')

    if os.path.exists(cudnn_bin_path):
        print(f"Nalezena cesta k cuDNN: {cudnn_bin_path}")
        # Přidání cesty k DLL knihovnám do systémové proměnné PATH
        os.environ['PATH'] = cudnn_bin_path + os.pathsep + os.environ['PATH']
        print("Cesta k cuDNN byla přidána do systémového PATH.")
    else:
        print("VAROVÁNÍ: Cesta k 'nvidia/cudnn/bin' nebyla nalezena. GPU nemusí fungovat.")
        
except Exception as e:
    print(f"CHYBA při nastavování cesty pro cuDNN: {e}")
# --- KONEC OPRAVY PRO cuDNN ---


# Teď teprve importujeme zbytek, včetně rembg
from pathlib import Path
from rembg import remove, new_session
from PIL import Image

# --- KONFIGURACE ---
Image.MAX_IMAGE_PIXELS = None

# Zvolený model pro odstranění pozadí.
POUZITY_MODEL = "birefnet-massive"

# Cesty ke složkám (UPRAV PODLE SEBE)
VSTUPNI_SLOZKA = Path(r'K:\tomik_samolepky\upskejld\upscayl_png_digital-art-4x_5x')
VYSTUPNI_SLOZKA = Path(r'K:\tomik_samolepky\bez_pozadi')

# Jaké typy souborů má skript zpracovávat?
TYPY_SOUBORU = ['*.jpg', '*.png', '*.jpeg']

# Parametry pro jemné doladění (alpha matting)
POUZIT_ALPHA_MATTING = False # Změnil jsi na True, tak to nechávám
ALPHA_MATTING_FOREGROUND_THRESHOLD = 240
ALPHA_MATTING_BACKGROUND_THRESHOLD = 10
ALPHA_MATTING_ERODE_SIZE = 10

# -----------------------------------------------------------------
# --- HLAVNÍ LOGIKA SKRIPTU ---

def process_image_for_sticker(input_path: Path, output_folder: Path, session,
                              use_alpha_matting: bool,
                              af: int, ab: int, ae: int):
    # Vytvoření výstupního názvu souboru s příponou .png
    output_filename = input_path.stem + "_sticker.png"
    output_path = output_folder / output_filename

    print(f"Zpracovávám '{input_path.name}' s modelem '{session.model_name}'...")

    try:
        with open(input_path, 'rb') as i:
            input_data = i.read()
            # Odstranění pozadí
            output_data = remove(
                input_data,
                session=session,
                alpha_matting=use_alpha_matting,
                af=af,
                ab=ab,
                ae=ae
            )
            
            # Uložení výsledku
            with open(output_path, 'wb') as o:
                o.write(output_data)
            
            print(f" -> Uloženo jako '{output_filename}'")

    except Exception as e:
        print(f"CHYBA při zpracování '{input_path.name}': {e}")

if __name__ == "__main__":
    # Inicializace session s vybraným modelem
    session = new_session(POUZITY_MODEL)

    # Vytvoření výstupní složky, pokud neexistuje
    os.makedirs(VYSTUPNI_SLOZKA, exist_ok=True)

    print(f"--- Spuštěno zpracování samolepek ---")
    print(f"Vstupní složka: {VSTUPNI_SLOZKA}")
    print(f"Výstupní složka: {VYSTUPNI_SLOZKA}")
    print(f"Použitý model: {POUZITY_MODEL}")
    print(f"Použít Alpha Matting: {POUZIT_ALPHA_MATTING}")

    processed_count = 0
    for file_type in TYPY_SOUBORU:
        for input_file in VSTUPNI_SLOZKA.glob(file_type):
            process_image_for_sticker(
                input_file,
                VYSTUPNI_SLOZKA,
                session,
                POUZIT_ALPHA_MATTING,
                ALPHA_MATTING_FOREGROUND_THRESHOLD,
                ALPHA_MATTING_BACKGROUND_THRESHOLD,
                ALPHA_MATTING_ERODE_SIZE
            )
            processed_count += 1
    
    if processed_count == 0:
        print(f"Nenalezeny žádné soubory typu {', '.join(TYPY_SOUBORU)} ve složce {VSTUPNI_SLOZKA}. Zkontrolujte cesty a přípony.")

    print(f"--- Dokončeno. Zpracováno {processed_count} obrázků. ---")