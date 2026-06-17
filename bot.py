
"""
BOT.PY — Publication Manager avec Validation Email
1. Genere le contenu automatiquement a partir du brief de veille
2. Envoie un email de validation la veille de la publication
3. Attend l'approbation (via fichier approval)
4. Publie sur LinkedIn une fois approuve
"""

import os
import json
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from openai import OpenAI

# ============================================================
# CONFIGURATION
# ============================================================
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_PERSON_ID = os.environ.get("LINKEDIN_PERSON_ID")

# Email (Gmail SMTP)
SMTP_EMAIL = os.environ.get("SMTP_EMAIL")  # ton email gmail
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")  # app password gmail
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL")  # email ou recevoir la validation

client = OpenAI(api_key=OPENAI_API_KEY)

# Fichiers
QUEUE_FILE = "content_queue.json"
TRACKER_FILE = "tracker.json"
PUBLISHED_DIR = "published_posts"
BRIEF_DIR = "veille_briefs"
PENDING_DIR = "pending_approval"
APPROVED_DIR = "approved_posts"

# Calendrier
PILLAR_SCHEDULE = {
    "even": {"Tuesday": "terrain", "Thursday": "analyste", "Saturday": "conversation"},
    "odd": {"Tuesday": "analyste", "Thursday": "terrain", "Saturday": "insight"},
}

HASHTAGS = {
    "terrain": "#Procurement #Achats #CategoryManagement #SupplyChain #Negociation",
    "analyste": "#Procuretech #AIprocurement #InnovationAchats #StartupTech #DigitalProcurement",
    "conversation": "#Procurement #Achats #Debat #CommunauteAchats",
    "insight": "#Procurement #LeconDuJour #Achats #Leadership",
}


# ============================================================
# TRACKER
# ============================================================
def load_tracker():
    default = {
        "total_posts": 0, "current_streak": 0, "last_post_date": None,
        "last_pillar": None, "next_pillar": "terrain", "queue_size": 0,
        "posts_this_week": 0, "target_per_week": 3,
        "week_start": datetime.now().strftime("%Y-%m-%d"), "history": [],
    }
    if os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE, "r", encoding="utf-8") as f:
            tracker = json.load(f)
            for k, v in default.items():
                if k not in tracker:
                    tracker[k] = v
            return tracker
    return default


def save_tracker(tracker):
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(tracker, f, ensure_ascii=False, indent=2)


def update_tracker(tracker, post):
    today = datetime.now().strftime("%Y-%m-%d")
    tracker["total_posts"] += 1
    tracker["last_post_date"] = today
    tracker["last_pillar"] = post.get("pillar", "terrain")
    tracker["posts_this_week"] += 1

    week_start = tracker.get("week_start", today)
    if datetime.strptime(week_start, "%Y-%m-%d").isocalendar()[1] != datetime.now().isocalendar()[1]:
        tracker["posts_this_week"] = 1
        tracker["week_start"] = today

    tracker["history"].append({
        "date": today, "pillar": post.get("pillar"), "format": post.get("format"),
    })
    tracker["history"] = tracker["history"][-100:]
    return tracker


# ============================================================
# PILIER DU JOUR
# ============================================================
def determine_pillar(target_date=None):
    """Determine le pilier pour une date donnee."""
    if target_date is None:
        target_date = datetime.now()
    day_name = target_date.strftime("%A")
    week_num = target_date.isocalendar()[1]
    week_type = "even" if week_num % 2 == 0 else "odd"
    schedule = PILLAR_SCHEDULE.get(week_type, {})
    return schedule.get(day_name, None)


