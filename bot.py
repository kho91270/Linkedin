import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import json
import os
import sys
from PIL import Image, ImageDraw, ImageFont
import textwrap
import time

# ============================================================
# CONFIGURATION
# ============================================================
LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_PERSON_ID = None # Sera trouve AUTOMATIQUEMENT par le script
SHEET_ID = "1k4G-v1-nEgtE256nKUYjq-KfQd4A3CvMn03S1cp8NSE"
SHEET_NAME = "Calendrier Personnel"

# ============================================================
# RECUPERATION AUTOMATIQUE ID LINKEDIN (Nouveau !)
# ============================================================
def get_my_linkedin_id():
    url = "https://api.linkedin.com/v2/me"
    headers = {"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json().get("id")
    else:
        print(f"❌ Impossible de recuperer l'ID LinkedIn. Verifie ton TOKEN. ({resp.text})")
        sys.exit(1)

# ============================================================
# CONNEXION GOOGLE SHEETS
# ============================================================
def connect_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
    return sheet

# ============================================================
# TROUVER LE PROCHAIN JOUR A PUBLIER
# ============================================================
def get_next_day(sheet):
    col_a = sheet.col_values(1)
    try:
        col_q = sheet.col_values(17)
    except:
        col_q = []
    
    # On commence a 1 pour ignorer l'en-tete
    for i in range(1, len(col_a)):
        val = col_a[i]
        if val.startswith("Jour"):
            row_index = i + 1
            if row_index <= len(col_q) and col_q[row_index - 1].upper() == "OUI":
                continue
            return row_index
    return None

# ============================================================
# GENERER IMAGE D'ACCROCHE
# ============================================================
def generate_image(hook_text, jour_num, categorie=""):
    img = Image.new('RGB', (1080, 1080), color='#FFFFFF')
    draw = ImageDraw.Draw(img)
    
    colors = {
        "Framework": {"top": "#1B3659", "accent": "#2E86AB", "badge": "MATRICE V.A.L.U.E."},
        "Mythbusters": {"top": "#8B0000", "accent": "#FF4500", "badge": "PROCUREMENT MYTHBUSTERS"},
        "Storytelling": {"top": "#2C3E50", "accent": "#27AE60", "badge": "STORY TIME"},
    }
    style = colors.get(categorie, {"top": "#1B3659", "accent": "#2E86AB", "badge": "PROCUREMENT INSIGHT"})
    
    draw.rectangle([0, 0, 1080, 120], fill=style["top"])
    draw.rectangle([0, 960, 1080, 1080], fill=style["top"])
    
    try:
        font_header = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        font_badge = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        font_main = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
        font_footer = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
    except:
        font_header = ImageFont.load_default()
        font_badge = ImageFont.load_default()
        font_main = ImageFont.load_default()
        font_footer = ImageFont.load_default()
    
    draw.text((540, 60), "MEHDI | Senior Procurement Consultant", font=font_header, fill='#FFFFFF', anchor='mm')
    
    draw.rounded_rectangle([340, 150, 740, 200], radius=10, fill=style["accent"])
    draw.text((540, 175), style["badge"], font=font_badge, fill='#FFFFFF', anchor='mm')
    
    wrapper = textwrap.TextWrapper(width=30)
    lines = wrapper.wrap(text=hook_text)
    y_start = 540 - (len(lines) * 32)
    
    for i, line in enumerate(lines):
        draw.text((540, y_start + i * 64), line, font=font_main, fill=style["top"], anchor='mm')
    
    draw.rectangle([100, 440, 980, 444], fill=style["accent"])
    draw.rectangle([100, 640, 980, 644], fill=style["accent"])
    
    draw.text((540, 1020), f"Jour {jour_num} | #Procurement", font=font_footer, fill='#FFFFFF', anchor='mm')
    
    filepath = f"image_jour_{jour_num}.png"
    img.save(filepath)
    return filepath

# ============================================================
# UPLOAD IMAGE SUR LINKEDIN
# ============================================================
def upload_image_linkedin(image_path):
    register_url = "https://api.linkedin.com/v2/assets?action=registerUpload"
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    register_body = {
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
            "owner": f"urn:li:person:{LINKEDIN_PERSON_ID}",
            "serviceRelationships": [{
                "relationshipType": "OWNER",
                "identifier": "urn:li:userGeneratedContent"
            }]
        }
    }
    
    resp = requests.post(register_url, headers=headers, json=register_body)
    resp.raise_for_status()
    data = resp.json()
    
    upload_url = data["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
    asset = data["value"]["asset"]
    
    with open(image_path, 'rb') as f:
        upload_headers = {
            "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
            "Content-Type": "image/png"
        }
        resp2 = requests.put(upload_url, headers=upload_headers, data=f)
        resp2.raise_for_status()
    
    return asset

# ============================================================
# PUBLIER POST TEXTE + IMAGE
# ============================================================
def publish_post_with_image(contenu, image_asset):
    url = "https://api.linkedin.com/v2/ugcPosts"
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0"
    }
    body = {
        "author": f"urn:li:person:{LINKEDIN_PERSON_ID}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": contenu},
                "shareMediaCategory": "IMAGE" if image_asset else "NONE"
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
    }
    
    if image_asset:
        body["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [{
            "status": "READY",
            "media": image_asset
        }]
    
    resp = requests.post(url, headers=headers, json=body)
    if resp.status_code == 422 and "DUPLICATE" in resp.text:
        return "DUPLICATE"
    resp.raise_for_status()
    return resp.json().get("id", "OK")

