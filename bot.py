BOT.PY - Publication Manager Bilingue (FR + EN) avec Validation Email
Utilise GROQ, Google Credentials pour Gmail, Leonardo pour images.
Genere 2 posts (FR + EN) pour chaque publication.
Commandes: generate | approve | publish | force
"""

import os
import sys
import json
import smtplib
import requests
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from groq import Groq
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
LEONARDO_API_KEY = os.environ.get("LEONARDO_API_KEY")
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS")
SMTP_EMAIL = os.environ.get("SMTP_EMAIL")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL")
LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_PERSON_ID = os.environ.get("LINKEDIN_PERSON_ID")

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

    prompt_fr = f"""Tu es Mehdi, Category Manager en procurement chez un grand groupe.
Positionnement LinkedIn: "Praticien terrain + Analyste procuretech".

PILIER: {pillar.upper()}
INSTRUCTIONS: {pillar_instructions.get(pillar, pillar_instructions['terrain'])}

{brief_context}

REGLES:
- Ecris en FRANCAIS
- Premiere personne (je)
- Hook percutant < 150 chars en premiere ligne
- Structure: Hook -> Vecu -> Insight -> Question ouverte
- Longueur: 800-1500 chars (texte), 300-600 (question), 200-400 (insight)
- Termine par une question ouverte
- 3-5 hashtags a la fin sur une ligne separee
- Max 3 emojis
- Ton direct, pas de bullshit corporate
- Sauts de ligne pour aerer
- Phrases courtes

Ecris UNIQUEMENT le post LinkedIn en francais. Rien d'autre."""

    prompt_en = f"""You are Mehdi, a Category Manager in procurement at a large corporation.
LinkedIn positioning: "Field practitioner + Procuretech analyst".

PILLAR: {pillar.upper()}
INSTRUCTIONS: {pillar_instructions.get(pillar, pillar_instructions['terrain'])}

{brief_context}

RULES:
- Write in ENGLISH
- First person (I)
- Punchy hook < 150 chars on the first line
- Structure: Hook -> Experience -> Insight -> Open question
- Length: 800-1500 chars (text), 300-600 (question), 200-400 (insight)
- End with an open question
- 3-5 hashtags at the end on a separate line
- Max 3 emojis
- Direct tone, no corporate BS
- Line breaks for readability
- Short sentences
- This is NOT a translation of a French post. Write a NATIVE English post with the same theme but adapted for an international procurement audience.

Write ONLY the LinkedIn post in English. Nothing else."""

    try:
        response_fr = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt_fr}],
            temperature=0.8,
            max_tokens=1500,
        )
        content_fr = response_fr.choices[0].message.content.strip()

        response_en = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt_en}],
            temperature=0.8,
            max_tokens=1500,
        )
        content_en = response_en.choices[0].message.content.strip()

        post = {
            "content_fr": content_fr,
            "content_en": content_en,
            "pillar": pillar,
            "format": format_map.get(pillar, "texte"),
            "generated_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "status": "pending_approval",
            "lang": "both",
        }

        # Quality check
        if evaluate_post:
            quality_report = evaluate_post(post)
            post["quality_report"] = quality_report
            if not quality_report.get("passed"):
                print("[WARN] Quality check failed, regenerating...")
                response_fr = client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[{"role": "user", "content": prompt_fr + "\n\nIMPORTANT: Le post precedent etait trop faible. Fais MIEUX. Hook plus percutant, structure plus claire."}],
                    temperature=0.9,
                    max_tokens=1500,
                )
                post["content_fr"] = response_fr.choices[0].message.content.strip()
                response_en = client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[{"role": "user", "content": prompt_en + "\n\nIMPORTANT: The previous post was too weak. Do BETTER. Punchier hook, clearer structure."}],
                    temperature=0.9,
                    max_tokens=1500,
                )
                post["content_en"] = response_en.choices[0].message.content.strip()

        # Generate image
        if generate_post_image:
            image_result = generate_post_image(post)
            post["image"] = image_result

        return post
    except Exception as e:
        print(f"[ERROR] Groq: {e}")
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
    # Check any approved post
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
    subject = f"[LinkedIn] 2 posts a valider pour le {publish_date} ({post['pillar'].upper()})"

    quality_text = ""
    if post.get("quality_report"):
        qr = post["quality_report"]
        score_fr = qr.get("score_fr", {}).get("total", "?")
        score_en = qr.get("score_en", {}).get("total", "?")
        quality_text = f"\nScore qualite: FR={score_fr}/100 | EN={score_en}/100"
        if qr.get("hooks_fr"):
            quality_text += f"\n\nHOOKS ALTERNATIFS FR:"
            quality_text += f"\n  A: {qr['hooks_fr'].get('hook_a', '')}"
            quality_text += f"\n  B: {qr['hooks_fr'].get('hook_b', '')}"
        if qr.get("hooks_en"):
            quality_text += f"\n\nHOOKS ALTERNATIFS EN:"
            quality_text += f"\n  A: {qr['hooks_en'].get('hook_a', '')}"
            quality_text += f"\n  B: {qr['hooks_en'].get('hook_b', '')}"

    html_body = f"""<html><body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;">
<div style="background:#1B2A4A;color:white;padding:20px;border-radius:8px 8px 0 0;">
<h2 style="margin:0;">2 Posts LinkedIn a valider (FR + EN)</h2>
<p style="margin:5px 0 0 0;opacity:0.8;">Publication prevue: <strong>{publish_date}</strong> | Pilier: <strong>{post['pillar'].upper()}</strong></p></div>
<div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 8px 8px;">
<h3 style="color:#2E86AB;">VERSION FRANCAISE</h3>
<div style="background:#f8f9fa;border-left:4px solid #2E86AB;padding:15px;margin:15px 0;white-space:pre-wrap;font-size:14px;line-height:1.6;">{post['content_fr']}</div>
<h3 style="color:#E8871E;">ENGLISH VERSION</h3>
<div style="background:#f8f9fa;border-left:4px solid #E8871E;padding:15px;margin:15px 0;white-space:pre-wrap;font-size:14px;line-height:1.6;">{post['content_en']}</div>
<hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
<p style="font-size:14px;color:#666;">
<strong>Approuver les 2:</strong> Reponds OK<br>
<strong>Approuver FR seulement:</strong> Reponds OK FR<br>
<strong>Approuver EN seulement:</strong> Reponds OK EN<br>
<strong>Hook A (FR):</strong> Reponds HOOK A FR<br>
<strong>Hook B (EN):</strong> Reponds HOOK B EN<br>
<strong>Modifier:</strong> Reponds avec tes corrections<br>
<strong>Refuser:</strong> Reponds SKIP</p>
</div></body></html>"""

    text_body = f"""2 POSTS LINKEDIN A VALIDER
Publication: {publish_date} | Pilier: {post['pillar'].upper()}
{quality_text}

{'='*40}
VERSION FRANCAISE
{'='*40}
{post['content_fr']}

{'='*40}
ENGLISH VERSION
{'='*40}
{post['content_en']}

{'='*40}
Reponds:
- OK = approuver les 2
- OK FR = approuver seulement le francais
- OK EN = approuver seulement l'anglais
- HOOK A FR / HOOK B FR = utiliser le hook alternatif
- SKIP = refuser
- Ou tes corrections
"""
    return send_email(NOTIFY_EMAIL, subject, html_body, text_body)


