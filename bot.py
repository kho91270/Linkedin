import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import json
import os
import sys
from PIL import Image, ImageDraw, ImageFont
import textwrap

# ============================================================
# CONFIGURATION
# ============================================================
LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_PERSON_ID = os.environ.get("LINKEDIN_PERSON_ID")
SHEET_ID = "1k4G-v1-nEgtE256nKUYjq-KfQd4A3CvMn03S1cp8NSE"
SHEET_NAME = "Calendrier Personnel"

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
    # Chercher la colonne "Publie" (colonne Q = 17)
    try:
        col_q = sheet.col_values(17)
    except:
        col_q = []
    
    for i, val in enumerate(col_a):
        if val.startswith("Jour"):
            row_index = i + 1
            # Verifier si deja publie
            if row_index <= len(col_q) and col_q[row_index - 1].upper() == "OUI":
                continue
            return row_index
    return None

# ============================================================
# GENERER IMAGE D'ACCROCHE
# ============================================================
def generate_image(hook_text, jour_num):
    """Genere une image 1080x1080 avec le hook text"""
    img = Image.new('RGB', (1080, 1080), color='#FFFFFF')
    draw = ImageDraw.Draw(img)
    
    # Bande bleue en haut
    draw.rectangle([0, 0, 1080, 120], fill='#1B3659')
    
    # Bande bleue en bas
    draw.rectangle([0, 960, 1080, 1080], fill='#1B3659')
    
    # Texte "MEHDI | Senior Procurement Consultant" en haut
    try:
        font_header = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        font_main = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
        font_footer = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
    except:
        font_header = ImageFont.load_default()
        font_main = ImageFont.load_default()
        font_footer = ImageFont.load_default()
    
    # Header text
    draw.text((540, 60), "MEHDI | Senior Procurement Consultant", font=font_header, fill='#FFFFFF', anchor='mm')
    
    # Main hook text (centered, wrapped)
    wrapper = textwrap.TextWrapper(width=28)
    lines = wrapper.wrap(text=hook_text)
    y_start = 540 - (len(lines) * 35)
    
    for i, line in enumerate(lines):
        draw.text((540, y_start + i * 70), line, font=font_main, fill='#1B3659', anchor='mm')
    
    # Footer
    draw.text((540, 1020), f"Jour {jour_num} | #Procurement #Strategy", font=font_footer, fill='#FFFFFF', anchor='mm')
    
    # Ligne accent
    draw.rectangle([100, 440, 980, 444], fill='#2E86AB')
    draw.rectangle([100, 640, 980, 644], fill='#2E86AB')
    
    filepath = f"image_jour_{jour_num}.png"
    img.save(filepath)
    return filepath

