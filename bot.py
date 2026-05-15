
import csv
import urllib.request
import json
import os
import sys

# ============================================================
# CONFIGURATION
# ============================================================
URL_GOOGLE_SHEET = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTTPwa3zExjfj3caHJPqvTl-fIRG2BM1QwKhN3nDi9XsLJFUSx3U2pdfkidi6aglmkCwoTE4R4q_Tox/pub?gid=1251610521&single=true&output=csv"
ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")

# Dossier contenant les carrousels PDF (nommés: carousel_jour_17.pdf, etc.)
CAROUSEL_DIR = os.environ.get("CAROUSEL_DIR", "./carrousels")

# Fichier compteur pour tracker le jour actuel
COUNTER_FILE = os.environ.get("COUNTER_FILE", "./jour_counter.txt")

# ============================================================
# STRUCTURE DES COLONNES DU GOOGLE SHEET
# ============================================================
COL_JOUR = 0          # A: "Jour 1", "Jour 2", etc.
COL_CATEGORIE = 1     # B: Catégorie
COL_SUJET = 2         # C: Sujet (EN/FR)
COL_FORMAT = 3        # D: Format (📊 Stat, 📋 Carrousel, etc.)
COL_CONTENU = 4       # E: Contenu du Post
COL_CTA_EN = 5        # F: CTA (EN)
COL_CTA_FR = 6        # G: CTA (FR)
COL_HASHTAGS = 7      # H: Mots-clés / Hashtags


# ============================================================
# GESTION DU COMPTEUR DE JOURS
# ============================================================
def get_current_day():
    """Lit le jour actuel depuis le fichier compteur."""
    try:
        with open(COUNTER_FILE, 'r') as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 1  # Commence au jour 1 par défaut

def increment_day():
    """Incrémente le compteur pour le prochain run."""
    current = get_current_day()
    next_day = current + 1 if current < 150 else 1  # Boucle après 150
    with open(COUNTER_FILE, 'w') as f:
        f.write(str(next_day))
    return current


# ============================================================
# LECTURE DU GOOGLE SHEET
# ============================================================
def recuperer_post_du_jour(jour_num):
    """Récupère le post correspondant au jour donné."""
    try:
        req = urllib.request.Request(URL_GOOGLE_SHEET)
        with urllib.request.urlopen(req) as response:
            lignes = [l.decode('utf-8-sig') for l in response.readlines()]

        lecteur = list(csv.reader(lignes))
        if not lecteur:
            print("❌ Le Google Sheet semble vide.")
            return None

        # Chercher la ligne correspondant au jour
        jour_cible = f"Jour {jour_num}"
        
        for ligne in lecteur[1:]:  # Skip header row
            if len(ligne) < 8:
                continue
                
            # Vérifier si c'est le bon jour
            jour_cell = ligne[COL_JOUR].strip()
            if jour_cell.lower() == jour_cible.lower():
                return {
                    'jour': jour_cell,
                    'categorie': ligne[COL_CATEGORIE].strip(),
                    'sujet': ligne[COL_SUJET].strip(),
                    'format': ligne[COL_FORMAT].strip(),
                    'contenu': ligne[COL_CONTENU].strip(),
                    'cta_en': ligne[COL_CTA_EN].strip(),
                    'cta_fr': ligne[COL_CTA_FR].strip(),
                    'hashtags': ligne[COL_HASHTAGS].strip()
                }

        print(f"❌ '{jour_cible}' introuvable dans le Google Sheet.")
        return None

    except Exception as e:
        print(f"❌ Erreur de lecture du Google Sheet : {e}")
        return None


# ============================================================
# MISE EN FORME DU POST LINKEDIN
# ============================================================
def formater_post(post_data):
    """Formate le post pour LinkedIn avec mise en forme professionnelle."""
    contenu = post_data['contenu']
    hashtags = post_data['hashtags']
    
    # Séparer EN et FR
    if 'FR:' in contenu:
        parts = contenu.split('FR:', 1)
        en_part = parts[0].replace('EN:', '').strip()
        fr_part = parts[1].strip()
    else:
        en_part = contenu
        fr_part = ""
    
    # Construction du post formaté
    post_formate = f"🇬🇧 EN

{en_part}"
    
    if fr_part:
        post_formate += f"

---

🇫🇷 FR

{fr_part}"
    
    post_formate += f"

---
{hashtags}"
    
    return post_formate


# ============================================================
# API LINKEDIN - RÉCUPÉRER L'URN PERSONNEL
# ============================================================
def get_personal_urn():
    """Récupère l'URN LinkedIn de l'utilisateur."""
    url = "https://api.linkedin.com/v2/userinfo"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as response:
            user_info = json.loads(response.read().decode('utf-8'))
            sub = user_info.get("sub")
            if sub:
                return f"urn:li:person:{sub}"
            return None
    except Exception as e:
        print(f"❌ Impossible de récupérer l'ID personnel : {e}")
        return None


# ============================================================
# API LINKEDIN - PUBLICATION TEXTE SIMPLE
# ============================================================
def publier_texte(contenu_texte, author_urn):
    """Publie un post texte simple sur LinkedIn."""
    url = "https://api.linkedin.com/v2/ugcPosts"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json"
    }

    payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": contenu_texte},
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }

    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode('utf-8'),
            headers=headers, method='POST'
        )
        with urllib.request.urlopen(req) as response:
            print("✅ Post TEXTE publié avec succès !")
            return True
    except urllib.error.HTTPError as e:
        print(f"❌ Erreur publication texte : {e.code} - {e.read().decode('utf-8')}")
        return False


