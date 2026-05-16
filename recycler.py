import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os
from datetime import datetime

# ============================================================
# CONTENT RECYCLER
# Identifie les posts publies il y a 30+ jours
# et propose un nouveau format pour les recycler
# ============================================================

SHEET_ID = "1k4G-v1-nEgtE256nKUYjq-KfQd4A3CvMn03S1cp8NSE"

FORMAT_ROTATION = {
    "texte+image": "carrousel",
    "carrousel": "sondage",
    "sondage": "texte+image",
}

ANGLE_VARIATIONS = [
    "[MISE A JOUR] {hook} - les chiffres ont change",
    "[DEBAT] {hook} - etes-vous d accord ?",
    "[DEEP DIVE] {hook} - allons plus loin",
    "[RETOUR D EXPERIENCE] {hook} - 3 mois apres",
    "[SONDAGE] {hook} - votez !",
]

def connect_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID)

def find_recyclable_posts():
    """Trouve les posts publies pour les recycler"""
    spreadsheet = connect_sheets()
    ws = spreadsheet.worksheet("Calendrier Personnel")
    all_data = ws.get_all_values()

    recyclable = []
    for i, row in enumerate(all_data[1:], start=2):
        if len(row) >= 17 and row[16].upper() == "OUI":
            jour_num = int(row[0].replace("Jour ", ""))
            categorie = row[3] if len(row) > 3 else ""
            sujet = row[2] if len(row) > 2 else ""
            contenu = row[4] if len(row) > 4 else ""
            format_actuel = row[10] if len(row) > 10 else "texte+image"
            hook = row[8] if len(row) > 8 else sujet

            recyclable.append({
                "jour": jour_num,
                "categorie": categorie,
                "sujet": sujet,
                "contenu": contenu[:200],
                "format_actuel": format_actuel,
                "nouveau_format": FORMAT_ROTATION.get(format_actuel, "carrousel"),
                "hook": hook
            })

    return recyclable

def propose_recycled_posts(recyclable):
    """Cree des propositions de posts recycles"""
    import random
    proposals = []

    # Prendre les 5 posts les plus anciens non encore recycles
    for post in recyclable[:5]:
        angle = random.choice(ANGLE_VARIATIONS)
        new_hook = angle.format(hook=post["hook"][:50])

        proposals.append([
            f"Recycle Jour {post['jour']}",
            post["sujet"],
            f"{post['format_actuel']} -> {post['nouveau_format']}",
            new_hook,
            post["nouveau_format"],
            ""
        ])

    return proposals

def write_proposals(proposals):
    """Ecrit les propositions dans l onglet Recycling"""
    spreadsheet = connect_sheets()

    try:
        ws = spreadsheet.worksheet("Recycling")
    except:
        ws = spreadsheet.add_worksheet(title="Recycling", rows=200, cols=6)
        ws.update("A1:F1", [["Source", "Sujet", "Transformation", "Nouveau Hook", "Format", "Publie"]])

    existing = ws.get_all_values()
    next_row = len(existing) + 1

    if proposals:
        ws.update(f"A{next_row}:F{next_row + len(proposals) - 1}", proposals)
        print(f"  [OK] {len(proposals)} posts proposes au recyclage")

def main():
    print("=" * 50)
    print("CONTENT RECYCLER")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    recyclable = find_recyclable_posts()
    print(f"  [OK] {len(recyclable)} posts recyclables identifies")

    if len(recyclable) == 0:
        print("  [!] Aucun post publie a recycler pour l instant")
        return

    proposals = propose_recycled_posts(recyclable)
    write_proposals(proposals)

    print("")
    print("[DONE] Propositions de recyclage ecrites!")

if __name__ == "__main__":
    main()