def publish_to_linkedin(content, image_url=None):
    if not LINKEDIN_ACCESS_TOKEN or not LINKEDIN_PERSON_ID:
        print("[SIMULATE] Publication simulee:")
        print(f"  {content[:150]}...")
        return {"status": "simulated", "id": "sim_" + datetime.now().strftime("%Y%m%d%H%M%S")}
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
            print(f"[OK] Publie! ID: {result.get('id')}")
            return {"status": "published", "id": result.get("id")}
        else:
            print(f"[ERROR] LinkedIn {response.status_code}: {response.text}")
            return {"status": "error", "code": response.status_code}
    except Exception as e:
        print(f"[ERROR] Publication: {e}")
        return {"status": "error", "message": str(e)}


def archive_post(post, result_fr, result_en):
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
        "linkedin_response_fr": result_fr,
        "linkedin_response_en": result_en,
        "lang": post.get("lang_approved", "both"),
        "image": post.get("image"),
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)
    print(f"[OK] Archive: {filepath}")


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
        print("[SKIP] Pas de publication prevue")
        return
    publish_date = tomorrow.strftime("%Y-%m-%d")
    print(f"[INFO] Publication: {publish_date} | Pilier: {pillar}")
    post = generate_post_content(pillar)
    if not post:
        print("[ERROR] Echec generation")
        return
    print(f"[OK] Posts generes FR ({len(post['content_fr'])} chars) + EN ({len(post['content_en'])} chars)")
    save_pending_post(post, publish_date)
    send_approval_email(post, publish_date)


def cmd_publish():
    print(f"[CMD] publish -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    post, filepath = check_approval()
    if not post:
        print("[SKIP] Aucun post approuve")
        return
    tracker = load_tracker()
    today = datetime.now().strftime("%Y-%m-%d")
    if tracker.get("last_post_date") == today:
        print("[SKIP] Deja publie aujourd'hui")
        return
    lang_approved = post.get("lang_approved", "both")
    result_fr = None
    result_en = None
    if lang_approved in ["both", "fr"] and post.get("content_fr"):
        print("[PUBLISH] Version francaise...")
        result_fr = publish_to_linkedin(post["content_fr"])
    if lang_approved in ["both", "en"] and post.get("content_en"):
        print("[PUBLISH] Version anglaise...")
        result_en = publish_to_linkedin(post["content_en"])
    published = False
    if result_fr and result_fr.get("status") in ["published", "simulated"]:
        published = True
    if result_en and result_en.get("status") in ["published", "simulated"]:
        published = True
    if published:
        archive_post(post, result_fr, result_en)
        tracker = update_tracker(tracker, post)
        save_tracker(tracker)
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        print(f"[STATS] Total: {tracker['total_posts']} | Semaine: {tracker['posts_this_week']}/{tracker['target_per_week']}")


def cmd_force():
    today = datetime.now().strftime("%Y-%m-%d")
    # Move any pending to approved
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