# ============================================================
# API LINKEDIN - PUBLICATION CARROUSEL (PDF)
# ============================================================
def publier_carrousel(contenu_texte, pdf_path, author_urn):
    """
    Publie un carrousel LinkedIn (document PDF) en 3 étapes :
    1. Initialiser l'upload
    2. Uploader le fichier PDF
    3. Créer le post avec le document
    """
    
    # --- ÉTAPE 1 : Initialiser l'upload ---
    register_url = "https://api.linkedin.com/v2/assets?action=registerUpload"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    register_payload = {
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-document"],
            "owner": author_urn,
            "serviceRelationships": [{
                "relationshipType": "OWNER",
                "identifier": "urn:li:userGeneratedContent"
            }]
        }
    }

    try:
        req = urllib.request.Request(
            register_url,
            data=json.dumps(register_payload).encode('utf-8'),
            headers=headers, method='POST'
        )
        with urllib.request.urlopen(req) as response:
            register_result = json.loads(response.read().decode('utf-8'))
        
        upload_url = register_result['value']['uploadMechanism'][
            'com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest']['uploadUrl']
        asset_urn = register_result['value']['asset']
        
        print(f"  📤 Upload URL obtenue. Asset: {asset_urn}")

    except Exception as e:
        print(f"❌ Erreur initialisation upload : {e}")
        return False

    # --- ÉTAPE 2 : Uploader le PDF ---
    try:
        with open(pdf_path, 'rb') as f:
            pdf_data = f.read()

        upload_headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/octet-stream"
        }

        req = urllib.request.Request(
            upload_url, data=pdf_data,
            headers=upload_headers, method='PUT'
        )
        with urllib.request.urlopen(req) as response:
            pass  # 201 Created = succès
        
        print(f"  📄 PDF uploadé ({len(pdf_data)} bytes)")

    except Exception as e:
        print(f"❌ Erreur upload PDF : {e}")
        return False

    # --- ÉTAPE 3 : Créer le post avec le document ---
    post_url = "https://api.linkedin.com/v2/ugcPosts"
    post_headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json"
    }

    post_payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": contenu_texte},
                "shareMediaCategory": "DOCUMENT",
                "media": [{
                    "status": "READY",
                    "media": asset_urn,
                    "title": {"text": "Swipe pour découvrir →"}
                }]
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }

    try:
        req = urllib.request.Request(
            post_url, data=json.dumps(post_payload).encode('utf-8'),
            headers=post_headers, method='POST'
        )
        with urllib.request.urlopen(req) as response:
            print("✅ Post CARROUSEL publié avec succès !")
            return True
    except urllib.error.HTTPError as e:
        print(f"❌ Erreur publication carrousel : {e.code} - {e.read().decode('utf-8')}")
        return False


# ============================================================
# DÉTECTION DU TYPE DE POST (CARROUSEL OU TEXTE)
# ============================================================
def get_carousel_pdf_path(jour_num):
    """
    Vérifie si un PDF carrousel existe pour ce jour.
    Convention de nommage : carousel_jour_17.pdf
    """
    filename = f"carousel_jour_{jour_num}.pdf"
    filepath = os.path.join(CAROUSEL_DIR, filename)
    
    if os.path.exists(filepath):
        return filepath
    return None


# ============================================================
# SCRIPT PRINCIPAL
# ============================================================
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 LINKEDIN AUTO-PUBLISHER")
    print("=" * 50)
    
    # Vérification du token
    if not ACCESS_TOKEN:
        print("❌ LINKEDIN_ACCESS_TOKEN manquant dans les variables d'environnement.")
        sys.exit(1)
    
    # Déterminer le jour à publier
    jour_num = increment_day()
    print(f"
📅 Publication du Jour {jour_num}/150")
    
    # Récupérer le post depuis Google Sheet
    post_data = recuperer_post_du_jour(jour_num)
    if not post_data:
        print("❌ Impossible de récupérer le post. Fin du script.")
        sys.exit(1)
    
    print(f"   📌 Sujet : {post_data['sujet'][:60]}")
    print(f"   🏷️  Format : {post_data['format']}")
    print(f"   📂 Catégorie : {post_data['categorie'][:40]}")
    
    # Formater le contenu
    contenu_formate = formater_post(post_data)
    
    # Récupérer l'URN LinkedIn
    author_urn = get_personal_urn()
    if not author_urn:
        print("❌ Impossible de récupérer l'identité LinkedIn.")
        sys.exit(1)
    
    # Décider : carrousel ou texte ?
    pdf_path = get_carousel_pdf_path(jour_num)
    
    if pdf_path:
        print(f"
   📋 Carrousel détecté : {pdf_path}")
        print("   Envoi du carrousel vers LinkedIn...")
        success = publier_carrousel(contenu_formate, pdf_path, author_urn)
    else:
        print(f"
   💬 Post texte (pas de carrousel pour ce jour)")
        print("   Envoi du post texte vers LinkedIn...")
        success = publier_texte(contenu_formate, author_urn)
    
    if success:
        print(f"
🎉 Jour {jour_num} publié ! Prochain : Jour {jour_num + 1 if jour_num < 150 else 1}")
    else:
        print(f"
⚠️ Échec de publication pour le Jour {jour_num}.")
        sys.exit(1)

