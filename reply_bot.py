
"""
REPLY_BOT.PY — Smart Reply Assistant
Gère les réponses aux commentaires de manière intelligente.
Auto pour la courtoisie, drafts pour les questions, alerte pour les comptes clés.
"""

import os
import json
import requests
from datetime import datetime, timedelta
from openai import OpenAI

# ============================================================
# CONFIGURATION
# ============================================================
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_PERSON_ID = os.environ.get("LINKEDIN_PERSON_ID")

client = OpenAI(api_key=OPENAI_API_KEY)

# Fichiers
KEY_ACCOUNTS_FILE = "key_accounts.json"
REPLY_LOG_FILE = "reply_log.json"
REPLY_DRAFTS_DIR = "reply_drafts"
PUBLISHED_DIR = "published_posts"

# Configuration des réponses
AUTO_REPLY_DELAY_HOURS = 24  # Répondre auto seulement après 24h
MAX_AUTO_REPLIES_PER_POST = 10


# ============================================================
# CLASSIFICATION DES COMMENTAIRES
# ============================================================
def classify_comment(comment_text, commenter_name, key_accounts):
    """
    Classifie un commentaire pour déterminer le type de réponse.
    Retourne: 'auto_thanks', 'draft_needed', 'priority_alert', 'ignore'
    """
    text_lower = comment_text.lower().strip()

    # Vérifier si c'est un compte clé
    is_key_account = any(
        acc["name"].lower() in commenter_name.lower()
        for acc in key_accounts
    )
    if is_key_account:
        return "priority_alert"

    # Commentaires de courtoisie simple (auto-réponse)
    courtesy_patterns = [
        "super post", "merci pour le partage", "très intéressant",
        "bravo", "top", "excellent", "bien dit", "je suis d'accord",
        "merci", "thanks", "great post", "well said", "totally agree",
        "100%", "tellement vrai", "pertinent", "j'adore", "inspirant",
        "👏", "🙏", "💯", "🔥", "👍",
    ]
    for pattern in courtesy_patterns:
        if pattern in text_lower and len(text_lower) < 100:
            return "auto_thanks"

    # Questions ou commentaires substantiels (draft nécessaire)
    question_indicators = ["?", "comment", "pourquoi", "est-ce que", "quelle",
                          "how", "what", "why", "which", "can you"]
    for indicator in question_indicators:
        if indicator in text_lower:
            return "draft_needed"

    # Commentaires longs = probablement substantiels
    if len(text_lower) > 150:
        return "draft_needed"

    # Par défaut, courtoisie
    return "auto_thanks"


# ============================================================
# GÉNÉRATION DE RÉPONSES
# ============================================================
def generate_auto_thanks(commenter_name):
    """Génère une réponse de courtoisie variée."""
    import random

    templates = [
        f"Merci {commenter_name} ! 🙏",
        f"Merci pour ton retour {commenter_name} !",
        f"Merci {commenter_name}, content que ça résonne !",
        f"Merci {commenter_name} 🙏 N'hésite pas si tu as des questions !",
        f"Merci beaucoup {commenter_name} !",
        f"Ravi que ça t'ait parlé {commenter_name} !",
        f"Merci {commenter_name}, au plaisir d'échanger !",
    ]
    return random.choice(templates)


def generate_smart_reply(comment_text, commenter_name, original_post_content):
    """Génère un draft de réponse intelligente pour les questions/débats."""
    prompt = f"""Tu es Mehdi, Category Manager en procurement. 
Quelqu'un a commenté ton post LinkedIn et tu dois répondre.

TON POST ORIGINAL (résumé):
{original_post_content[:500]}

COMMENTAIRE DE {commenter_name}:
{comment_text}

RÈGLES POUR TA RÉPONSE:
- 2-4 phrases max
- Réponds à la question ou enrichis le débat
- Apporte de la valeur (expérience, chiffre, nuance)
- Ton naturel et direct
- Première personne
- Pas de hashtags
- Max 1 emoji
- Si c'est une question, donne une réponse concrète basée sur ton expérience

Génère 2 options:
OPTION A: [réponse courte et directe]
OPTION B: [réponse plus détaillée avec exemple]"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=400,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ERROR] Génération réponse: {e}")
        return None


# ============================================================
# RÉCUPÉRATION DES COMMENTAIRES
# ============================================================
def fetch_post_comments(post_id):
    """Récupère les commentaires d'un post LinkedIn."""
    if not LINKEDIN_ACCESS_TOKEN:
        print("[SIMULATE] Mode simulation - pas de token LinkedIn")
        return []

    url = f"https://api.linkedin.com/v2/socialActions/{post_id}/comments"
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            return data.get("elements", [])
        else:
            print(f"[WARN] API comments {response.status_code}")
            return []
    except Exception as e:
        print(f"[ERROR] Fetch comments: {e}")
        return []


def reply_to_comment(post_id, comment_id, reply_text):
    """Poste une réponse à un commentaire."""
    if not LINKEDIN_ACCESS_TOKEN:
        print(f"[SIMULATE] Réponse: {reply_text[:80]}...")
        return {"status": "simulated"}

    url = f"https://api.linkedin.com/v2/socialActions/{post_id}/comments"
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    payload = {
        "actor": f"urn:li:person:{LINKEDIN_PERSON_ID}",
        "message": {"text": reply_text},
        "parentComment": comment_id,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        if response.status_code == 201:
            return {"status": "sent", "response": response.json()}
        else:
            return {"status": "error", "code": response.status_code}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================================
# LOG DES RÉPONSES
# ============================================================
def load_reply_log():
    """Charge le log des réponses."""
    if os.path.exists(REPLY_LOG_FILE):
        with open(REPLY_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"replies": [], "pending_drafts": [], "priority_alerts": []}


def save_reply_log(log):
    """Sauvegarde le log."""
    with open(REPLY_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f,
