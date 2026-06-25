"""
BOT.PY - Publication Manager Multi-Plateformes (LinkedIn + X) Bilingue (FR + EN) avec Validation Email
Utilise GROQ, Google Credentials pour Gmail, Leonardo pour images, Tweepy pour X.
Genere et publie des versions distinctes et adaptees pour chaque reseau social.
Commandes: generate | publish | force
"""

import os
import sys
import json
import smtplib
import requests
import base64
import tweepy
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from groq import Groq
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Secrets existants
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
LEONARDO_API_KEY = os.environ.get("LEONARDO_API_KEY")
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS")
SMTP_EMAIL = os.environ.get("SMTP_EMAIL")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL")
LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_PERSON_ID = os.environ.get("LINKEDIN_PERSON_ID")

# Nouveaux Secrets pour l'API X v2
X_API_KEY = os.environ.get("X_API_KEY")
X_API_KEY_SECRET = os.environ.get("X_API_KEY_SECRET")
X_ACCESS_TOKEN = os.environ.get("X_ACCESS_TOKEN")
X_ACCESS_TOKEN_SECRET = os.environ.get("X_ACCESS_TOKEN_SECRET")

client = Groq(api_key=GROQ_API_KEY)
GROQ_MODEL = "llama-3.3-70b-versatile"

QUEUE_FILE = "content_queue.json"
TRACKER_FILE = "tracker.json"
PUBLISHED_DIR = "published_posts"
BRIEF_DIR = "veille_briefs"
PENDING_DIR = "pending_approval"
APPROVED_DIR = "approved_posts"

try:
    from smart_scheduler import get_optimal_pillar_for_date
except ImportError:
    get_optimal_pillar_for_date = None

try:
    from quality_scorer import evaluate_post, format_quality_report, MIN_QUALITY_SCORE
except ImportError:
    evaluate_post = None

try:
    from image_generator import generate_post_image
except ImportError:
    generate_post_image = None


def get_gmail_service():
    if not GOOGLE_CREDENTIALS:
        return None
    try:
        creds_data = json.loads(GOOGLE_CREDENTIALS)
        creds = Credentials.from_authorized_user_info(creds_data)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build("gmail", "v1", credentials=creds)
    except Exception as e:
        print(f"[WARN] Gmail init: {e}")
        return None


