```python
"""
REPLY_BOT.PY — Smart Reply Assistant
Gère les réponses aux commentaires de manière intelligente.
Auto pour la courtoisie, drafts pour les questions, alerte pour les comptes clés.
"""

import os
import json
import random
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

# Configuration
AUTO_REPLY_DELAY_HOURS = 24
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

    # Questions ou commentaires substantiels
    question_indicators = ["?", "comment", "pourquoi", "est-ce que", "quelle",
                           "how", "what", "why", "which", "can you", "quel outil",
                           "tu recommandes", "tu utilises"]
    for indicator in question_indicators:
        if indicator in text_lower:
            return "draft_needed"

    # Commentaires longs = substantiels
    if len(text_lower) > 150:
        return "draft_needed"

    # Commentaires spam / irrelevant
    spam_patterns = ["check my profile", "dm me", "free course", "link in bio",
                     "visite mon profil", "message privé", "lien dans"]
    for pattern in spam_patterns:
        if pattern in text_lower:
            return "ignore"

    # Par défaut, courtoisie
    return "auto_thanks"


# ============================================================
# GÉNÉRATION DE RÉPONSES
# ============================================================
def generate_auto_thanks(commenter_name):
    """Génère une réponse de courtoisie variée."""
    first_name = commenter_name.split()[0] if commenter_name else ""

    templates = [
        f"Merci {first_name} ! 🙏",
        f"Merci pour ton retour {first_name} !",
        f"Merci {first_name}, content que ça résonne !",
        f"Merci {first_name} 🙏 N'hésite pas si tu as des questions !",
        f"Merci beaucoup {first_name} !",
        f"Ravi que ça t'ait parlé {first_name} !",
        f"Merci {first_name}, au plaisir d'échanger !",
        f"Merci {first_name} ! Si tu veux creuser le sujet, n'hésite pas.",
        f"Content que ça te parle {first_name} !",
        f"Merci {first_name} 🙏",
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
- Si c'est une question, donne une réponse concrète basée sur ton expérience terrain

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


def generate_priority_reply(comment_text, commenter_name, account_info, original_post_content):
    """Génère une réponse haute qualité pour un compte clé."""
    prompt = f"""Tu es Mehdi, Category Manager en procurement.
Un CONTACT IMPORTANT a commenté ton post. Tu dois répondre avec soin.

CONTEXTE DU CONTACT:
- Nom: {commenter_name}
- Entreprise: {account_info.get('company', 'N/A')}
- Catégorie: {account_info.get('category', 'N/A')}

TON POST ORIGINAL:
{original_post_content[:500]}

SON COMMENTAIRE:
{comment_text}

OBJECTIF: Créer une connexion, montrer ton expertise, ouvrir un dialogue.
RÈGLES:
- 3-5 phrases
- Mentionne un élément spécifique de son commentaire
- Pose une question de suivi si pertinent
- Ton respectueux mais pas sycophante
- Montre que tu connais son travail/entreprise
- Pas de hashtags, max 1 emoji

Génère 2 options:
OPTION A: [réponse qui enrichit le débat]
OPTION B: [réponse qui ouvre un dialogue / invite à échanger plus]"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ERROR] Génération réponse prioritaire: {e}")
        return None


# ============================================================
# RÉCUPÉRATION DES COMMENTAIRES LINKEDIN
# ============================================================
def fetch_recent_posts():
    """Récupère les posts récents publiés (depuis published_posts/)."""
    posts = []
    if not os.path.exists(PUBLISHED_DIR):
        return posts

    for filename in sorted(os.listdir(PUBLISHED_DIR), reverse=True)[:5]:
        if filename.endswith(".json"):
            filepath = os.path.join(PUBLISHED_DIR, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                post = json.load(f)
                posts.append(post)
    return posts


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
    params = {"count": 50, "start": 0}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
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
        print(f"[SIMULATE] Réponse → {reply_text[:80]}...")
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
            return {"status": "error", "code": response.status_code, "body": response.text}
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
    return {"replies_sent": [], "pending_drafts": [], "priority_alerts": [], "ignored": []}


def save_reply_log(log):
    """Sauvegarde le log."""
    with open(REPLY_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def is_already_replied(log, comment_id):
    """Vérifie si on a déjà répondu à ce commentaire."""
    replied_ids = [r.get("comment_id") for r in log.get("replies_sent", [])]
    draft_ids = [d.get("comment_id") for d in log.get("pending_drafts", [])]
    return comment_id in replied_ids or comment_id in draft_ids


# ============================================================
# PROCESSUS PRINCIPAL
# ============================================================
def process_comments_for_post(post, key_accounts, reply_log):
    """Traite tous les commentaires d'un post."""
    post_id = post.get("linkedin_response", {}).get("id")
    post_content = post.get("content", "")
    post_date = post.get("published_date", "")

    if not post_id:
        print(f"  [SKIP] Pas d'ID LinkedIn pour ce post")
        return reply_log

    # Vérifier que le post a plus de AUTO_REPLY_DELAY_HOURS heures
    # (ne pas répondre auto dans la première heure — réponses manuelles)
    if post_date:
        post_datetime = datetime.strptime(post_date, "%Y-%m-%d")
        hours_since = (datetime.now() - post_datetime).total_seconds() / 3600
        if hours_since < 1:
            print(f"  [SKIP] Post trop récent ({hours_since:.0f}h) — réponse manuelle recommandée")
            return reply_log

    # Récupérer les commentaires
    comments = fetch_post_comments(post_id)
    print(f"  → {len(comments)} commentaires trouvés")

    auto_count = 0
    for comment in comments:
        comment_id = comment.get("id", comment.get("$URN", ""))
        commenter = comment.get("actor", {})
        commenter_name = commenter.get("name", "Utilisateur")
        comment_text = comment.get("message", {}).get("text", "")

        # Skip si déjà traité
        if is_already_replied(reply_log, comment_id):
            continue

        # Classifier
        classification = classify_comment(comment_text, commenter_name, key_accounts)

        if classification == "ignore":
            reply_log["ignored"].append({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "comment_id": comment_id,
                "commenter": commenter_name,
                "reason": "spam/irrelevant",
            })
            continue

        elif classification == "auto_thanks":
            # Limite de réponses auto par post
            if auto_count >= MAX_AUTO_REPLIES_PER_POST:
                continue

            # Ne répondre auto qu'après le délai
            if hours_since < AUTO_REPLY_DELAY_HOURS:
                continue

            reply_text = generate_auto_thanks(commenter_name)
            result = reply_to_comment(post_id, comment_id, reply_text)

            reply_log["replies_sent"].append({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "comment_id": comment_id,
                "commenter": commenter_name,
                "type": "auto_thanks",
                "reply": reply_text,
                "status": result.get("status"),
            })
            auto_count += 1
            print(f"    ✅ Auto-reply → {commenter_name}: {reply_text[:50]}")

        elif classification == "draft_needed":
            # Générer un draft (pas d'envoi auto)
            draft = generate_smart_reply(comment_text, commenter_name, post_content)
            if draft:
                reply_log["pending_drafts"].append({
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "comment_id": comment_id,
                    "commenter": commenter_name,
                    "comment_text": comment_text,
                    "draft_options": draft,
                    "post_id": post_id,
                    "status": "pending_review",
                })
                print(f"    📝 Draft créé → {commenter_name}: {comment_text[:50]}...")

        elif classification == "priority_alert":
            # Compte clé: générer réponse premium + alerte
            account_info = next(
                (acc for acc in key_accounts if acc["name"].lower() in commenter_name.lower()),
                {}
            )
            draft = generate_priority_reply(comment_text, commenter_name, account_info, post_content)
            if draft:
                reply_log["priority_alerts"].append({
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "comment_id": comment_id,
                    "commenter": commenter_name,
                    "company": account_info.get("company", ""),
                    "category": account_info.get("category", ""),
                    "comment_text": comment_text,
                    "draft_options": draft,
                    "post_id": post_id,
                    "status": "URGENT_REVIEW",
                })
                print(f"    🔔 PRIORITÉ → {commenter_name} ({account_info.get('company', '')})")

    return reply_log


# ============================================================
# RAPPORT
# ============================================================
def print_reply_summary(reply_log):
    """Affiche un résumé des actions."""
    print("\n" + "=" * 50)
    print("📬 RÉSUMÉ DES RÉPONSES")
    print("=" * 50)
    print(f"  ✅ Auto-replies envoyées: {len(reply_log.get('replies_sent', []))}")
    print(f"  📝 Drafts en attente: {len(reply_log.get('pending_drafts', []))}")
    print(f"  🔔 Alertes prioritaires: {len(reply_log.get('priority_alerts', []))}")
    print(f"  🚫 Ignorés (spam): {len(reply_log.get('ignored', []))}")

    # Afficher les alertes prioritaires
    priority = reply_log.get("priority_alerts", [])
    if priority:
        print(f"\n  ⚠️  RÉPONSES PRIORITAIRES À ENVOYER MANUELLEMENT:")
        for alert in priority[-5:]:
            if alert.get("status") == "URGENT_REVIEW":
                print(f"     → {alert['commenter']} ({alert.get('company', '')})")
                print(f"       \"{alert['comment_text'][:80]}...\"")

    # Afficher les drafts en attente
    drafts = [d for d in reply_log.get("pending_drafts", []) if d.get("status") == "pending_review"]
    if drafts:
        print(f"\n  📝 DRAFTS À VALIDER ({len(drafts)}):")
        for draft in drafts[-5:]:
            print(f"     → {draft['commenter']}: \"{draft['comment_text'][:60]}...\"")

    print("=" * 50 + "\n")


# ============================================================
# MAIN
# ============================================================
def main():
    print(f"[START] Reply Bot — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Charger les données
    key_accounts = []
    if os.path.exists(KEY_ACCOUNTS_FILE):
        with open(KEY_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            key_accounts = json.load(f)

    reply_log = load_reply_log()

    # Récupérer les posts récents
    recent_posts = fetch_recent_posts()
    print(f"[INFO] {len(recent_posts)} posts récents à traiter")

    # Traiter les commentaires de chaque post
    for i, post in enumerate(recent_posts):
        post_date = post.get("published_date", "?")
        print(f"\n[{i+1}/{len(recent_posts)}] Post du {post_date} ({post.get('pillar', '?')})")
        reply_log = process_comments_for_post(post, key_accounts, reply_log)

    # Sauvegarder les drafts dans un fichier séparé pour review facile
    os.makedirs(REPLY_DRAFTS_DIR, exist_ok=True)
    pending = [d for d in reply_log.get("pending_drafts", []) if d.get("status") == "pending_review"]
    priority = [a for a in reply_log.get("priority_alerts", []) if a.get("status") == "URGENT_REVIEW"]

    if pending or priority:
        drafts_file = os.path.join(REPLY_DRAFTS_DIR, f"to_review_{datetime.now().strftime('%Y-%m-%d')}.json")
        with open(drafts_file, "w", encoding="utf-8") as f:
            json.dump({"priority": priority, "drafts": pending}, f, ensure_ascii=False, indent=2)
        print(f"\n[OK] Drafts sauvegardés pour review: {drafts_file}")

    # Résumé
    print_reply_summary(reply_log)

    # Sauvegarder
    save_reply_log(reply_log)
    print("[DONE] Reply Bot terminé.")


if __name__ == "__main__":
    main()
