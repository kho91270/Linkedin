import csv
import urllib.request
import json
import os

# Le lien pointe désormais vers votre Calendrier Personnel d'Expertise
URL_GOOGLE_SHEET = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTjZqY4aO78EPuGJO-B7RZR8Q0TG1toSa21ff_S-P4xBxlEgF19E5QD9HAfMdkspXU7cv6_Ayh9wc3T/pub?gid=1251610521&single=true&output=csv"
ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")

def recuperer_post_du_jour():
    try:
        req = urllib.request.Request(URL_GOOGLE_SHEET)
        with urllib.request.urlopen(req) as response:
            lignes = [l.decode('utf-8') for l in response.readlines()]
            
        lecteur = list(csv.DictReader(lignes))
        jour_cible = "Jour 1" 
        
        for ligne in lecteur:
            if ligne.get('Jour') == jour_cible:
                contenu = ligne.get('Contenu du Post (EN / FR)')
                mots_cles = ligne.get('Mots-clés')
                
                if not contenu:
                    return None
                    
                # --- MISE EN FORME PROFESSIONNELLE ---
                # Ajout des drapeaux et aération du texte pour un rendu Premium
                contenu_pro = contenu.replace("EN:", "🇬🇧 **EN**\n")
                contenu_pro = contenu_pro.replace("FR:", "\n\n🇫🇷 **FR**\n")
                
                texte_complet = f"{contenu_pro}\n\n---\n{mots_cles}"
                # -------------------------------------

                return texte_complet
                
        return None
    except Exception as e:
        print(f"Erreur de lecture du Google Sheet : {e}")
        return None

def get_personal_urn():
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

def publier_sur_linkedin(contenu_texte):
    if not ACCESS_TOKEN:
        print("❌ Erreur : Le jeton d'accès est introuvable.")
        return False

    AUTHOR_URN = get_personal_urn()
    if not AUTHOR_URN:
        return False

    url = "https://api.linkedin.com/v2/ugcPosts"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json"
    }
    
    payload = {
        "author": AUTHOR_URN,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": contenu_texte
                },
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }

    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            print("✅ SUCCÈS : Le post expert est en ligne sur votre profil !")
            return True
    except urllib.error.HTTPError as e:
        print(f"❌ Erreur de publication : {e.code} - {e.read().decode('utf-8')}")
        return False

if __name__ == "__main__":
    post_texte = recuperer_post_du_jour()
    if post_texte:
        print("Envoi vers LinkedIn en cours...")
        publier_sur_linkedin(post_texte)
    else:
        print("Fin du script : rien à publier.")