# ============================================================
# GENERATION AUTOMATIQUE DU CONTENU
# ============================================================
def generate_post_content(pillar, brief=None):
    """Genere un post LinkedIn complet a partir du brief et du pilier."""

    # Charger le brief du jour si pas fourni
    if brief is None:
        today = datetime.now().strftime("%Y-%m-%d")
        brief_file = os.path.join(BRIEF_DIR, f"brief_{today}.json")
        if not os.path.exists(brief_file):
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            brief_file = os.path.join(BRIEF_DIR, f"brief_{yesterday}.json")
        if os.path.exists(brief_file):
            with open(brief_file, "r", encoding="utf-8") as f:
                brief = json.load(f)

    # Construire le contexte pour la generation
    brief_context = ""
    if brief and brief.get("status") not in ["NO_NEWS", "ERROR"]:
        brief_context = f"""
INFORMATIONS DU BRIEF DE VEILLE:
- Funding: {json.dumps(brief.get('funding_alert'), ensure_ascii=False)}
- Stat cle: {json.dumps(brief.get('key_stat'), ensure_ascii=False)}
- Nouvel outil: {json.dumps(brief.get('new_tool'), ensure_ascii=False)}
- Sujet chaud: {json.dumps(brief.get('hot_topic'), ensure_ascii=False)}
- Angles suggeres: {json.dumps(brief.get('post_angles'), ensure_ascii=False)}
"""

    # Instructions selon le pilier
    pillar_instructions = {
        "terrain": """Tu ecris un post TERRAIN: partage une experience personnelle reelle de Category Manager.
Sujets possibles: evaluation fournisseur, negociation, scorecard, gestion stakeholders, RFI/RFP, 
relation fournisseur, digitalisation process, erreurs commises, lecons apprises.
Le post doit sembler 100% vecu. Utilise des chiffres credibles et des details concrets.""",
        "analyste": """Tu ecris un post ANALYSTE PROCURETECH: analyse une startup, un outil, une tendance du marche.
Utilise les infos du brief de veille. Donne ton AVIS personnel de praticien (pas juste du reportage).
Compare avec ton experience terrain. Sois critique et nuance.""",
        "conversation": """Tu ecris un post CONVERSATION: pose une question ouverte qui genere du debat.
La question doit etre polarisante ou faire reflechir. Commence par un mini-contexte personnel.""",
        "insight": """Tu ecris un post INSIGHT: une lecon courte et percutante.
1 phrase de contexte + 1 insight fort + 1 question. Tres court (200-400 chars).""",
    }

    format_map = {
        "terrain": "texte",
        "analyste": "texte",
        "conversation": "question",
        "insight": "insight",
    }

    prompt = f"""Tu es Mehdi, Category Manager en procurement chez un grand groupe.
Tu publies sur LinkedIn avec le positionnement "Praticien terrain + Analyste procuretech".

{pillar_instructions.get(pillar, pillar_instructions['terrain'])}

{brief_context}

REGLES STRICTES:
- Premiere personne (je)
- Structure HVIA: Hook (1 ligne choc < 150 chars) -> Vecu (3-5 lignes) -> Insight (la lecon) -> Appel (question ouverte)
- Longueur: 800-1500 caracteres pour texte, 300-600 pour question, 200-400 pour insight
- Accroche premiere ligne: percutante, fait arreter le scroll
- Termine TOUJOURS par une question ouverte
- 3-5 hashtags pertinents a la fin (une ligne separee)
- Max 3 emojis dans tout le post
- Ton direct, pas de bullshit corporate, pas de "dans un monde ou..."
- Sauts de ligne pour aerer
- Phrases courtes

Ecris UNIQUEMENT le post LinkedIn. Rien d'autre."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=1500,
        )
        content = response.choices[0].message.content.strip()
        return {
            "content": content,
            "pillar": pillar,
            "format": format_map.get(pillar, "texte"),
            "generated_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "status": "pending_approval",
        }
    except Exception as e:
        print(f"[ERROR] Generation: {e}")
        return None


# ============================================================
# EMAIL DE VALIDATION
# ============================================================
def send_approval_email(post, publish_date):
    """Envoie un email avec le post pour validation."""
    if not SMTP_EMAIL or not SMTP_PASSWORD or not NOTIFY_EMAIL:
        print("[WARN] Email non configure -- sauvegarde locale uniquement")
        return False

    subject = f"[LinkedIn] Post a valider pour le {publish_date} ({post['pillar'].upper()})"

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #1B2A4A; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
            <h2 style="margin: 0;">Post LinkedIn a valider</h2>
            <p style="margin: 5px 0 0 0; opacity: 0.8;">Publication prevue: <strong>{publish_date}</strong></p>
        </div>
        
        <div style="border: 1px solid #ddd; border-top: none; padding: 20px; border-radius: 0 0 8px 8px;">
            <table style="width: 100%; margin-bottom: 15px;">
                <tr>
                    <td><strong>Pilier:</strong> {post['pillar'].upper()}</td>
                    <td><strong>Format:</strong> {post.get('format', 'texte')}</td>
                </tr>
            </table>
            
            <div style="background: #f8f9fa; border-left: 4px solid #2E86AB; padding: 15px; margin: 15px 0; white-space: pre-wrap; font-size: 14px; line-height: 1.6;">
{post['content']}
            </div>
            
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
            
            <p style="font-size: 14px; color: #666;">
                <strong>Pour approuver :</strong> Reponds "OK" ou "APPROVE" a cet email.<br>
                <strong>Pour modifier :</strong> Reponds avec tes corrections.<br>
                <strong>Pour refuser :</strong> Reponds "SKIP" ou "REFUSE".
            </p>
            
            <p style="font-size: 12px; color: #999; margin-top: 20px;">
                Genere automatiquement le {datetime.now().strftime('%Y-%m-%d a %H:%M')} | 
                Mehdi LinkedIn Bot
            </p>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_EMAIL
    msg["To"] = NOTIFY_EMAIL

    # Version texte
    text_body = f"""POST LINKEDIN A VALIDER