# ============================================================
# PUBLIER CARROUSEL (PDF)
# ============================================================
def publish_carousel(contenu, jour_num):
    pdf_path = f"carousel_pages/jour_{jour_num}.pdf"
    
    if not os.path.exists(pdf_path):
        print(f"  [!] PDF carrousel non trouve: {pdf_path}")
        return None
    
    register_url = "https://api.linkedin.com/v2/assets?action=registerUpload"
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    register_body = {
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-document"],
            "owner": f"urn:li:person:{LINKEDIN_PERSON_ID}",
            "serviceRelationships": [{
                "relationshipType": "OWNER",
                "identifier": "urn:li:userGeneratedContent"
            }]
        }
    }
    
    resp = requests.post(register_url, headers=headers, json=register_body)
    resp.raise_for_status()
    data = resp.json()
    
    upload_url = data["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
    asset = data["value"]["asset"]
    
    with open(pdf_path, 'rb') as f:
        upload_headers = {
            "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
            "Content-Type": "application/pdf"
        }
        resp2 = requests.put(upload_url, headers=upload_headers, data=f)
        resp2.raise_for_status()
    
    url = "https://api.linkedin.com/v2/ugcPosts"
    body = {
        "author": f"urn:li:person:{LINKEDIN_PERSON_ID}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": contenu},
                "shareMediaCategory": "DOCUMENT",
                "media": [{
                    "status": "READY",
                    "media": asset,
                    "title": {"text": f"Carrousel Jour {jour_num}"}
                }]
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
    }
    
    resp = requests.post(url, headers=headers, json=body)
    if resp.status_code == 422 and "DUPLICATE" in resp.text:
        return "DUPLICATE"
    resp.raise_for_status()
    return resp.json().get("id", "OK")

# ============================================================
# PUBLIER SONDAGE (POLL)
# ============================================================
def publish_poll(contenu, question, options):
    url = "https://api.linkedin.com/rest/posts"
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "LinkedIn-Version": "202401",
        "X-Restli-Protocol-Version": "2.0.0"
    }
    
    poll_options = []
    for opt in options:
        if opt.strip():
            poll_options.append({"text": opt.strip()})
    
    body = {
        "author": f"urn:li:person:{LINKEDIN_PERSON_ID}",
        "commentary": contenu,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": []
        },
        "content": {
            "poll": {
                "question": question,
                "options": poll_options,
                "settings": {
                    "duration": "THREE_DAYS"
                }
            }
        },
        "lifecycleState": "PUBLISHED"
    }
    
    resp = requests.post(url, headers=headers, json=body)
    if resp.status_code == 422 and "DUPLICATE" in resp.text:
        return "DUPLICATE"
    resp.raise_for_status()
    return resp.headers.get("x-restli-id", "OK")

# ============================================================
# POSTER UN COMMENTAIRE
# ============================================================
def post_comment(post_urn, comment_text):
    url = f"https://api.linkedin.com/v2/socialActions/{post_urn}/comments"
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    body = {
        "actor": f"urn:li:person:{LINKEDIN_PERSON_ID}",
        "message": {"text": comment_text}
    }
    
    try:
        resp = requests.post(url, headers=headers, json=body)
        resp.raise_for_status()
        print(f"  [OK] Premier commentaire poste!")
        return True
    except Exception as e:
        print(f"  [!] Erreur commentaire: {e}")
        return False

# ============================================================
# MARQUER COMME PUBLIE
# ============================================================
def mark_published(sheet, row_index):
    sheet.update_cell(row_index, 17, "OUI")

