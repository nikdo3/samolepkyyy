import os
import sys
import site
import io
import warnings
import numpy as np
import torch
import requests
from tqdm import tqdm
from pathlib import Path
from PIL import Image, ImageChops
from rembg import remove, new_session
from segment_anything_hq import SamPredictor, sam_model_registry

# --- OPRAVA cuDNN (zůstává nutná) ---
try:
    venv_path = sys.prefix
    cudnn_bin_path = os.path.join(venv_path, 'Lib', 'site-packages', 'nvidia', 'cudnn', 'bin')
    if not os.path.exists(cudnn_bin_path):
        user_site_packages = site.getusersitepackages()
        cudnn_bin_path = os.path.join(user_site_packages, 'nvidia', 'cudnn', 'bin')
    if os.path.exists(cudnn_bin_path):
        os.environ['PATH'] = cudnn_bin_path + os.pathsep + os.environ['PATH']
        print(f"Přidána cesta k cuDNN: {cudnn_bin_path}")
    else:
        print("VAROVÁNÍ: Cesta k cuDNN nenalezena.")
except Exception as e:
    print(f"CHYBA při nastavování cesty pro cuDNN: {e}")

# --- Vypnutí omezení a varování ---
Image.MAX_IMAGE_PIXELS = None
warnings.filterwarnings("ignore", category=UserWarning, module='torch')

# --- KONFIGURACE ---
VSTUPNI_SLOZKA = Path(r'K:\tomik_samolepky\upskejld\upscayl_png_digital-art-4x_5x')
VYSTUPNI_SLOZKA = Path(r'K:\tomik_samolepky\bez_pozadi_SAM_HQ')

# Model pro "prompt" (rychlý, volnější)
PROMPTER_MODEL = "isnet-general-use" 

# Model pro "segmentaci" (pomalý, přesný)
SAM_MODEL_TYPE = "vit_h" # vit_l (Large) nebo vit_h (Huge)
SAM_CHECKPOINT_NAME = "sam_hq_vit_h.pth"
SAM_CHECKPOINT_URL = "https://huggingface.co/lkeab/hq-sam/resolve/main/sam_hq_vit_h.pth"

# -----------------------------------------------------------------

def stahni_model(url, nazev_souboru):
    """Stáhne model, pokud neexistuje, s ukazatelem průběhu."""
    model_path = Path(nazev_souboru)
    if model_path.exists():
        print(f"Model {nazev_souboru} již existuje.")
        return model_path

    print(f"Stahuji model {nazev_souboru} z {url} (může to trvat)...")
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024
        
        with open(model_path, 'wb') as f, tqdm(
            desc=nazev_souboru,
            total=total_size,
            unit='iB',
            unit_scale=True,
            unit_divisor=1024,
        ) as bar:
            for data in response.iter_content(block_size):
                bar.update(len(data))
                f.write(data)
                
        if total_size != 0 and bar.n != total_size:
            raise Exception("Chyba při stahování, velikost nesouhlasí.")
            
        print(f"Model {nazev_souboru} úspěšně stažen.")
        return model_path
        
    except Exception as e:
        print(f"CHYBA při stahování modelu: {e}")
        if model_path.exists():
            os.remove(model_path) # Smaž poškozený soubor
        sys.exit(1)


def nacti_obrazek_pil_do_rgba(cesta):
    """Načte obrázek pomocí PIL a zajistí, že je v RGBA."""
    img = Image.open(cesta).convert("RGBA")
    return img

