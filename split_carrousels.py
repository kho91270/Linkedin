import os
import sys
import subprocess

try:
    from PyPDF2 import PdfReader, PdfWriter
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyPDF2"])
    from PyPDF2 import PdfReader, PdfWriter

# Mapping : quel carrousel = quelles pages dans le PDF
LOT1_MAPPING = {
    "carousel_jour_17.pdf": (0, 5),
    "carousel_jour_21.pdf": (6, 10),
    "carousel_jour_14.pdf": (11, 16),
    "carousel_jour_64.pdf": (17, 17),
    "carousel_jour_22.pdf": (18, 23),
}

LOT2_MAPPING = {
    "carousel_jour_46.pdf": (0, 0),
    "carousel_jour_110.pdf": (1, 7),
    "carousel_jour_18.pdf": (8, 13),
    "carousel_jour_129.pdf": (14, 14),
    "carousel_jour_20.pdf": (15, 22),
}


def split_pdf(input_pdf_path, mapping, output_dir):
    if not os.path.exists(input_pdf_path):
        print("⚠️ Fichier introuvable : " + input_pdf_path)
        return False

    reader = PdfReader(input_pdf_path)
    total_pages = len(reader.pages)
    print("📄 " + input_pdf_path + " : " + str(total_pages) + " pages")

    os.makedirs(output_dir, exist_ok=True)

    for filename, (start, end) in mapping.items():
        writer = PdfWriter()
        for page_num in range(start, min(end + 1, total_pages)):
            writer.add_page(reader.pages[page_num])
        output_path = os.path.join(output_dir, filename)
        with open(output_path, 'wb') as f:
            writer.write(f)
        nb_pages = end - start + 1
        print("  ✅ " + filename + " (" + str(nb_pages) + " pages)")

    return True


if __name__ == "__main__":
    INPUT_DIR = "./pptx_exports"
    OUTPUT_DIR = "./carrousels"

    print("=" * 50)
    print("✂️ DECOUPE DES CARROUSELS")
    print("=" * 50)

    print("")
    print("📋 LOT 1...")
    split_pdf(os.path.join(INPUT_DIR, "LOT1_complet.pdf"), LOT1_MAPPING, OUTPUT_DIR)

    print("")
    print("📋 LOT 2...")
    split_pdf(os.path.join(INPUT_DIR, "LOT2_complet.pdf"), LOT2_MAPPING, OUTPUT_DIR)

    print("")
    print("🎉 Termine !")
    if os.path.exists(OUTPUT_DIR):
        for f in sorted(os.listdir(OUTPUT_DIR)):
            print("  📄 " + f)
