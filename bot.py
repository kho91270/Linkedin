import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import json
import os
import sys
import time
import re

# ============================================================
# CONFIGURATION
# ============================================================
LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
LEONARDO_API_KEY = os.environ.get("LEONARDO_API_KEY")
LINKEDIN_PERSON_ID = None
SHEET_ID = "1k4G-v1-nEgtE256nKUYjq-KfQd4A3CvMn03S1cp8NSE"
SHEET_NAME = "Calendrier Personnel"

# ============================================================
# RECUPERATION AUTOMATIQUE ID LINKEDIN
# ============================================================
def get_my_linkedin_id():
    headers = {"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"}
    resp1 = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers)
    if resp1.status_code == 200:
        return resp1.json().get("sub")
    resp2 = requests.get("https://api.linkedin.com/v2/me", headers=headers)
    if resp2.status_code == 200:
        return resp2.json().get("id")
    print("  Impossible de recuperer l'ID LinkedIn.")
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
# FORMATER LE POST (AERATION AUTOMATIQUE INTELLIGENTE)
# ============================================================
def formater_post_linkedin(contenu_brut):
    if not contenu_brut:
        return ""
    
    # 1. Nettoyage initial : on aplatit tout en un seul bloc propre
    contenu = contenu_brut.replace("<br>", " ").replace("<br/>", " ").replace("\n", " ")
    contenu = re.sub(r'\s+', ' ', contenu).strip()

    # 2. Chercher le point de bascule entre l'Anglais et le Français
    match = re.search(r'(\*\*Français|\*\*FR|Français\s*:|FR\s*:|🇫🇷)', contenu, flags=re.IGNORECASE)
    
    if match and match.start() > 10:
        split_idx = match.start()
        part_en = contenu[:split_idx].strip()
        part_fr = contenu[split_idx:].strip()
        
        en_aere = aerer_texte(part_en)
        fr_aere = aerer_texte(part_fr)
        
        return en_aere + "\n\n➖➖➖➖➖➖➖➖➖➖\n\n" + fr_aere
    
    # Si c'est juste une seule langue
    return aerer_texte(contenu)

def aerer_texte(texte):
    # Séparer les en-têtes (ex: **English:**) pour qu'ils ne soient pas collés à la phrase
    texte = re.sub(r'(\*\*(?:English|Français|FR|EN)[^*]*\*\*)\s*', r'\1. ', texte, flags=re.IGNORECASE)
    texte = texte.replace(".. ", ". ")

    # Découpe intelligente par phrase (après un point/exclamation/interrogation suivi d'une majuscule)
    phrases = re.split(r'(?<=[.!?])\s+(?=[A-ZÉÀÊ"\'*])', texte)
    
    paragraphes = []
    current_para = []
    
    for phrase in phrases:
        phrase = phrase.strip()
        if not phrase:
            continue
            
        # Isoler les titres pour qu'ils soient seuls sur leur ligne
        if phrase.startswith("**") and ("English" in phrase or "Français" in phrase or "FR" in phrase or "EN" in phrase):
            if phrase.endswith("."):
                phrase = phrase[:-1]
            if current_para:
                paragraphes.append(" ".join(current_para))
                current_para = []
            paragraphes.append(phrase)
            continue
            
        current_para.append(phrase)
        
        # Regrouper par 2 phrases max pour aérer
        if len(current_para) >= 2:
            paragraphes.append(" ".join(current_para))
            current_para = []
            
    if current_para:
        paragraphes.append(" ".join(current_para))
        
    return "\n\n".join(paragraphes)

