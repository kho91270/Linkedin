
"""
ENGAGEMENT.PY — Strategic Engagement Manager
Gère l'engagement ciblé sur les comptes clés procurement.
Pas de spam : monitoring intelligent + alertes + suggestions de commentaires.
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

client = OpenAI(api_key=OPENAI_API_KEY)

# Fichiers de données
KEY_ACCOUNTS_FILE = "key_accounts.json"
INTERACTIONS_LOG = "interactions_log.json"
COMMENT_DRAFTS_DIR = "comment_drafts"

# ============================================================
# COMPTES CLÉS
# ============================================================
DEFAULT_KEY_ACCOUNTS = [
    # Fondateurs Procuretech
    {"name": "Sudhir Bhojwani", "company": "Oro Labs", "category": "founder_procuretech", "linkedin_url": ""},
    {"name": "Russ Woolley", "company": "Flowie", "category": "founder_procuretech", "linkedin_url": ""},
    {"name": "CEO Zapro", "company": "Zapro", "category": "founder_procuretech", "linkedin_url": ""},
    {"name": "CEO Tamarin AI", "company": "Tamarin AI", "category": "founder_procuretech", "linkedin_url": ""},
    {"name": "CEO Pavus", "company": "Pavus", "category": "founder_procuretech", "linkedin_url": ""},
    {"name": "Kevin Frechette", "company": "Fairmarkit", "category": "founder_procuretech", "linkedin_url": ""},
    # Analystes
    {"name": "Jason Busch", "company": "Spend Matters", "category": "analyst", "linkedin_url": ""},
    {"name": "Pierre Mitchell", "company": "Spend Matters", "category": "analyst", "linkedin_url": ""},
    {"name": "Bertrand Gabriel", "company": "Procurement Leaders", "category": "analyst", "linkedin_url": ""},
    # Leaders Achats
    {"name": "Hélène Duval", "company": "CPO CAC40", "category": "cpo_leader", "linkedin_url": ""},
    # Pairs / Communauté
    {"name": "Procurement community", "company": "Various", "category": "peer", "linkedin_url": ""},
]


def load_key_accounts():
    """Charge la liste des comptes clés."""
    if os.path.exists(KEY_ACCOUNTS_FILE):
        with open(KEY_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # Créer le fichier avec les défauts
    save_key_accounts(DEFAULT_KEY_ACCOUNTS)
    return DEFAULT_KEY_ACCOUNTS


def save_key_accounts(accounts):
    """Sauvegarde les comptes clés."""
    with open(KEY_ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)


# ============================================================
# LOG DES INTERACTIONS
# ============================================================
def load_interactions_log():
    """Charge le log des interactions."""
    if os.path.exists(INTERACTIONS_LOG):
        with open(INTERACTIONS_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"interactions": [], "stats": {}}


def save_interactions_log(log):
    """Sauvegarde le log."""
    with open(INTERACTIONS_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def log_interaction(log, account_name, interaction_type, post_topic, comment_draft=""):
    """Enregistre une interaction."""
    interaction = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "account": account_name,
        "type": interaction_type,  # "comment", "like", "share", "reply_received"
        "topic": post_topic,
        "comment_draft": comment_draft,
        "status": "drafted",  # drafted, sent, replied
    }
    log["interactions"].append(interaction)

    # Mettre à jour les stats
    if account_name not in log["stats"]:
        log["stats"][account_name] = {"total_interactions": 0, "replies_received": 0, "last_interaction": None}
    log["stats"][account_name]["total_interactions"] += 1
    log["stats"][account_name]["last_interaction"] = datetime.now().strftime("%Y-%m-%d")

    return log


# ============================================================
# GÉNÉRATION DE COMMENTAIRES INTELLIGENTS
# ============================================================
def generate_smart_comment(post_content, post_author, author_category):
    """Génère un commentaire pertinent et personnel pour un post."""
    category_context = {
        "founder_procuretech": "Tu commentes le post d'un fondateur de startup procuretech. Montre que tu es un utilisateur/testeur potentiel. Pose une question terrain.",
        "analyst": "Tu commentes le post d'un analyste marché. Apporte un point de vue praticien qui complète son analyse.",
        "cpo_leader": "Tu commentes le post d'un CPO/directeur achats. Partage une expérience complémentaire ou une question stratégique.",
        "peer": "Tu commentes le post d'un pair en procurement. Sois collégial, partage un retour terrain.",
    }

    context = category_context.get(author_category, "Tu commentes un post LinkedIn sur le procurement.")

    prompt = f"""Tu es Mehdi, Category Manager en procurement. Tu veux commenter intelligemment ce post LinkedIn.

AUTEUR: {post_author}
CONTEXTE: {context}

CONTENU DU POST:
{post_content[:1000]}

RÈGLES POUR TON COMMENTAIRE:
- Maximum 3-4 phrases
- Apporte de la VALEUR (pas juste "super post!")
- Soit: une expérience complémentaire, une question pertinente, ou un point de vue terrain
- Ton naturel, pas sycophante
- Première personne
- Pas de hashtags dans les commentaires
- Pas d'emojis excessifs (max 1)

Génère 2 options de commentaire (option A et option B).
Format:
OPTION A: [commentaire]
OPTION B: [commentaire]"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=500,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ERROR] Génération commentaire: {e}")
        return None