def send_email(to_email, subject, html_body, text_body):
    service = get_gmail_service()
    if service:
        try:
            msg = MIMEMultipart("alternative")
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            service.users().messages().send(userId="me", body={"raw": raw}).execute()
            print("[OK] Email envoye via Gmail API")
            return True
        except Exception as e:
            print(f"[WARN] Gmail API: {e}")
    if SMTP_EMAIL and SMTP_PASSWORD:
        try:
            msg = MIMEText(text_body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = SMTP_EMAIL
            msg["To"] = to_email
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(SMTP_EMAIL, SMTP_PASSWORD)
                server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
            print("[OK] Email envoye via SMTP")
            return True
        except Exception as e:
            print(f"[ERROR] SMTP: {e}")
    return False


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
    tracker["history"].append({"date": today, "pillar": post.get("pillar"), "format": post.get("format"), "lang": post.get("lang", "both")})
    tracker["history"] = tracker["history"][-100:]
    return tracker


def determine_pillar(target_date=None):
    if target_date is None:
        target_date = datetime.now()
    if get_optimal_pillar_for_date:
        return get_optimal_pillar_for_date(target_date)
    day_name = target_date.strftime("%A")
    week_num = target_date.isocalendar()[1]
    pillar_schedule = {
        "even": {"Tuesday": "terrain", "Thursday": "analyste", "Saturday": "conversation"},
        "odd": {"Tuesday": "analyste", "Thursday": "terrain", "Saturday": "insight"},
    }
    week_type = "even" if week_num % 2 == 0 else "odd"
    return pillar_schedule.get(week_type, {}).get(day_name, None)


def generate_post_content(pillar, brief=None):
    if brief is None:
        today = datetime.now().strftime("%Y-%m-%d")
        brief_file = os.path.join(BRIEF_DIR, f"brief_{today}.json")
        if not os.path.exists(brief_file):
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            brief_file = os.path.join(BRIEF_DIR, f"brief_{yesterday}.json")
        if os.path.exists(brief_file):
            with open(brief_file, "r", encoding="utf-8") as f:
                brief = json.load(f)

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

    pillar_instructions = {
        "terrain": "Experience personnelle de Category Manager. Evaluation fournisseur, negociation, scorecard, RFI/RFP, erreurs, lecons. 100% vecu avec details concrets.",
        "analyste": "Analyse une startup procuretech, un outil, une tendance. Utilise le brief. Donne ton AVIS de praticien. Compare avec ton experience. Sois critique.",
        "conversation": "Question ouverte qui genere du debat. Polarisante. Mini-contexte personnel en intro.",
        "insight": "Lecon courte et percutante. 1 contexte + 1 insight + 1 question. 200-400 chars.",
    }

    format_map = {"terrain": "texte", "analyste": "texte", "conversation": "question", "insight": "insight"}

    # ---- PROMPTS LINKEDIN ----
    prompt_fr = f"""Tu es Mehdi, Category Manager en procurement chez un grand groupe.
Positionnement LinkedIn: "Praticien terrain + Analyste procuretech".
PILIER: {pillar.upper()}
INSTRUCTIONS: {pillar_instructions.get(pillar, pillar_instructions['terrain'])}
{brief_context}
REGLES:
- Ecris en FRANCAIS, premiere personne (je)
- Hook percutant < 150 chars en premiere ligne
- Structure: Hook -> Vecu -> Insight -> Question ouverte
- 3-5 hashtags a la fin sur une ligne separee, Max 3 emojis, sauts de ligne pour aerer
Ecris UNIQUEMENT le post LinkedIn en francais. Rien d'autre."""

    prompt_en = f"""You are Mehdi, a Category Manager in procurement at a large corporation.
LinkedIn positioning: "Field practitioner + Procuretech analyst".
PILLAR: {pillar.upper()}
INSTRUCTIONS: {pillar_instructions.get(pillar, pillar_instructions['terrain'])}
{brief_context}
RULES:
- Write in ENGLISH, first person (I)
- Punchy hook < 150 chars on the first line
- Structure: Hook -> Experience -> Insight -> Open question
- 3-5 hashtags at the end, Max 3 emojis, line breaks for readability
- NATIVE English adaptation, not a direct translation.
Write ONLY the LinkedIn post in English. Nothing else."""

    try:
        # Génération LinkedIn FR
        response_fr = client.chat.completions.create(
            model=GROQ_MODEL, messages=[{"role": "user", "content": prompt_fr}], temperature=0.8, max_tokens=1500
        )
        content_fr = response_fr.choices[0].message.content.strip()

        # Génération LinkedIn EN
        response_en = client.chat.completions.create(
            model=GROQ_MODEL, messages=[{"role": "user", "content": prompt_en}], temperature=0.8, max_tokens=1500
        )
        content_en = response_en.choices[0].message.content.strip()

        # ---- GENERATION SPECIFIQUE POUR X (FR + EN) ----
        print("[GENERATE] Generation des versions techniques specifiques pour X...")
        
        prompt_x_fr = f"""Basé sur ce sujet procurement/procuretech : '{pillar_instructions.get(pillar, "")}'.
Prends aussi en compte ce contexte : {brief_context}
Rédige un post pour X (Twitter) unique en FRANCAIS.
CONTRAINTES DE STYLE POUR X :
- Style radicalement different de LinkedIn : Pas d'intro corporate ("Bonjour le réseau"), pas d'emojis superflus.
- Sois tres direct, incisif et tres technique (oriente chiffres, processus rfi/rfp, architecture outils).
- Max 1 hashtag pertinent à la fin.
- CONTRAINTE ABSOLUE DE LONGUEUR : Maximum 260 caracteres (espaces compris).
Ecris UNIQUEMENT le post pour X en francais."""

        prompt_x_en = f"""Based on this procurement topic: '{pillar_instructions.get(pillar, "")}'.
Context framework: {brief_context}
Write a unique post for X (Twitter) in ENGLISH.
STYLE CONSTRAINTS FOR X:
- Radical difference from LinkedIn: No corporate fluff, no greetings, no corporate bs.
- Highly engineering/procurement-focused, data-driven, precise and direct tone.
- Max 1 hashtag.
- ABSOLUTE LENGTH CONSTRAINT: Maximum 260 characters (including spaces).
Write ONLY the post for X in English."""

        response_x_fr = client.chat.completions.create(
            model=GROQ_MODEL, messages=[{"role": "user", "content": prompt_x_fr}], temperature=0.7, max_tokens=300
        )
        content_x_fr = response_x_fr.choices[0].message.content.strip()

        response_x_en = client.chat.completions.create(
            model=GROQ_MODEL, messages=[{"role": "user", "content": prompt_x_en}], temperature=0.7, max_tokens=300
        )
        content_x_en = response_x_en.choices[0].message.content.strip()

        post = {
            "content_fr": content_fr,
            "content_en": content_en,
            "content_x_fr": content_x_fr,
            "content_x_en": content_x_en,
            "pillar": pillar,
            "format": format_map.get(pillar, "texte"),
            "generated_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "status": "pending_approval",
            "lang": "both",
        }

        # Quality check (LinkedIn uniquement)
        if evaluate_post:
            quality_report = evaluate_post(post)
            post["quality_report"] = quality_report
            if not quality_report.get("passed"):
                print("[WARN] Quality check failed, regenerating LinkedIn parts...")
                response_fr = client.chat.completions.create(
                    model=GROQ_MODEL, messages=[{"role": "user", "content": prompt_fr + "\n\nIMPORTANT: Fais MIEUX."}], temperature=0.9, max_tokens=1500
                )
                post["content_fr"] = response_fr.choices[0].message.content.strip()
                response_en = client.chat.completions.create(
                    model=GROQ_MODEL, messages=[{"role": "user", "content": prompt_en + "\n\nIMPORTANT: Do BETTER."}], temperature=0.9, max_tokens=1500
                )
                post["content_en"] = response_en.choices[0].message.content.strip()

        if generate_post_image:
            image_result = generate_post_image(post)
            post["image"] = image_result

        return post
    except Exception as e:
        print(f"[ERROR] Groq generation workflow: {e}")
        return None


def save_pending_post(post, publish_date):
    os.makedirs(PENDING_DIR, exist_ok=True)
    filename = f"pending_{publish_date}_{post['pillar']}.json"
    filepath = os.path.join(PENDING_DIR, filename)
    post["publish_date"] = publish_date
    post["approval_status"] = "pending"
    post["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(post, f, ensure_ascii=False, indent=2)
    print(f"[OK] Pending: {filepath}")
    return filepath


def check_approval():
    os.makedirs(APPROVED_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    for filename in os.listdir(APPROVED_DIR):
        if filename.endswith(".json") and today in filename:
            filepath = os.path.join(APPROVED_DIR, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                post = json.load(f)
            if post.get("approval_status") == "approved":
                return post, filepath
    for filename in sorted(os.listdir(APPROVED_DIR)):
        if filename.endswith(".json"):
            filepath = os.path.join(APPROVED_DIR, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                post = json.load(f)
            if post.get("approval_status") == "approved":
                return post, filepath
    return None, None


def send_approval_email(post, publish_date):
    if not NOTIFY_EMAIL:
        return False
    subject = f"[Multi-Post] Contenus a valider pour le {publish_date} ({post['pillar'].upper()})"

    quality_text = ""
    if post.get("quality_report"):
        qr = post["quality_report"]
        score_fr = qr.get("score_fr", {}).get("total", "?")
        score_en = qr.get("score_en", {}).get("total", "?")
        quality_text = f"\nScore qualite: FR={score_fr}/100 | EN={score_en}/100"

    html_body = f"""<html><body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;color:#333;">
<div style="background:#1B2A4A;color:white;padding:20px;border-radius:8px 8px 0 0;">
<h2 style="margin:0;">Publications Multi-Plateformes a valider (FR + EN)</h2>
<p style="margin:5px 0 0 0;opacity:0.8;">Prevu le: <strong>{publish_date}</strong> | Pilier: <strong>{post['pillar'].upper()}</strong></p></div>
<div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 8px 8px;">
<h2 style="color:#2E86AB;border-bottom:2px solid #2E86AB;padding-bottom:5px;">STRATEGIE FRANCAISE</h2>
<h3>LinkedIn</h3>
<div style="background:#f8f9fa;border-left:4px solid #2E86AB;padding:15px;margin:10px 0;white-space:pre-wrap;font-size:14px;">{post['content_fr']}</div>
<h3>X (Twitter) - Technique</h3>
<div style="background:#f1f3f5;border-left:4px solid #4A5568;padding:12px;margin:10px 0;white-space:pre-wrap;font-size:13px;font-family:monospace;">{post.get('content_x_fr', 'Non généré')}</div>

<h2 style="color:#E8871E;border-bottom:2px solid #E8871E;padding-bottom:5px;margin-top:30px;">ENGLISH STRATEGY</h2>
<h3>LinkedIn</h3>
<div style="background:#f8f9fa;border-left:4px solid #E8871E;padding:15px;margin:10px 0;white-space:pre-wrap;font-size:14px;">{post['content_en']}</div>
<h3>X (Twitter) - Technical</h3>
<div style="background:#f1f3f5;border-left:4px solid #4A5568;padding:12px;margin:10px 0;white-space:pre-wrap;font-size:13px;font-family:monospace;">{post.get('content_x_en', 'Not generated')}</div>

<hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
<p style="font-size:14px;color:#666;line-height:1.5;">
<strong>OK</strong> = Valider FR + EN (LinkedIn + X)<br>
<strong>OK FR</strong> = Valider Francais uniquement (LinkedIn + X)<br>
<strong>OK EN</strong> = Valider Anglais uniquement (LinkedIn + X)<br>
<strong>SKIP</strong> = Tout refuser et effacer</p>
</div></body></html>"""

    text_body = f"""PUBLICATIONS A VALIDER
Date: {publish_date} | Pilier: {post['pillar'].upper()}
{quality_text}

=== VERSION FRANCAISE ===
[LinkedIn]:\n{post['content_fr']}\n
[X (Twitter)]:\n{post.get('content_x_fr')}\n

=== ENGLISH VERSION ===
[LinkedIn]:\n{post['content_en']}\n
[X (Twitter)]:\n{post.get('content_x_en')}\n

Reponds: OK, OK FR, OK EN ou SKIP.
"""
    return send_email(NOTIFY_EMAIL, subject, html_body, text_body)


def publish_to_linkedin(content, image_url=None):
    if not LINKEDIN_ACCESS_TOKEN or not LINKEDIN_PERSON_ID:
        print("[SIMULATE] LinkedIn simule:")
        print(f"  {content[:100]}...")
        return {"status": "simulated", "id": "sim_ln_" + datetime.now().strftime("%Y%m%d%H%M%S")}
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
                "shareCommentary": {"text": content},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 201:
            result = response.json()
            print(f"[OK LinkedIn] Publie! ID: {result.get('id')}")
            return {"status": "published", "id": result.get("id")}
        else:
            print(f"[ERROR LinkedIn] {response.status_code}: {response.text}")
            return {"status": "error", "code": response.status_code}
    except Exception as e:
        print(f"[ERROR LinkedIn] Connecteur: {e}")
        return {"status": "error", "message": str(e)}


def publish_to_x(post_data):
    """Gere la publication sur X en FR et/ou EN selon l'e-mail d'approbation recu."""
    if not all([X_API_KEY, X_API_KEY_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET]):
        print("[SIMULATE] Secrets X manquants ou incomplets. Mode simulation actif.")
        print(f"  [X FR]: {post_data.get('content_x_fr', '')[:50]}...")
        print(f"  [X EN]: {post_data.get('content_x_en', '')[:50]}...")
        return {"status": "simulated"}

    lang_approved = post_data.get("lang_approved", "both")
    queue_x = []

    if lang_approved in ["both", "fr"] and post_data.get("content_x_fr"):
        queue_x.append(("Français", post_data["content_x_fr"]))
    if lang_approved in ["both", "en"] and post_data.get("content_x_en"):
        queue_x.append(("Anglais", post_data["content_x_en"]))

    if not queue_x:
        print("[INFO X] Aucun contenu X approuve pour cette langue.")
        return {"status": "skipped"}

    try:
        client_x = tweepy.Client(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_KEY_SECRET,
            access_token=X_ACCESS_TOKEN,
            access_token_secret=X_ACCESS_TOKEN_SECRET
        )
        
        responses = {}
        for lang_name, text in queue_x:
            text = text.strip()
            # Tronquage de securite strict pour l'API v2 (Plan Free)
            if len(text) > 280:
                print(f"[WARN X] Longueur excessive ({len(text)} car.) pour le post {lang_name}. Tronquage.")
                text = text[:277] + "..."
                
            response = client_x.create_tweet(text=text)
            print(f"[OK X] Post technique {lang_name} en ligne ! ID: {response.data['id']}")
            responses[lang_name] = {"status": "published", "id": response.data['id']}
        return responses
    except Exception as e:
        print(f"[ERROR X] Erreur lors de la publication sur X: {e}")
        return {"status": "error", "message": str(e)}


def archive_post(post, result_fr, result_en, result_x):
    os.makedirs(PUBLISHED_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"post_{today}_{post.get('pillar', 'unknown')}.json"
    filepath = os.path.join(PUBLISHED_DIR, filename)
    archive = {
        "published_date": today,
        "published_time": datetime.now().strftime("%H:%M"),
        "pillar": post.get("pillar"),
        "format": post.get("format"),
        "content_fr": post.get("content_fr"),
        "content_en": post.get("content_en"),
        "content_x_fr": post.get("content_x_fr"),
        "content_x_en": post.get("content_x_en"),
        "linkedin_response_fr": result_fr,
        "linkedin_response_en": result_en,
        "x_responses": result_x,
        "lang": post.get("lang_approved", "both"),
        "image": post.get("image"),
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)
    print(f"[OK] Archive globale enregistree: {filepath}")


def cmd_generate():
    print(f"[CMD] generate -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    tomorrow = datetime.now() + timedelta(days=1)
    pillar = determine_pillar(tomorrow)
    if not pillar:
        for delta in range(2, 5):
            future = datetime.now() + timedelta(days=delta)
            pillar = determine_pillar(future)
            if pillar:
                tomorrow = future
                break
    if not pillar:
        print("[SKIP] Pas de publication prevue dans le calendrier de piliers")
        return
    publish_date = tomorrow.strftime("%Y-%m-%d")
    print(f"[INFO] Planification: {publish_date} | Pilier: {pillar}")
    post = generate_post_content(pillar)
    if not post:
        print("[ERROR] Echec de generation de contenu")
        return
    print(f"[OK] Elements generes. LinkedIn FR/EN + X FR ({len(post.get('content_x_fr', ''))} c) / EN ({len(post.get('content_x_en', ''))} c)")
    save_pending_post(post, publish_date)
    send_approval_email(post, publish_date)


def cmd_publish():
    print(f"[CMD] publish -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    post, filepath = check_approval()
    if not post:
        print("[SKIP] Aucun post approuve dans le dossier approved_posts/")
        return
    tracker = load_tracker()
    today = datetime.now().strftime("%Y-%m-%d")
    if tracker.get("last_post_date") == today:
        print("[SKIP] Securite : Une publication a deja ete effectuee aujourd'hui")
        return
    
    lang_approved = post.get("lang_approved", "both")
    result_fr = None
    result_en = None
    
    # 1. Envois vers LinkedIn
    if lang_approved in ["both", "fr"] and post.get("content_fr"):
        print("[PUBLISH] Envoi de la version LinkedIn Francaise...")
        result_fr = publish_to_linkedin(post["content_fr"])
    if lang_approved in ["both", "en"] and post.get("content_en"):
        print("[PUBLISH] Envoi de la version LinkedIn Anglaise...")
        result_en = publish_to_linkedin(post["content_en"])
        
    # 2. Envois vers X (Multi-publication interne FR / EN gérée dans la fonction)
    print("[PUBLISH] Execution du module de publication sur X...")
    result_x = publish_to_x(post)

    published = False
    if result_fr and result_fr.get("status") in ["published", "simulated"]:
        published = True
    if result_en and result_en.get("status") in ["published", "simulated"]:
        published = True
    if result_x and any(res.get("status") in ["published", "simulated"] for res in result_x.values() if isinstance(res, dict)):
        published = True

    if published:
        archive_post(post, result_fr, result_en, result_x)
        tracker = update_tracker(tracker, post)
        save_tracker(tracker)
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        print(f"[STATS] Total: {tracker['total_posts']} | Semaine: {tracker['posts_this_week']}/{tracker['target_per_week']}")


def cmd_force():
    if os.path.exists(PENDING_DIR):
        os.makedirs(APPROVED_DIR, exist_ok=True)
        for fn in os.listdir(PENDING_DIR):
            if fn.endswith(".json"):
                src = os.path.join(PENDING_DIR, fn)
                with open(src, "r", encoding="utf-8") as f:
                    post = json.load(f)
                post["approval_status"] = "approved"
                post["lang_approved"] = "both"
                dst = os.path.join(APPROVED_DIR, fn.replace("pending_", "approved_"))
                with open(dst, "w", encoding="utf-8") as f:
                    json.dump(post, f, ensure_ascii=False, indent=2)
                os.remove(src)
                break
    cmd_publish()


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "generate"
    commands = {"generate": cmd_generate, "publish": cmd_publish, "force": cmd_force}
    if command in commands:
        commands[command]()
    else:
        print("Usage: python bot.py [generate|publish|force]")


if __name__ == "__main__":
    main()