# ============================================================
# GENERER IMAGE VIA LEONARDO AI
# ============================================================
def generate_image_leonardo(sujet, categorie=""):
    """
    Genere une image professionnelle via Leonardo AI API.
    Retourne le chemin du fichier image telecharge.
    """
    if not LEONARDO_API_KEY:
        print("  [!] LEONARDO_API_KEY non configuree. Pas d'image.")
        return None

    # Construire un prompt professionnel adapte au sujet
    style_map = {
        "Framework": "clean corporate infographic style, blue and white tones, minimalist",
        "Mythbusters": "dramatic lighting, myth vs reality concept, bold red accents",
        "Storytelling": "warm cinematic lighting, business narrative scene, human connection",
    }
    style = style_map.get(categorie, "professional corporate photography, modern office environment, clean composition")

    prompt = (
        f"Professional LinkedIn post illustration about: {sujet}. "
        f"Style: {style}. "
        f"High quality, photorealistic, no text overlays, no watermarks, "
        f"suitable for a senior procurement consultant's personal brand. "
        f"Square format 1080x1080, modern and clean aesthetic."
    )

    # Etape 1 : Lancer la generation
    url = "https://cloud.leonardo.ai/api/rest/v1/generations"
    headers = {
        "Authorization": f"Bearer {LEONARDO_API_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "prompt": prompt,
        "modelId": "6b645e3a-d64f-4341-a6d8-7a3690fbf042",  # Leonardo Phoenix 1.0
        "width": 1024,
        "height": 1024,
        "num_images": 1,
        "alchemy": True,
        "photoReal": True,
        "photoRealVersion": "v2"
    }

    print(f"  [LEONARDO] Generation image en cours...")
    print(f"  [PROMPT] {prompt[:100]}...")

    resp = requests.post(url, headers=headers, json=body)
    if resp.status_code != 200:
        print(f"  [!] Erreur Leonardo generation: {resp.status_code} - {resp.text}")
        return None

    generation_id = resp.json().get("sdGenerationJob", {}).get("generationId")
    if not generation_id:
        print(f"  [!] Pas de generationId dans la reponse Leonardo")
        return None

    # Etape 2 : Attendre que l'image soit prete (polling)
    print(f"  [LEONARDO] Attente generation (ID: {generation_id})...")
    get_url = f"https://cloud.leonardo.ai/api/rest/v1/generations/{generation_id}"
    
    for attempt in range(20):  # Max 60 secondes d'attente
        time.sleep(3)
        resp2 = requests.get(get_url, headers=headers)
        if resp2.status_code != 200:
            continue
        
        data = resp2.json()
        gen_data = data.get("generations_by_pk", {})
        status = gen_data.get("status")
        
        if status == "COMPLETE":
            images = gen_data.get("generated_images", [])
            if images:
                image_url = images[0].get("url")
                print(f"  [LEONARDO] Image generee avec succes!")
                # Telecharger l'image
                img_resp = requests.get(image_url)
                if img_resp.status_code == 200:
                    filepath = "linkedin_post_image.png"
                    with open(filepath, "wb") as f:
                        f.write(img_resp.content)
                    print(f"  [OK] Image sauvegardee: {filepath}")
                    return filepath
            break
        elif status == "FAILED":
            print(f"  [!] Generation Leonardo echouee.")
            break
    
    print(f"  [!] Timeout generation Leonardo.")
    return None

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
        "LinkedIn-Version": "202604",
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
                "settings": {"duration": "THREE_DAYS"}
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
# TROUVER LE PROCHAIN JOUR A PUBLIER
# ============================================================
def get_next_day(sheet):
    col_a = sheet.col_values(1)
    try:
        col_q = sheet.col_values(17)
    except:
        col_q = []
    for i in range(1, len(col_a)):
        val = col_a[i]
        if val.startswith("Jour"):
            row_index = i + 1
            if row_index <= len(col_q) and col_q[row_index - 1].upper() == "OUI":
                continue
            return row_index
    return None

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
    print("LINKEDIN AUTO-PUBLISHER v5.2 (Aeration Intelligente Regex)")
    print("=" * 50)

    # 1. Recuperation automatique de l'ID
    print("[>] Demarrage...")
    LINKEDIN_PERSON_ID = get_my_linkedin_id()
    print(f"[OK] ID LinkedIn trouve: {LINKEDIN_PERSON_ID}")

    # 2. Connexion Google Sheets
    sheet = connect_sheets()
    print("[OK] Connecte a Google Sheets")

    # 3. Trouver le prochain jour
    row_index = get_next_day(sheet)
    if not row_index:
        print("[!] Tous les 180 jours sont publies! Bravo!")
        sys.exit(0)

    # 4. Lire les donnees du jour
    row = sheet.row_values(row_index)
    jour = row[0] if len(row) > 0 else ""
    sujet_fr = row[2] if len(row) > 2 else ""
    categorie = row[3] if len(row) > 3 else ""
    contenu_brut = row[4] if len(row) > 4 else ""
    hashtags = row[7] if len(row) > 7 else ""
    image_hook = row[8] if len(row) > 8 else ""
    premier_commentaire = row[9] if len(row) > 9 else ""
    type_post = row[10] if len(row) > 10 else "texte+image"
    sondage_question = row[11] if len(row) > 11 else ""
    sondage_opt1 = row[12] if len(row) > 12 else ""
    sondage_opt2 = row[13] if len(row) > 13 else ""
    sondage_opt3 = row[14] if len(row) > 14 else ""
    sondage_opt4 = row[15] if len(row) > 15 else ""

    digits = ''.join(filter(str.isdigit, jour))
    jour_num = int(digits) if digits else 0

    print(f"")
    print(f"[>] Publication: {jour}")
    print(f"    Sujet: {sujet_fr}")
    print(f"    Categorie: {categorie}")
    print(f"    Type: {type_post}")

    # 5. FORMATAGE LINKEDIN (Découpe intelligente)
    contenu = formater_post_linkedin(contenu_brut)
    if hashtags:
        contenu_final = contenu + "\n\n" + hashtags
    else:
        contenu_final = contenu

    # 6. PUBLICATION SELON LE TYPE
    post_id = None

    if type_post == "sondage" and sondage_question:
        print(f"    [POLL] Question: {sondage_question}")
        options = [o for o in [sondage_opt1, sondage_opt2, sondage_opt3, sondage_opt4] if o.strip()]
        result = publish_poll(contenu_final, sondage_question, options)
        if result == "DUPLICATE":
            mark_published(sheet, row_index)
            print(f"  [>] {jour} marque publie (duplicate)")
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
            print(f"    [FALLBACK] Pas de PDF -> Leonardo AI image")
            image_path = generate_image_leonardo(sujet_fr, categorie)
            if image_path:
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
        # TEXTE + IMAGE via Leonardo AI
        print(f"    [LEONARDO] Generation image IA pour: {sujet_fr}")
        image_path = generate_image_leonardo(sujet_fr, categorie)
        if image_path:
            print(f"    [UPLOAD] Upload LinkedIn...")
            asset = upload_image_linkedin(image_path)
            result = publish_post_with_image(contenu_final, asset)
        else:
            print(f"    [TEXT-ONLY] Pas d'image, publication texte seul")
            result = publish_post_with_image(contenu_final, None)

        if result == "DUPLICATE":
            mark_published(sheet, row_index)
            print(f"  [>] {jour} marque publie (duplicate)")
            return
        post_id = result
        print(f"  [OK] Post publie!")

    # 7. PREMIER COMMENTAIRE
    if post_id and premier_commentaire:
        print(f"")
        print(f"  [WAIT] Attente 30s avant commentaire...")
        time.sleep(30)
        post_comment(post_id, premier_commentaire)

    # 8. MARQUER COMME PUBLIE
    mark_published(sheet, row_index)

    print(f"")
    print(f"{'=' * 50}")
    print(f"[DONE] {jour} publie avec succes!")
    print(f"{'=' * 50}")

if __name__ == "__main__":
    main()
