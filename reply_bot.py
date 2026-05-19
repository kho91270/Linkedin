import requests
import json
import os
import sys
import time

# ============================================================
# REPLY BOT v2.0 - Repond aux commentaires LinkedIn
# IA : Groq (GRATUIT) - Modele Llama 3.3 70B
# Ton : Professionnel + touche d'humour (Option A)
# ============================================================

LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
LINKEDIN_PERSON_ID = None

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
# RECUPERER LES POSTS RECENTS
# ============================================================
def get_my_recent_posts():
    url = f"https://api.linkedin.com/v2/ugcPosts?q=authors&authors=List(urn%3Ali%3Aperson%3A{LINKEDIN_PERSON_ID})&sortBy=LAST_MODIFIED&count=10"
    headers = {"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"}
    
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        url2 = f"https://api.linkedin.com/rest/posts?author=urn%3Ali%3Aperson%3A{LINKEDIN_PERSON_ID}&q=author&count=10&sortBy=LAST_MODIFIED"
        headers2 = {
            "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
            "LinkedIn-Version": "202401",
            "X-Restli-Protocol-Version": "2.0.0"
        }
        resp = requests.get(url2, headers=headers2)
        if resp.status_code != 200:
            print(f"  [!] Erreur recup posts: {resp.status_code}")
            return []