def main():
    # --- Krok 1: Kontrola a příprava modelů ---
    print("Kontroluji a připravuji modely...")
    
    # Stáhneme SAM model
    sam_model_path = stahni_model(SAM_CHECKPOINT_URL, SAM_CHECKPOINT_NAME)
    
    # Zjistíme, jestli máme GPU
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Detekováno zařízení: {device.upper()}")
    if device == "cpu":
        print("VAROVÁNÍ: Běh na CPU bude extrémně pomalý!")

    # Načteme SAM
    print(f"Načítám SAM ({SAM_MODEL_TYPE}) do paměti... (zabere hodně VRAM)")
    sam = sam_model_registry[SAM_MODEL_TYPE](checkpoint=sam_model_path)
    sam.to(device=device)
    predictor = SamPredictor(sam)
    print("SAM model připraven.")

    # Načteme Rembg (Prompter)
    print(f"Načítám Rembg ({PROMPTER_MODEL})...")
    session_prompter = new_session(PROMPTER_MODEL)
    print("Rembg model připraven.")

    os.makedirs(VYSTUPNI_SLOZKA, exist_ok=True)
    
    # --- Krok 2: Zpracování složky ---
    print(f"--- Spuštěno zpracování (Prompter: Rembg, Segmenter: SAM-HQ) ---")
    
    image_files = list(VSTUPNI_SLOZKA.glob('*.png')) + \
                  list(VSTUPNI_SLOZKA.glob('*.jpg')) + \
                  list(VSTUPNI_SLOZKA.glob('*.jpeg'))
                  
    if not image_files:
        print(f"Nenalezeny žádné obrázky ve složce {VSTUPNI_SLOZKA}")
        return

    for img_path in image_files:
        print(f"\n--- Zpracovávám: {img_path.name} ---")
        try:
            # --- Fáze 1: Prompter (Rembg) ---
            print("  Fáze 1: Vytvářím hrubý 'prompt' pomocí Rembg...")
            with open(img_path, 'rb') as f:
                input_data = f.read()
            
            # Získáme výstup z Rembg
            rembg_output_data = remove(input_data, session=session_prompter, alpha_matting=False)
            
            # Získáme masku a z ní Bounding Box
            rembg_mask = Image.open(io.BytesIO(rembg_output_data)).getchannel("A")
            bbox = rembg_mask.getbbox()
            
            if not bbox:
                print("  CHYBA: Rembg nenašel žádný objekt (obrázek je prázdný?). Přeskakuji.")
                continue
                
            print(f"  Rembg našel objekt v boxu: {bbox}")

            # --- Fáze 2: Segmenter (SAM-HQ) ---
            print("  Fáze 2: Spouštím SAM-HQ pro přesnou segmentaci...")
            
            # SAM vyžaduje obrázek jako NumPy pole (H, W, C) v RGB
            # Musíme načíst originál
            original_pil = Image.open(img_path).convert("RGB")
            original_np = np.array(original_pil)

            # Nastavíme obrázek do SAM prediktoru
            predictor.set_image(original_np)
            
            # Převedeme PIL BBox na NumPy BBox
            input_box = np.array(bbox)
            
            # Spustíme SAM predikci!
            masks, scores, logits = predictor.predict(
                box=input_box,
                multimask_output=False, # Chceme jen jednu, nejlepší masku
                hq_input=input_box # Použijeme HQ vylepšení
            )
            
            # Výstup 'masks' je [1, H, W] NumPy pole (True/False)
            # Převedeme ho na PIL masku (0-255)
            final_mask_pil = Image.fromarray(masks[0] * 255)

            # --- Fáze 3: Uložení ---
            print("  Fáze 3: Aplikuji finální masku a ukládám...")
            
            # Načteme originál znovu, tentokrát i s alfou (pokud ji má)
            final_image = nacti_obrazek_pil_do_rgba(img_path)
            
            # Vložíme naši novou, super přesnou masku
            final_image.putalpha(final_mask_pil)
            
            # Ořežeme finální obrázek (teď už s přesnou maskou)
            final_bbox = final_image.getbbox()
            if final_bbox:
                final_image = final_image.crop(final_bbox)

            # Uložení
            output_path = VYSTUPNI_SLOZKA / (img_path.stem + "_SAM_HQ.png")
            final_image.save(output_path)
            print(f"  Hotovo -> {output_path.name}")

        except Exception as e:
            print(f"  *** SELHALO ZPRACOVÁNÍ pro {img_path.name}: {e} ***")

    print("\n--- Všechny úkoly dokončeny. ---")

if __name__ == "__main__":
    main()