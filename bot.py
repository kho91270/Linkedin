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

CAROUSEL_DIR = os.environ.get("CAROUSEL_DIR", "./carrousels")
COUNTER_FILE = os.environ.get("COUNTER_FILE", "./jour_counter.txt")

# Structure des colonnes du Google Sheet
COL_JOUR = 0
COL_CATEGORIE = 1
COL_SUJET = 2
COL_FORMAT = 3
COL_CONTENU = 4
COL_CTA_EN = 5
COL_CTA_FR = 6
COL_HASHTAGS = 7


# ============================================================
# GESTION DU COMPTEUR
# ============================================================
def get_current_day():
    try:
        with open(COUNTER_FILE, 'r') as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 1


def increment_day():
    current = get_current_day()
    next_day = current + 1 if current < 150 else 1
    with open(COUNTER_FILE, 'w') as f:
        f.write(str(next_day))


# ============================================================
# LECTURE DU GOOGLE SHEET
# ============================================================
def recuperer_post_du_jour():
    jour_num = get_current_day()
    jour_cible = "Jour " + str(jour_num)

    try:
        req = urllib.request.Request(URL_GOOGLE_SHEET)
        with urllib.request.urlopen(req) as response:
            lignes = [l.decode('utf-8-sig') for l in response.readlines()]

        lecteur = list(csv.reader(lignes))
        if not lecteur:
            print("❌ Le Google Sheet semble vide.")
            return None, jour_num

        for ligne in lecteur[1:]:
            if len(ligne) < 8:
                continue
            if ligne[COL_JOUR].strip().lower() == jour_cible.lower():
                contenu = ligne[COL_CONTENU].strip()
                hashtags = ligne[COL_HASHTAGS].strip()

                # Mise en forme
                contenu_pro = contenu.replace("EN:", "\U0001f1ec\U0001f1e7 EN
")
                contenu_pro = contenu_pro.replace("FR:", "

\U0001f1eb\U0001f1f7 FR
")
                texte_complet = contenu_pro + "

---
" + hashtags

                return texte_complet, jour_num

        print("❌ '" + jour_cible + "' introuvable dans le Google Sheet.")
        return None, jour_num

    except Exception as e:
        print("❌ Erreur lecture Google Sheet : " + str(e))
        return None, jour_num


# ============================================================
# API LINKEDIN - URN
# ============================================================
def get_personal_urn():
    url = "https://api.linkedin.com/v2/userinfo"
    headers = {"Authorization": "Bearer " + ACCESS_TOKEN}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as response:
            user_info = json.loads(response.read().decode('utf-8'))
            sub = user_info.get("sub")
            if sub:
                return "urn:li:person:" + sub
            return None
    except Exception as e:
        print("❌ Impossible de recuperer l'ID personnel : " + str(e))
        return None


# ============================================================
# PUBLICATION TEXTE SIMPLE
# ============================================================
def publier_texte(contenu_texte, author_urn):
    url = "https://api.linkedin.com/v2/ugcPosts"
    headers = {
        "Authorization": "Bearer " + ACCESS_TOKEN,
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
            print("✅ Post TEXTE publie avec succes !")
            return True
    except urllib.error.HTTPError as e:
        print("❌ Erreur publication texte : " + str(e.code) + " - " + e.read().decode('utf-8'))
        return False


# ============================================================
# PUBLICATION CARROUSEL (PDF)
# ============================================================
def publier_carrousel(contenu_texte, pdf_path, author_urn):
    headers = {
        "Authorization": "Bearer " + ACCESS_TOKEN,
        "Content-Type": "application/json"
    }

    # ETAPE 1 : Initialiser l'upload
    register_url = "https://api.linkedin.com/v2/assets?action=registerUpload"
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
            result = json.loads(response.read().decode('utf-8'))

        upload_url = result['value']['uploadMechanism']['com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest']['uploadUrl']
        asset_urn = result['value']['asset']
        print("  ✅ Etape 1/3 : URL d'upload obtenue")

    except Exception as e:
        print("  ❌ Etape 1/3 echouee : " + str(e))
        return False

    # ETAPE 2 : Uploader le PDF
    try:
        with open(pdf_path, 'rb') as f:
            pdf_data = f.read()

        upload_headers = {
            "Authorization": "Bearer " + ACCESS_TOKEN,
            "Content-Type": "application/octet-stream"
        }
        req = urllib.request.Request(
            upload_url, data=pdf_data,
            headers=upload_headers, method='PUT'
        )
        with urllib.request.urlopen(req) as response:
            pass
        print("  ✅ Etape 2/3 : PDF uploade (" + str(len(pdf_data)) + " bytes)")

    except Exception as e:
        print("  ❌ Etape 2/3 echouee : " + str(e))
        return False

    # ETAPE 3 : Creer le post avec le document
    post_url = "https://api.linkedin.com/v2/ugcPosts"
    post_headers = {
        "Authorization": "Bearer " + ACCESS_TOKEN,
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
                    "title": {"text": "Swipe pour decouvrir"}
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
            print("  ✅ Etape 3/3 : Post carrousel publie !")
            return True
    except urllib.error.HTTPError as e:
        print("  ❌ Etape 3/3 echouee : " + str(e.code) + " - " + e.read().decode('utf-8'))
        return False


# ============================================================
# DETECTION CARROUSEL
# ============================================================
def get_carousel_pdf_path(jour_num):
    filename = "carousel_jour_" + str(jour_num) + ".pdf"
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

    if not ACCESS_TOKEN:
        print("❌ LINKEDIN_ACCESS_TOKEN manquant.")
        sys.exit(1)

    # Recuperer le post du jour
    post_texte, jour_num = recuperer_post_du_jour()

    if not post_texte:
        print("Fin du script : rien a publier.")
        sys.exit(1)

    print("")
    print("📅 Publication du Jour " + str(jour_num) + "/150")

    # Recuperer l'URN LinkedIn
    author_urn = get_personal_urn()
    if not author_urn:
        print("❌ Impossible de recuperer l'identite LinkedIn.")
        sys.exit(1)

    # Verifier si un carrousel existe pour ce jour
    pdf_path = get_carousel_pdf_path(jour_num)

    if pdf_path:
        print("📋 Carrousel detecte : " + pdf_path)
        success = publier_carrousel(post_texte, pdf_path, author_urn)
    else:
        print("💬 Post texte simple")
        success = publier_texte(post_texte, author_urn)

    if success:
        increment_day()
        next_day = jour_num + 1 if jour_num < 150 else 1
        print("")
        print("🎉 Jour " + str(jour_num) + " publie ! Prochain : Jour " + str(next_day))
    else:
        print("")
        print("⚠️ Echec pour le Jour " + str(jour_num) + ".")
        sys.exit(1)