# ============================================================
# UPLOAD IMAGE SUR LINKEDIN
# ============================================================
def upload_image_linkedin(image_path):
    """Upload image et retourne l'asset URN"""
    # Etape 1: Register upload
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
    
    # Etape 2: Upload binary
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
    """Publie un post avec image"""
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
                "shareMediaCategory": "IMAGE",
                "media": [{
                    "status": "READY",
                    "media": image_asset
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
# PUBLIER POST CARROUSEL (PDF)
# ============================================================
def publish_carousel(contenu, jour_num):
    """Publie un carrousel depuis le PDF split"""
    pdf_path = f"carousel_pages/jour_{jour_num}.pdf"
    
    if not os.path.exists(pdf_path):
        print(f"  [!] PDF carrousel non trouve: {pdf_path}")
        print(f"  [>] Publication en texte+image a la place")
        return None
    
    # Register upload pour document
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
    
    # Publier
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
    """Publie un sondage LinkedIn"""
    url = "https://api.linkedin.com/rest/posts"
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "LinkedIn-Version": "202401",
        "X-Restli-Protocol-Version": "2.0.0"
    }
    
    # Construire les options du sondage
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
    """Poste un premier commentaire sous le post"""
    url = "https://api.linkedin.com/v2/socialActions/{}/comments".format(post_urn)
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
    """Marque le jour comme publie dans colonne Q"""
    sheet.update_cell(row_index, 17, "OUI")

# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 50)
    print("LINKEDIN AUTO-PUBLISHER v3.0")
    print("Images + Commentaires + Sondages")
    print("=" * 50)
    
    # Connexion
    sheet = connect_sheets()
    print("[OK] Connecte a Google Sheets")
    
    # Trouver le prochain jour
    row_index = get_next_day(sheet)
    if not row_index:
        print("[!] Tous les jours sont publies!")
        sys.exit(0)
    
    # Lire les donnees du jour
    row = sheet.row_values(row_index)
    jour = row[0]  # A: Jour
    contenu = row[4] if len(row) > 4 else ""  # E: Contenu
    hashtags = row[7] if len(row) > 7 else ""  # H: Hashtags
    
    # Nouvelles colonnes (I=8, J=9, K=10, L=11, M=12, N=13, O=14, P=15)
    image_hook = row[8] if len(row) > 8 else ""  # I: Image_Hook
    premier_commentaire = row[9] if len(row) > 9 else ""  # J: Premier_Commentaire
    type_post = row[10] if len(row) > 10 else "texte+image"  # K: Type_Post
    sondage_question = row[11] if len(row) > 11 else ""  # L: Sondage_Question
    sondage_opt1 = row[12] if len(row) > 12 else ""  # M
    sondage_opt2 = row[13] if len(row) > 13 else ""  # N
    sondage_opt3 = row[14] if len(row) > 14 else ""  # O
    sondage_opt4 = row[15] if len(row) > 15 else ""  # P
    
    jour_num = int(jour.replace("Jour ", ""))
    
    print(f"
[>] Publication: {jour}")
    print(f"    Type: {type_post}")
    print(f"    Hook: {image_hook}")
    
    # Formater le contenu
    contenu_final = contenu
    if hashtags:
        contenu_final = contenu + "

" + hashtags
    
    # ============================================================
    # PUBLICATION SELON LE TYPE
    # ============================================================
    post_id = None
    
    if type_post == "sondage" and sondage_question:
        # --- SONDAGE ---
        print(f"    [POLL] Question: {sondage_question}")
        options = [sondage_opt1, sondage_opt2, sondage_opt3, sondage_opt4]
        options = [o for o in options if o.strip()]
        
        result = publish_poll(contenu_final, sondage_question, options)
        if result == "DUPLICATE":
            print(f"  [!] DUPLICATE - On skip {jour}")
            mark_published(sheet, row_index)
            print(f"  [>] {jour} marque comme publie, prochain = Jour {jour_num + 1}")
            return
        post_id = result
        print(f"  [OK] Sondage publie!")
    
    elif type_post == "carrousel":
        # --- CARROUSEL ---
        print(f"    [CAROUSEL] Recherche du PDF...")
        result = publish_carousel(contenu_final, jour_num)
        if result == "DUPLICATE":
            print(f"  [!] DUPLICATE - On skip {jour}")
            mark_published(sheet, row_index)
            return
        if result is None:
            # Fallback: publier en texte+image
            print(f"    [FALLBACK] Publication en texte+image")
            image_path = generate_image(image_hook, jour_num)
            asset = upload_image_linkedin(image_path)
            result = publish_post_with_image(contenu_final, asset)
            if result == "DUPLICATE":
                mark_published(sheet, row_index)
                return
        post_id = result
        print(f"  [OK] Carrousel publie!")
    
    else:
        # --- TEXTE + IMAGE ---
        print(f"    [IMAGE] Generation de l'image...")
        image_path = generate_image(image_hook, jour_num)
        print(f"    [UPLOAD] Upload sur LinkedIn...")
        asset = upload_image_linkedin(image_path)
        result = publish_post_with_image(contenu_final, asset)
        if result == "DUPLICATE":
            print(f"  [!] DUPLICATE - On skip {jour}")
            mark_published(sheet, row_index)
            print(f"  [>] {jour} marque comme publie, prochain = Jour {jour_num + 1}")
            return
        post_id = result
        print(f"  [OK] Post + image publie!")
    
    # ============================================================
    # PREMIER COMMENTAIRE (boost algo)
    # ============================================================
    if post_id and premier_commentaire:
        import time
        print(f"
  [WAIT] Attente 30s avant commentaire (algo LinkedIn)...")
        time.sleep(30)
        post_comment(post_id, premier_commentaire)
    
    # Marquer comme publie
    mark_published(sheet, row_index)
    print(f"
{'=' * 50}")
    print(f"[DONE] {jour} publie avec succes!")
    print(f"{'=' * 50}")

if __name__ == "__main__":
    main()