# ============================================================
# MAIN
# ============================================================
def main():
    global LINKEDIN_PERSON_ID
    
    print("=" * 50)
    print("LINKEDIN AUTO-PUBLISHER v4.0 (Auto-ID)")
    print("=" * 50)
    
    # 1. Recuperation automatique de l'ID
    print("[>] Demarrage...")
    LINKEDIN_PERSON_ID = get_my_linkedin_id()
    print(f"[OK] ID LinkedIn trouve automatiquement : {LINKEDIN_PERSON_ID}")
    
    # 2. Connexion
    sheet = connect_sheets()
    print("[OK] Connecte a Google Sheets")
    
    # Trouver le prochain jour
    row_index = get_next_day(sheet)
    if not row_index:
        print("[!] Tous les 180 jours sont publies! Bravo!")
        sys.exit(0)
    
    # Lire les donnees du jour
    row = sheet.row_values(row_index)
    jour = row[0] if len(row) > 0 else ""
    sujet_fr = row[2] if len(row) > 2 else ""
    categorie = row[3] if len(row) > 3 else ""
    contenu = row[4] if len(row) > 4 else ""
    hashtags = row[7] if len(row) > 7 else ""
    image_hook = row[8] if len(row) > 8 else ""
    premier_commentaire = row[9] if len(row) > 9 else ""
    type_post = row[10] if len(row) > 10 else "texte+image"
    sondage_question = row[11] if len(row) > 11 else ""
    sondage_opt1 = row[12] if len(row) > 12 else ""
    sondage_opt2 = row[13] if len(row) > 13 else ""
    sondage_opt3 = row[14] if len(row) > 14 else ""
    sondage_opt4 = row[15] if len(row) > 15 else ""
    
    # Extraction blindee des chiffres
    digits = ''.join(filter(str.isdigit, jour))
    jour_num = int(digits) if digits else 0
    
    print(f"")
    print(f"[>] Publication: {jour}")
    print(f"    Sujet: {sujet_fr}")
    print(f"    Categorie: {categorie}")
    print(f"    Type: {type_post}")
    print(f"    Hook: {image_hook}")
    
    if hashtags:
        contenu_final = f"{contenu}\n\n{hashtags}"
    else:
        contenu_final = contenu
    
    # ============================================================
    # PUBLICATION SELON LE TYPE
    # ============================================================
    post_id = None
    
    if type_post == "sondage" and sondage_question:
        print(f"    [POLL] Question: {sondage_question}")
        options = [sondage_opt1, sondage_opt2, sondage_opt3, sondage_opt4]
        options = [o for o in options if o.strip()]
        
        result = publish_poll(contenu_final, sondage_question, options)
        if result == "DUPLICATE":
            mark_published(sheet, row_index)
            print(f"  [>] {jour} marque publie")
            return
        post_id = result
        print(f"  [OK] Sondage publie!")
    
    elif type_post == "carrousel":
        print(f"    [CAROUSEL] Recherche PDF...")
        result = publish_carousel(contenu_final, jour_num)
        if result == "DUPLICATE":
            mark_published(sheet, row_index)
            return
        if result is None:
            print(f"    [FALLBACK] Pas de PDF -> texte+image")
            if image_hook:
                image_path = generate_image(image_hook, jour_num, categorie)
                asset = upload_image_linkedin(image_path)
                result = publish_post_with_image(contenu_final, asset)
            else:
                result = publish_post_with_image(contenu_final, None)
            if result == "DUPLICATE":
                mark_published(sheet, row_index)
                return
        post_id = result
        print(f"  [OK] Carrousel publie!")
    
    else:
        if image_hook:
            print(f"    [IMAGE] Generation image...")
            image_path = generate_image(image_hook, jour_num, categorie)
            print(f"    [UPLOAD] Upload LinkedIn...")
            asset = upload_image_linkedin(image_path)
            result = publish_post_with_image(contenu_final, asset)
        else:
            result = publish_post_with_image(contenu_final, None)
        
        if result == "DUPLICATE":
            mark_published(sheet, row_index)
            print(f"  [>] {jour} marque publie")
            return
        post_id = result
        print(f"  [OK] Post publie!")
    
    # ============================================================
    # PREMIER COMMENTAIRE
    # ============================================================
    if post_id and premier_commentaire:
        print(f"")
        print(f"  [WAIT] Attente 30s avant commentaire...")
        time.sleep(30)
        post_comment(post_id, premier_commentaire)
    
    # Marquer comme publie
    mark_published(sheet, row_index)
    
    print(f"")
    print(f"{'=' * 50}")
    print(f"[DONE] {jour} publie avec succes!")
    print(f"{'=' * 50}")

if __name__ == "__main__":
    main()
