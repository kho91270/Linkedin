import os
import subprocess
import sys

# --- OPTION A : Découpe via PyPDF2 (si tu exportes manuellement 2 PDFs complets) ---
# Tu exportes LOT1 et LOT2 en UN SEUL PDF chacun (pas besoin de splitter à la main)
# Le script se charge de découper par plages de slides

try:
    from PyPDF2 import PdfReader, PdfWriter
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyPDF2"])
    from PyPDF2 import PdfReader, PdfWriter


# ============================================================
# CONFIGURATION : Mapping des slides par carrousel
# ============================================================

# LOT 1 : pages dans le PDF (index commence à 0)
LOT1_MAPPING = {
    "carousel_jour_17.pdf": (0, 5),     # Slides 1-6 → Kraljic
    "carousel_jour_21.pdf": (6, 10),    # Slides 7-11 → Value Engineering
    "carousel_jour_14.pdf": (11, 16),   # Slides 12-17 → IA Générative
    "carousel_jour_64.pdf": (17, 17),   # Slide 18 → Tail Spend Trap (infographie)
    "carousel_jour_22.pdf": (18, 23),   # Slides 19-24 → KPIs vs OKRs
}

# LOT 2 : pages dans le PDF (index commence à 0)
LOT2_MAPPING = {
    "carousel_jour_46.pdf": (0, 0),     # Slide 1 → Nearshoring (infographie)
    "carousel_jour_110.pdf": (1, 7),    # Slides 2-8 → Sourcing IA
    "carousel_jour_18.pdf": (8, 13),    # Slides 9-14 → Négociation Factuelle
    "carousel_jour_129.pdf": (14, 14),  # Slide 15 → Tail Spend Playbook (infographie)
    "carousel_jour_20.pdf": (15, 22),   # Slides 16-23 → Change Management
}


def split_pdf(input_pdf_path, mapping, output_dir):
    """Découpe un PDF en plusieurs fichiers selon le mapping."""
    
    if not os.path.exists(input_pdf_path):
        print(f"⚠️  Fichier introuvable : {input_pdf_path}")
        return False
    
    reader = PdfReader(input_pdf_path)
    total_pages = len(reader.pages)
    print(f"📄 {input_pdf_path} : {total_pages} pages détectées")
    
    os.makedirs(output_dir, exist_ok=True)
    
    for filename, (start, end) in mapping.items():
        writer = PdfWriter()
        
        for page_num in range(start, min(end + 1, total_pages)):
            writer.add_page(reader.pages[page_num])
        
        output_path = os.path.join(output_dir, filename)
        with open(output_path, 'wb') as f:
            writer.write(f)
        
        print(f"  ✅ {filename} ({end - start + 1} pages)")
    
    return True


# ============================================================
# SCRIPT PRINCIPAL
# ============================================================
if __name__ == "__main__":
    
    # Dossiers
    INPUT_DIR = "./pptx_exports"   # Où tu mets tes 2 PDFs complets
    OUTPUT_DIR = "./carrousels"    # Où les PDFs découpés seront créés
    
    print("=" * 50)
    print("✂️  DÉCOUPE DES CARROUSELS LINKEDIN")
    print("=" * 50)
    
    # Découper LOT 1
    lot1_path = os.path.join(INPUT_DIR, "LOT1_complet.pdf")
    print(f"
📋 Traitement LOT 1...")
    split_pdf(lot1_path, LOT1_MAPPING, OUTPUT_DIR)
    
    # Découper LOT 2
    lot2_path = os.path.join(INPUT_DIR, "LOT2_complet.pdf")
    print(f"
📋 Traitement LOT 2...")
    split_pdf(lot2_path, LOT2_MAPPING, OUTPUT_DIR)
    
    # Vérification
    print(f"
{'=' * 50}")
    print(f"📁 Contenu du dossier '{OUTPUT_DIR}' :")
    if os.path.exists(OUTPUT_DIR):
        for f in sorted(os.listdir(OUTPUT_DIR)):
            size = os.path.getsize(os.path.join(OUTPUT_DIR, f))
            print(f"  📄 {f} ({size // 1024} KB)")
    
    print(f"
🎉 Terminé ! {len(os.listdir(OUTPUT_DIR))} carrousels prêts.")

