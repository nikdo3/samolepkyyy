import os
import sys
import site
import io 
from pathlib import Path
from rembg import remove, new_session
from PIL import Image, ImageChops 

# --- ZAČÁTEK OPRAVY PRO cuDNN ---
# (Tohle zůstává stejné)
try:
    venv_path = sys.prefix
    cudnn_bin_path = os.path.join(venv_path, 'Lib', 'site-packages', 'nvidia', 'cudnn', 'bin')
    if not os.path.exists(cudnn_bin_path):
        user_site_packages = site.getusersitepackages()
        cudnn_bin_path = os.path.join(user_site_packages, 'nvidia', 'cudnn', 'bin')
    if os.path.exists(cudnn_bin_path):
        print(f"Nalezena cesta k cuDNN: {cudnn_bin_path}")
        os.environ['PATH'] = cudnn_bin_path + os.pathsep + os.environ['PATH']
        print("Cesta k cuDNN byla přidána do systémového PATH.")
    else:
        print("VAROVÁNÍ: Cesta k 'nvidia/cudnn/bin' nebyla nalezena. GPU nemusí fungovat.")
except Exception as e:
    print(f"CHYBA při nastavování cesty pro cuDNN: {e}")
# --- KONEC OPRAVY PRO cuDNN ---


# <<< ODSTRANĚNÍ OMEZENÍ PRO VELKÉ OBRÁZKY >>>
Image.MAX_IMAGE_PIXELS = None 

# --- KONFIGURACE ---

# <<< DVA MODELY >>>
MODEL_A = "birefnet-massive" # Agresivní a přesný
MODEL_B = "isnet-general-use" # Volnější

# Cesty ke složkám (podle tvého logu)
VSTUPNI_SLOZKA = Path(r'K:\tomik_samolepky\upskejld\upscayl_png_digital-art-4x_5x')
VYSTUPNI_SLOZKA = Path(r'K:\tomik_samolepky\bez_pozadi')

# Jaké typy souborů má skript zpracovávat?
TYPY_SOUBORU = ['*.jpg', '*.png', '*.jpeg']

# -----------------------------------------------------------------
# --- NOVÁ HLAVNÍ LOGIKA SKRIPTU ---

def process_image_combined(input_path: Path, output_folder: Path, session_a, session_b):
    """
    Zpracuje jeden obrázek pomocí DVOU modelů a zkombinuje jejich masky.
    """
    output_filename = input_path.stem + "_sticker_combined.png"
    output_path = output_folder / output_filename

    print(f"Zpracovávám '{input_path.name}' (Kombinace: {session_a.model_name} + {session_b.model_name})...")

    try:
        # Načteme originální soubor jen jednou
        with open(input_path, 'rb') as f:
            input_data = f.read()

        # --- Model A (Agresivní) ---
        output_data_A = remove(input_data, session=session_a, alpha_matting=False)
        img_A = Image.open(io.BytesIO(output_data_A))
        mask_A = img_A.split()[-1] # Získáme jen Alfa kanál (masku)

        # --- Model B (Volnější) ---
        output_data_B = remove(input_data, session=session_b, alpha_matting=False)
        img_B = Image.open(io.BytesIO(output_data_B))
        mask_B = img_B.split()[-1] # Získáme jen Alfa kanál (masku)

        # --- Kombinace masek ---
        # <<< OPRAVA ZDE >>>
        # ImageChops.lighter vezme světlejší pixel z obou masek.
        # Tzn. pokud A řekne "pozadí" (0) a B řekne "popředí" (255), výsledek je 255.
        # Přesně to chceme: "ponech, pokud si ALESPOŇ JEDEN model myslí, že to je popředí".
        final_mask = ImageChops.lighter(mask_A, mask_B)

        # --- Aplikace finální masky na originál ---
        original_img = Image.open(io.BytesIO(input_data)).convert("RGBA")
        original_img.putalpha(final_mask)
        
        # Uložení výsledku
        original_img.save(output_path)
        
        print(f" -> Uloženo jako '{output_filename}'")

    except Exception as e:
        print(f"CHYBA při zpracování '{input_path.name}': {e}")

# --- Spouštěcí část skriptu ---
if __name__ == "__main__":
    
    print("Inicializuji oba modely (může to chvíli trvat)...")
    # Inicializace session pro oba modely
    session_a = new_session(MODEL_A)
    session_b = new_session(MODEL_B)
    print("Modely připraveny.")

    # Vytvoření výstupní složky, pokud neexistuje
    os.makedirs(VYSTUPNI_SLOZKA, exist_ok=True)

    print(f"--- Spuštěno kombinované zpracování samolepek ---")
    print(f"Vstupní složka: {VSTUPNI_SLOZKA}")
    print(f"Výstupní složka: {VYSTUPNI_SLOZKA}")
    print(f"Použité modely: {MODEL_A} (přesný) + {MODEL_B} (volnější)")

    processed_count = 0
    for file_type in TYPY_SOUBORU:
        for input_file in VSTUPNI_SLOZKA.glob(file_type):
            process_image_combined(
                input_file,
                VYSTUPNI_SLOZKA,
                session_a,
                session_b
            )
            processed_count += 1
    
    if processed_count == 0:
        print(f"Nenalezeny žádné soubory typu {', '.join(TYPY_SOUBORU)} ve složce {VSTUPNI_SLOZKA}. Zkontrolujte cesty a přípony.")

    print(f"--- Dokončeno. Zpracováno {processed_count} obrázků. ---")