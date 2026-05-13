import csv
import urllib.request
import json
import os

URL_GOOGLE_SHEET = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTjZqY4aO78EPuGJO-B7RZR8Q0TG1toSa21ff_S-P4xBxlEgF19E5QD9HAfMdkspXU7cv6_Ayh9wc3T/pub?output=csv"
ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
AUTHOR_URN = os.environ.get("LINKEDIN_AUTHOR_URN")

def recuperer_post_du_jour():
    try:
        req = urllib.request.Request(URL_GOOGLE_SHEET)
        with urllib.request.urlopen(req) as response:
            lignes = [l.decode('utf-8') for l in response.readlines()]
            
        lecteur = list(csv.DictReader(lignes))
        
        # On cible explicitement "Jour 1"
        jour_cible = "Jour 1" 
        
        for ligne in lecteur:
            # On regarde si la cellule de la colonne "Jour" correspond
            if ligne.get('Jour') == jour_cible:
                # On récupère les colonnes exactes du tableau bilingue
                contenu = ligne.get('Contenu du Post (EN / FR)')
                mots_cles = ligne.get('Mots-clés')
                
                # Sécurité au cas où les colonnes aient un nom légèrement différent
                if not contenu:
                    print("⚠️ Colonne 'Contenu du Post (EN / FR)' introuvable.")
                    print(f"Colonnes disponibles : {list(ligne.keys())}")
                    return None
                    
                texte_complet = f"{contenu}\n\n{mots_cles}"
                return texte_complet
                
        print(f"❌ Impossible de trouver la ligne pour : {jour_cible}")
        if lecteur:
             print(f"Colonnes détectées dans votre fichier : {list(lecteur[0].keys())}")
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
        print(f"❌ Erreur de publication sur LinkedIn : {e.code} - {e.read().decode('utf-8')}")
        return False

if __name__ == "__main__":
    post_texte = recuperer_post_du_jour()
    if post_texte:
        print("Envoi vers LinkedIn en cours...")
        publier_sur_linkedin(post_texte)
    else:
        print("Fin du script : rien à publier.")
