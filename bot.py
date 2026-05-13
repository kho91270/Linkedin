import csv
import urllib.request
import json
import os
from datetime import datetime

# --- CONFIGURATION ---
URL_GOOGLE_SHEET = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTjZqY4aO78EPuGJO-B7RZR8Q0TG1toSa21ff_S-P4xBxlEgF19E5QD9HAfMdkspXU7cv6_Ayh9wc3T/pub?output=csv"

# Récupération sécurisée depuis les GitHub Secrets
ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
AUTHOR_URN = os.environ.get("LINKEDIN_AUTHOR_URN")

def recuperer_post_du_jour():
    try:
        req = urllib.request.Request(URL_GOOGLE_SHEET)
        with urllib.request.urlopen(req) as response:
            lignes = [l.decode('utf-8') for l in response.readlines()]
            
        lecteur = list(csv.DictReader(lignes))
        
        # Logique pour trouver le post du jour
        # Pour le test initial, on peut cibler spécifiquement le premier jour
        jour_cible = "Day 1" 
        
        for ligne in lecteur:
            if ligne.get('Day') == jour_cible:
                texte_complet = f"{ligne.get('Post Content')}\n\n{ligne.get('Keywords')}"
                return texte_complet
                
        print("❌ Aucun post trouvé pour aujourd'hui.")
        return None

    except Exception as e:
        print(f"Erreur de lecture du Google Sheet : {e}")
        return None

def publier_sur_linkedin(contenu_texte):
    if not ACCESS_TOKEN or not AUTHOR_URN:
        print("❌ Erreur : Les clés d'API (Secrets) sont introuvables.")
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
            print("✅ Publication réussie sur la page MBK Procurement !")
            return True
    except urllib.error.HTTPError as e:
        print(f"❌ Erreur de publication : {e.code} - {e.read().decode('utf-8')}")
        return False

if __name__ == "__main__":
    post_texte = recuperer_post_du_jour()
    if post_texte:
        print("Envoi vers LinkedIn en cours...")
        publier_sur_linkedin(post_texte)