Publication prevue: {publish_date}
Pilier: {post['pillar'].upper()} | Format: {post.get('format', 'texte')}

--- CONTENU DU POST ---

{post['content']}

--- FIN DU POST ---

Pour approuver: reponds OK ou APPROVE
Pour modifier: reponds avec tes corrections
Pour refuser: reponds SKIP ou REFUSE
"""

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, NOTIFY_EMAIL, msg.as_string())
        print(f"[OK] Email de validation envoye a {NOTIFY_EMAIL}")
        return True
    except Exception as e:
        print(f"[ERROR] Envoi email: {e}")
        return False


# ============================================================
# GESTION DES APPROBATIONS
# ============================================================
def save_pending_post(post, publish_date):
    """Sauvegarde le post en attente d'approbation."""
    os.makedirs(PENDING_DIR, exist_ok=True)
    filename = f"pending_{publish_date}_{post['pillar']}.json"
    filepath = os.path.join(PENDING_DIR, filename)

    post["publish_date"] = publish_date
    post["approval_status"] = "pending"
    post["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(post, f, ensure_ascii=False, indent=2)

    print(f"[OK] Post en attente: {filepath}")
    return filepath


def check_approval():
    """Verifie s'il y a un post approuve a publier aujourd'hui."""
    os.makedirs(APPROVED_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")

    # Chercher dans approved/
    for filename in os.listdir(APPROVED_DIR):
        if filename.endswith(".json") and today in filename:
            filepath = os.path.join(APPROVED_DIR, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                post = json.load(f)
            if post.get("approval_status") == "approved":
                return post, filepath
    return None, None


def approve_post(publish_date):
    """Approuve un post en attente (appele manuellement ou via webhook)."""
    os.makedirs(APPROVED_DIR, exist_ok=True)

    # Chercher le post pending pour cette date
    if not os.path.exists(PENDING_DIR):
        print("[ERROR] Aucun post en attente")
        return False

    for filename in os.listdir(PENDING_DIR):
        if publish_date in filename and filename.endswith(".json"):
            filepath = os.path.join(PENDING_DIR, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                post = json.load(f)

            post["approval_status"] = "approved"
            post["approved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

            # Deplacer vers approved/
            approved_path = os.path.join(APPROVED_DIR, filename.replace("pending_", "approved_"))
            with open(approved_path, "w", encoding="utf-8") as f:
                json.dump(post, f, ensure_ascii=False, indent=2)

            # Supprimer le pending
            os.remove(filepath)
            print(f"[OK] Post approuve: {approved_path}")
            return True

    print(f"[ERROR] Aucun post pending pour {publish_date}")
    return False


# ============================================================
# PUBLICATION LINKEDIN
# ============================================================
def publish_to_linkedin(post):
    """Publie sur LinkedIn."""
    if not LINKEDIN_ACCESS_TOKEN or not LINKEDIN_PERSON_ID:
        print("[SIMULATE] Publication simulee:")
        print(f"  Pilier: {post.get('pillar')}")
        print(f"  Contenu: {post.get('content', '')[:150]}...")
        return {"status": "simulated", "id": "sim_" + datetime.now().strftime("%Y%m%d%H%M")}

    url = "https://api.linkedin.com/v2/ugcPosts"
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    payload = {
        "author": f"urn:li:person:{LINKEDIN_PERSON_ID}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": post["content"]},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 201:
            result = response.json()
            print(f"[OK] Publie! ID: {result.get('id', 'N/A')}")
            return {"status": "published", "id": result.get("id")}
        else:
            print(f"[ERROR] LinkedIn {response.status_code}: {response.text}")
            return {"status": "error", "code": response.status_code}
    except Exception as e:
        print(f"[ERROR] Publication: {e}")
        return {"status": "error", "message": str(e)}


def archive_post(post, result):
    """Archive le post publie."""
    os.makedirs(PUBLISHED_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"post_{today}_{post.get('pillar', 'unknown')}.json"
    filepath = os.path.join(PUBLISHED_DIR, filename)

    archive = {
        "published_date": today,
        "published_time": datetime.now().strftime("%H:%M"),
        "pillar": post.get("pillar"),
        "format": post.get("format"),
        "content": post.get("content"),
        "linkedin_response": result,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)
    print(f"[OK] Archive: {filepath}")


# ============================================================
# COMMANDES PRINCIPALES
# ============================================================
def cmd_generate():
    """Commande: genere le post du lendemain et envoie l'email de validation."""
    print(f"[CMD] generate -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Determiner le prochain jour de publication
    tomorrow = datetime.now() + timedelta(days=1)
    pillar = determine_pillar(tomorrow)

    # Si demain n'est pas un jour de publication, chercher le prochain
    if not pillar:
        for delta in range(2, 5):
            future = datetime.now() + timedelta(days=delta)
            pillar = determine_pillar(future)
            if pillar:
                tomorrow = future
                break

    if not pillar:
        print("[SKIP] Pas de publication prevue dans les prochains jours")
        return

    publish_date = tomorrow.strftime("%Y-%m-%d")
    print(f"[INFO] Publication prevue: {publish_date} | Pilier: {pillar}")

    # Generer le contenu
    print("[GENERATE] Creation du post...")
    post = generate_post_content(pillar)
    if not post:
        print("[ERROR] Echec de generation")
        return

    print(f"[OK] Post genere ({len(post['content'])} chars)")
    print(f"--- PREVIEW ---\n{post['content'][:300]}...\n--- FIN ---")

    # Sauvegarder en pending
    save_pending_post(post, publish_date)

    # Envoyer l'email de validation
    email_sent = send_approval_email(post, publish_date)
    if not email_sent:
        print("[INFO] Email non envoye -- approuve manuellement via: python bot.py approve")


def cmd_approve():
    """Commande: approuve le post du jour."""
    today = datetime.now().strftime("%Y-%m-%d")
    # Essayer aujourd'hui et demain
    for date in [today, (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")]:
        if approve_post(date):
            return
    print("[INFO] Aucun post a approuver trouve")


def cmd_publish():
    """Commande: publie le post approuve du jour."""
    print(f"[CMD] publish -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Verifier s'il y a un post approuve
    post, filepath = check_approval()
    if not post:
        print("[SKIP] Aucun post approuve pour aujourd'hui")
        return

    # Verifier qu'on n'a pas deja publie aujourd'hui
    tracker = load_tracker()
    today = datetime.now().strftime("%Y-%m-%d")
    if tracker.get("last_post_date") == today:
        print("[SKIP] Deja publie aujourd'hui")
        return

    print(f"[PUBLISH] Post approuve trouve: {post.get('pillar')} / {post.get('format')}")

    # Publier
    result = publish_to_linkedin(post)

    if result.get("status") in ["published", "simulated"]:
        archive_post(post, result)
        tracker = update_tracker(tracker, post)
        save_tracker(tracker)

        # Nettoyer le fichier approved
        if filepath and os.path.exists(filepath):
            os.remove(filepath)

        print(f"[STATS] Total: {tracker['total_posts']} | Streak: {tracker['current_streak']} | Semaine: {tracker['posts_this_week']}/{tracker['target_per_week']}")
    else:
        print("[ERROR] Publication echouee")


def cmd_force_approve_and_publish():
    """Commande: approuve ET publie immediatement (bypass email)."""
    today = datetime.now().strftime("%Y-%m-%d")
    approve_post(today)
    cmd_publish()


# ============================================================
# MAIN
# ============================================================
def main():
    import sys
    command = sys.argv[1] if len(sys.argv) > 1 else "generate"

    commands = {
        "generate": cmd_generate,
        "approve": cmd_approve,
        "publish": cmd_publish,
        "force": cmd_force_approve_and_publish,
    }

    if command in commands:
        commands[command]()
    else:
        print(f"Usage: python bot.py [generate|approve|publish|force]")
        print(f"  generate  — Genere le post du lendemain + envoie email validation")
        print(f"  approve   — Approuve le post en attente")
        print(f"  publish   — Publie le post approuve du jour")
        print(f"  force     — Approuve + publie immediatement")


if __name__ == "__main__":
    main()

