import os
import sys
from pathlib import Path
from PIL import Image
from rectpack import newPacker

# --- KONFIGURACE ---

# Odkud brát PNG obrázky bez pozadí
VSTUPNI_SLOZKA = Path(r'K:\tomik_samolepky\bez_pozadi')

# Kam uložit finální vícestránkové PDF
VYSTUPNI_PDF = Path(r'K:\tomik_samolepky\samolepky_k_tisku_1200dpi_NORMALIZED.pdf')

# Rozlišení tisku
PRINT_DPI = 1200

# === NASTAVENÍ VELIKOSTI SAMOLEPEK ===
# Velikost nejdelší strany KAŽDÉ samolepky v centimetrech.
# Všechny samolepky budou mít svou nejdelší stranu takto velkou.
STICKER_SIZE_CM = 4.5
# Přepočet na pixely
NORMALIZED_SIDE_PX = int((STICKER_SIZE_CM / 2.54) * PRINT_DPI)

# Mezera mezi samolepkami v cm (přepočte se na pixely)
SPACING_CM = 0.15
SPACING_PX = int((SPACING_CM / 2.54) * PRINT_DPI) # Bude cca 70px

# Rozměry A4 v pixelech (už není potřeba je nastavovat ručně)
A4_WIDTH_MM = 210
A4_HEIGHT_MM = 297
A4_WIDTH_PX = int((A4_WIDTH_MM / 25.4) * PRINT_DPI)  # 9921 px
A4_HEIGHT_PX = int((A4_HEIGHT_MM / 25.4) * PRINT_DPI) # 14031 px

# -----------------------------------------------------------------

def create_sticker_pdf():
    print(f"--- Spuštěno finální zpracování (Ořez + Normalizace + Skládání) ---")
    print(f"Cílové rozlišení: {PRINT_DPI} DPI ({A4_WIDTH_PX}x{A4_HEIGHT_PX} px).")
    print(f"Normalizovaná velikost (nejdelší strana): {STICKER_SIZE_CM} cm ({NORMALIZED_SIDE_PX} px)")
    print(f"Mezera mezi samolepkami: {SPACING_CM} cm ({SPACING_PX} px)")

    # --- Krok 1: Ořezat, normalizovat a připravit obdélníky ---
    print("Načítám, ořezávám a normalizuji obrázky...")
    rectangles_to_pack = [] # Seznam (šířka, výška, id)
    image_map = {}          # Slovník {id: (PIL_Image, cílová_šířka, cílová_výška)}
    
    image_files = list(VSTUPNI_SLOZKA.glob('*.png'))
    if not image_files:
        print(f"CHYBA: Ve složce '{VSTUPNI_SLOZKA}' nebyly nalezeny žádné .png soubory.")
        return

    img_id_counter = 0
    for file_path in image_files:
        try:
            with Image.open(file_path) as img:
                
                # --- Logika ořezu ---
                bbox = img.getbbox()
                if not bbox:
                    print(f"Přeskočeno: {file_path.name} (je prázdný)")
                    continue
                
                cropped_img = img.crop(bbox)
                
                # --- Logika normalizace velikosti ---
                w, h = cropped_img.size
                if w > h:
                    # Širší než vyšší
                    new_w = NORMALIZED_SIDE_PX
                    new_h = int(new_w * (h / w)) # Zachovat poměr stran
                else:
                    # Vyšší než širší (nebo čtverec)
                    new_h = NORMALIZED_SIDE_PX
                    new_w = int(new_h * (w / h)) # Zachovat poměr stran

                # --- Logika přípravy pro balení ---
                # Uložíme si ořezaný obrázek A JEHO FINÁLNÍ NORMALIZOVANÉ ROZMĚRY
                image_map[img_id_counter] = (cropped_img.copy(), new_w, new_h)
                
                # Packerovi dáme rozměr VČETNĚ mezery
                rect_w = new_w + SPACING_PX
                rect_h = new_h + SPACING_PX
                
                if rect_w > A4_WIDTH_PX or rect_h > A4_HEIGHT_PX:
                    print(f"VAROVÁNÍ: Obrázek {file_path.name} je i po normalizaci ({new_w}x{new_h}px) "
                          f"stále větší než stránka A4. To by se nemělo stávat.")
                    continue

                rectangles_to_pack.append((rect_w, rect_h, img_id_counter))
                img_id_counter += 1
                
        except Exception as e:
            print(f"CHYBA při načítání/ořezu souboru {file_path.name}: {e}")

    if not image_map:
        print("Nebyly načteny žádné platné obrázky k zabalení.")
        return
        
    print(f"Nalezeno a normalizováno {len(image_map)} obrázků k zabalení.")

    # --- Krok 2: Spustit balicí algoritmus ---
    print("Optimalizuji rozložení na stránky (může to chvíli trvat)...")
    
    # Vypneme otáčení, abychom předešli deformacím.
    # Je to méně efektivní pro místo, ale 100% spolehlivé.
    packer = newPacker(rotation=False) 
    
    for r in rectangles_to_pack:
        packer.add_rect(r[0], r[1], rid=r[2])

    for i in range(len(rectangles_to_pack)): 
        packer.add_bin(A4_WIDTH_PX, A4_HEIGHT_PX)

    packer.pack()

    # --- Krok 3: Vygenerovat PDF stránky ---
    all_pages = list(packer)
    print(f"Optimální rozložení bude vyžadovat {len(all_pages)} stránek A4.")
    
    pdf_pages = []
    
    for i, page in enumerate(all_pages):
        print(f"Generuji PDF stranu {i+1} / {len(all_pages)}...")
        page_image = Image.new('RGBA', (A4_WIDTH_PX, A4_HEIGHT_PX), 'WHITE')
        
        for rect in page:
            rid = rect.rid
            
            # Získáme obrázek A JEHO SPRÁVNÉ NORMALIZOVANÉ ROZMĚRY
            original_img, target_w, target_h = image_map[rid]
            
            # Zmenšíme obrázek na cílovou velikost
            sticker_img = original_img.resize((target_w, target_h), Image.LANCZOS)
            
            # === OPRAVA PŘEKRÝVÁNÍ ===
            # Vložíme obrázek doprostřed jeho přiděleného bloku
            # (rect.x, rect.y) je levý horní roh bloku, který je o SPACING_PX větší
            paste_x = rect.x + (SPACING_PX // 2)
            paste_y = rect.y + (SPACING_PX // 2)
            
            # Vlepíme ho na stránku
            page_image.paste(sticker_img, (paste_x, paste_y), sticker_img)
            
        pdf_pages.append(page_image.convert('RGB')) 
    
    # --- Krok 4: Uložit finální PDF ---
    if not pdf_pages:
        print("Nebyly vygenerovány žádné stránky.")
    else:
        print(f"Ukládám finální PDF soubor: {VYSTUPNI_PDF}")
        pdf_pages[0].save(
            VYSTUPNI_PDF,
            "PDF",
            resolution=PRINT_DPI,
            save_all=True,
            append_images=pdf_pages[1:]
        )
        print(f"--- HOTOVO! ---")
        print(f"Všechny samolepky byly uloženy do souboru: {VYSTUPNI_PDF}")

# Spuštění hlavní funkce
if __name__ == "__main__":
    create_sticker_pdf()