# ============================================================
# MONITORING DES POSTS CLÉS
# ============================================================
def check_key_accounts_activity():
    """
    Vérifie l'activité récente des comptes clés.
    Note: LinkedIn API officielle est limitée. En production, 
    utiliser des outils comme Phantombuster, ou scraper via des proxys.
    Ici on simule la logique.
    """
    accounts = load_key_accounts()
    activity_report = []

    print(f"[INFO] Monitoring de {len(accounts)} comptes clés...")

    # En production: appel API LinkedIn ou outil tiers
    # Simulation de la structure attendue
    for account in accounts:
        # Placeholder pour l'activité récupérée
        activity = {
            "account": account["name"],
            "company": account["company"],
            "category": account["category"],
            "recent_posts": [],  # En prod: liste des posts récents
            "needs_engagement": False,
        }
        activity_report.append(activity)

    return activity_report


def identify_engagement_opportunities(activity_report):
    """Identifie les opportunités d'engagement prioritaires."""
    log = load_interactions_log()
    opportunities = []

    for activity in activity_report:
        account_name = activity["account"]
        stats = log["stats"].get(account_name, {})
        last_interaction = stats.get("last_interaction")

        # Ne pas sur-engager : max 1 interaction par compte par semaine
        if last_interaction:
            last_date = datetime.strptime(last_interaction, "%Y-%m-%d")
            if (datetime.now() - last_date).days < 7:
                continue

        # Prioriser par catégorie
        priority_order = {
            "founder_procuretech": 1,
            "analyst": 2,
            "cpo_leader": 3,
            "peer": 4,
        }

        if activity.get("recent_posts"):
            opportunity = {
                "account": account_name,
                "category": activity["category"],
                "priority": priority_order.get(activity["category"], 5),
                "posts": activity["recent_posts"],
            }
            opportunities.append(opportunity)

    # Trier par priorité
    opportunities.sort(key=lambda x: x["priority"])
    return opportunities[:5]  # Top 5 opportunités


# ============================================================
# ENGAGEMENT DASHBOARD
# ============================================================
def generate_engagement_report():
    """Génère un rapport d'engagement hebdomadaire."""
    log = load_interactions_log()
    accounts = load_key_accounts()

    report = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "period": "last_7_days",
        "total_accounts_monitored": len(accounts),
        "interactions_this_week": 0,
        "replies_received": 0,
        "accounts_engaged": [],
        "accounts_to_engage": [],
        "top_performing_comments": [],
    }

    # Compter les interactions de la semaine
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    for interaction in log.get("interactions", []):
        if interaction.get("date", "")[:10] >= week_ago:
            report["interactions_this_week"] += 1
            if interaction.get("status") == "replied":
                report["replies_received"] += 1

    # Identifier les comptes non engagés cette semaine
    for account in accounts:
        stats = log["stats"].get(account["name"], {})
        last = stats.get("last_interaction")
        if not last or last < week_ago:
            report["accounts_to_engage"].append({
                "name": account["name"],
                "company": account["company"],
                "category": account["category"],
                "days_since_last": (datetime.now() - datetime.strptime(last, "%Y-%m-%d")).days if last else 999,
            })

    return report


# ============================================================
# MAIN
# ============================================================
def main():
    print(f"[START] Engagement Manager — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Charger les données
    accounts = load_key_accounts()
    log = load_interactions_log()

    print(f"[INFO] {len(accounts)} comptes clés configurés")

    # Monitoring activité
    print("[1/3] Monitoring des comptes clés...")
    activity = check_key_accounts_activity()

    # Identifier les opportunités
    print("[2/3] Identification des opportunités...")
    opportunities = identify_engagement_opportunities(activity)

    if opportunities:
        print(f"[INFO] {len(opportunities)} opportunités d'engagement trouvées")

        # Générer des drafts de commentaires
        os.makedirs(COMMENT_DRAFTS_DIR, exist_ok=True)
        drafts = []

        for opp in opportunities:
            for post in opp.get("posts", []):
                draft = generate_smart_comment(
                    post_content=post.get("content", ""),
                    post_author=opp["account"],
                    author_category=opp["category"],
                )
                if draft:
                    drafts.append({
                        "account": opp["account"],
                        "category": opp["category"],
                        "post_preview": post.get("content", "")[:100],
                        "comment_options": draft,
                    })
                    # Logger l'interaction (comme draft)
                    log = log_interaction(
                        log, opp["account"], "comment",
                        post.get("content", "")[:50], draft
                    )

        # Sauvegarder les drafts
        drafts_file = os.path.join(
            COMMENT_DRAFTS_DIR,
            f"drafts_{datetime.now().strftime('%Y-%m-%d')}.json"
        )
        with open(drafts_file, "w", encoding="utf-8") as f:
            json.dump(drafts, f, ensure_ascii=False, indent=2)
        print(f"[OK] {len(drafts)} drafts sauvegardés: {drafts_file}")
    else:
        print("[INFO] Aucune opportunité cette fois-ci")

    # Rapport
    print("[3/3] Génération du rapport d'engagement...")
    report = generate_engagement_report()
    print(f"\n📊 RAPPORT ENGAGEMENT:")
    print(f"   Interactions cette semaine: {report['interactions_this_week']}")
    print(f"   Comptes à engager: {len(report['accounts_to_engage'])}")
    for acc in report["accounts_to_engage"][:5]:
        print(f"   → {acc['name']} ({acc['company']}) — {acc['days_since_last']}j sans interaction")

    # Sauvegarder
    save_interactions_log(log)
    print("\n[DONE] Engagement Manager terminé.")


if __name__ == "__main__":
    main()

