
"""
RECYCLER.PY - Content Rotator Intelligent
Utilise GROQ. Identifie les posts recyclables, transforme, envoie pour validation.
"""

import os
import json
import random
import smtplib
import base64
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from groq import Groq
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS")
SMTP_EMAIL = os.environ.get("SMTP_EMAIL")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL")

client = Groq(api_key=GROQ_API_KEY)
GROQ_MODEL = "llama-3.3-70b-versatile"

PUBLISHED_DIR = "published_posts"
PENDING_DIR = "pending_approval"
RECYCLED_LOG = "recycled_log.json"

RECYCLE_DELAYS = {"terrain": 90, "analyste": 60, "conversation": 45, "insight": 45}
FORMAT_TRANSFORMS = {
    "texte": ["carrousel", "question", "insight"],
    "carrousel": ["texte", "insight"],
    "question": ["texte", "carrousel"],
    "insight": ["texte", "carrousel"],
}


def send_email_notification(to_email, subject, body_text):
    if GOOGLE_CREDENTIALS:
        try:
            creds_data = json.loads(GOOGLE_CREDENTIALS)
            creds = Credentials.from_authorized_user_info(creds_data)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            service = build("gmail", "v1", credentials=creds)
            msg = MIMEText(body_text, "plain", "utf-8")
            msg["To"] = to_email
            msg["Subject"] = subject
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            service.users().messages().send(userId="me", body={"raw": raw}).execute()
            print("[OK] Email envoye (Gmail API)")
            return True
        except Exception as e:
            print(f"[WARN] Gmail API: {e}")
    if SMTP_EMAIL and SMTP_PASSWORD:
        try:
            msg = MIMEText(body_text, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = SMTP_EMAIL
            msg["To"] = to_email
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(SMTP_EMAIL, SMTP_PASSWORD)
                server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
            print("[OK] Email envoye (SMTP)")
            return True
        except Exception as e:
            print(f"[ERROR] SMTP: {e}")
    return False


def load_recycled_log():
    if os.path.exists(RECYCLED_LOG):
        with open(RECYCLED_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"recycled": [], "blacklist": []}


def save_recycled_log(log):
    with open(RECYCLED_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def find_recyclable_posts():
    recycled_log = load_recycled_log()
    recyclable = []
    if not os.path.exists(PUBLISHED_DIR):
        return []
    for fn in os.listdir(PUBLISHED_DIR):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(PUBLISHED_DIR, fn), "r", encoding="utf-8") as f:
            post = json.load(f)
        pub_date = post.get("published_date")
        if not pub_date:
            continue
        try:
            days_since = (datetime.now() - datetime.strptime(pub_date, "%Y-%m-%d")).days
        except ValueError:
            continue
        pillar = post.get("pillar", "terrain")
        min_delay = RECYCLE_DELAYS.get(pillar, 90)
        if days_since < min_delay:
            continue
        already = any(r.get("original_filename") == fn for r in recycled_log.get("recycled", []))
        if already or fn in recycled_log.get("blacklist", []):
            continue
        if not post.get("content") or len(post.get("content", "")) < 100:
            continue
        post["_filename"] = fn
        post["_days_since"] = days_since
        recyclable.append(post)
    return recyclable


def recycle_post(post):
    original_content = post.get("content", "")
    pillar = post.get("pillar", "terrain")
    original_format = post.get("format", "texte")
    new_format = random.choice(FORMAT_TRANSFORMS.get(original_format, ["texte"]))

    strategies = {
        "terrain": [
            "Meme histoire, focus sur UNE lecon differente",
            "Transformer en conseil actionnable (framework)",
            "Prendre le contre-pied: ce qui aurait pu mal tourner",
            "Generaliser: de mon cas a un principe universel",
        ],
        "analyste": [
            "Update avec nouvelles infos (levee, pivot)",
            "Comparer avec un concurrent",
            "Retour apres X mois: prediction verifiee ?",
            "Elargir a un trend plus large",
        ],
        "conversation": [
            "Reformuler avec nouveau contexte",
            "Synthese des meilleures reponses",
            "Prendre position: donner MA reponse",
        ],
        "insight": [
            "Developper en post terrain complet",
            "Transformer en carrousel avec exemples",
            "Illustrer avec un cas reel recent",
        ],
    }

    strategy = random.choice(strategies.get(pillar, strategies["terrain"]))

    format_instructions = {
        "texte": "Post texte (800-1500 chars). Hook < 150 chars -> Vecu -> Insight -> Question. 3-5 hashtags.",
        "carrousel": "SLIDE 1: [hook] / SLIDE 2: [probleme] / SLIDE 3-6: [points] / SLIDE 7: [CTA].",
        "question": "Post court (300-600 chars). Contexte + Question ouverte. 3-5 hashtags.",
        "insight": "Post tres court (200-400 chars). 1 contexte + 1 lecon + 1 question. 3-5 hashtags.",
    }

    prompt = f"""Tu es Mehdi, Category Manager en procurement.
Recycle cet ancien post avec un NOUVEL ANGLE completement different.

POST ORIGINAL (publie il y a {post.get('_days_since', 90)} jours):
---
{original_content}
---

STRATEGIE: "{strategy}"
FORMAT: {new_format}
INSTRUCTIONS: {format_instructions.get(new_format, format_instructions['texte'])}

REGLES:
- TRES DIFFERENT de l'original
- Meme theme, NOUVEL angle
- Premiere personne, ton direct
- Le lecteur ne doit PAS reconnaitre un recyclage
- Accroche < 150 chars

Ecris UNIQUEMENT le nouveau post."""

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85,
            max_tokens=1500,
        )
        return {
            "content": response.choices[0].message.content.strip(),
            "pillar": pillar,
            "format": new_format,
            "status": "pending_approval",
            "source": "recycled",
            "original_filename": post.get("_filename", ""),
            "recycle_strategy": strategy,
            "generated_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    except Exception as e:
        print(f"[ERROR] Groq recyclage: {e}")
        return None


def main():
    print(f"[START] Recycler -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    print("\n[1/3] Recherche des posts recyclables...")
    recyclable = find_recyclable_posts()
    print(f"       -> {len(recyclable)} posts recyclables")

    if not recyclable:
        print("[DONE] Aucun post a recycler.")
        return

    print("\n[2/3] Recyclage...")
    recycled_log = load_recycled_log()
    recycled_count = 0

    for post in recyclable[:2]:
        print(f"\n  --- {post.get('_filename', '?')} ({post.get('_days_since')}j)")
        recycled_post = recycle_post(post)
        if not recycled_post:
            print("      [FAIL]")
            continue

        os.makedirs(PENDING_DIR, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"pending_{date_str}_recycled_{recycled_post['pillar']}.json"
        with open(os.path.join(PENDING_DIR, filename), "w", encoding="utf-8") as f:
            json.dump(recycled_post, f, ensure_ascii=False, indent=2)

        if NOTIFY_EMAIL:
            body = f"""POST RECYCLE A VALIDER
Pilier: {recycled_post['pillar']} | Format: {recycled_post['format']}
Strategie: {recycled_post['recycle_strategy']}

--- NOUVEAU POST ---
{recycled_post['content']}

--- ORIGINAL (comparaison) ---
{post.get('content', '')[:400]}

---
Reponds OK / SKIP / ou tes corrections."""
            send_email_notification(NOTIFY_EMAIL, f"[LinkedIn Recycle] Post a valider ({recycled_post['pillar'].upper()})", body)

        recycled_log["recycled"].append({
            "date": date_str,
            "original_filename": post.get("_filename", ""),
            "new_format": recycled_post["format"],
            "strategy": recycled_post["recycle_strategy"],
        })
        recycled_count += 1
        print(f"      [OK] -> {recycled_post['format']}")

    save_recycled_log(recycled_log)
    print(f"\n[3/3] Resume: {recycled_count} recycles")
    print("[DONE]")


if __name__ == "__main__":
    main()

