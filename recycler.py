RECYCLER.PY - Content Rotator Intelligent Bilingue
Identifie les posts recyclables, transforme en FR+EN.
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
            return True
        except Exception:
            pass
    if SMTP_EMAIL and SMTP_PASSWORD:
        try:
            msg = MIMEText(body_text, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = SMTP_EMAIL
            msg["To"] = to_email
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(SMTP_EMAIL, SMTP_PASSWORD)
                server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
            return True
        except Exception:
            pass
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
        content = post.get("content_fr") or post.get("content") or ""
        if len(content) < 100:
            continue
        post["_filename"] = fn
        post["_days_since"] = days_since
        recyclable.append(post)
    return recyclable


def recycle_post(post):
    original_content = post.get("content_fr") or post.get("content", "")
    pillar = post.get("pillar", "terrain")
    original_format = post.get("format", "texte")
    new_format = random.choice(FORMAT_TRANSFORMS.get(original_format, ["texte"]))

    strategies = {
        "terrain": [
            "Meme histoire, focus sur UNE lecon differente",
            "Transformer en conseil actionnable (framework)",
            "Prendre le contre-pied: ce qui aurait pu mal tourner",
        ],
        "analyste": [
            "Update avec nouvelles infos",
            "Comparer avec un concurrent",
            "Retour apres X mois: prediction verifiee ?",
        ],
        "conversation": [
            "Reformuler avec nouveau contexte",
            "Prendre position: donner MA reponse",
        ],
        "insight": [
            "Developper en post terrain complet",
            "Transformer en carrousel avec exemples",
        ],
    }

    strategy = random.choice(strategies.get(pillar, strategies["terrain"]))

    prompt_fr = f"""Tu es Mehdi, Category Manager en procurement.
Recycle cet ancien post avec un NOUVEL ANGLE completement different.

POST ORIGINAL (publie il y a {post.get('_days_since', 90)} jours):
---
{original_content}
---

STRATEGIE: "{strategy}"
FORMAT: {new_format}

REGLES:
- Ecris en FRANCAIS
- TRES DIFFERENT de l'original
- Meme theme, NOUVEL angle
- Premiere personne, ton direct
- Le lecteur ne doit PAS reconnaitre un recyclage
- 800-1500 chars, hook < 150 chars
- 3-5 hashtags a la fin

Ecris UNIQUEMENT le nouveau post en francais."""

    prompt_en = f"""You are Mehdi, a Category Manager in procurement.
Recycle this old post with a COMPLETELY NEW ANGLE.

ORIGINAL POST (published {post.get('_days_since', 90)} days ago):
---
{original_content}
---

STRATEGY: "{strategy}"
FORMAT: {new_format}

RULES:
- Write in ENGLISH
- VERY DIFFERENT from the original
- Same theme, NEW angle
- First person, direct tone
- The reader must NOT recognize a recycled post
- 800-1500 chars, hook < 150 chars
- 3-5 hashtags at the end
- NATIVE English, NOT a translation

Write ONLY the new LinkedIn post in English."""

    try:
        response_fr = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt_fr}],
            temperature=0.85,
            max_tokens=1500,
        )
        response_en = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt_en}],
            temperature=0.85,
            max_tokens=1500,
        )
        return {
            "content_fr": response_fr.choices[0].message.content.strip(),
            "content_en": response_en.choices[0].message.content.strip(),
            "pillar": pillar,
            "format": new_format,
            "status": "pending_approval",
            "source": "recycled",
            "lang": "both",
            "original_filename": post.get("_filename", ""),
            "recycle_strategy": strategy,
            "generated_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    except Exception as e:
        print(f"[ERROR] Groq recyclage: {e}")
        return None


def main():
    print(f"[START] Recycler -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    recyclable = find_recyclable_posts()
    print(f"       -> {len(recyclable)} posts recyclables")
    if not recyclable:
        print("[DONE] Aucun post a recycler.")
        return
    recycled_log = load_recycled_log()
    for post in recyclable[:2]:
        recycled_post = recycle_post(post)
        if not recycled_post:
            continue
        os.makedirs(PENDING_DIR, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"pending_{date_str}_recycled_{recycled_post['pillar']}.json"
        with open(os.path.join(PENDING_DIR, filename), "w", encoding="utf-8") as f:
            json.dump(recycled_post, f, ensure_ascii=False, indent=2)
        if NOTIFY_EMAIL:
            body = f"""POST RECYCLE A VALIDER (FR + EN)
Pilier: {recycled_post['pillar']} | Strategie: {recycled_post['recycle_strategy']}

{'='*40}
VERSION FRANCAISE
{'='*40}
{recycled_post['content_fr']}

{'='*40}
ENGLISH VERSION
{'='*40}
{recycled_post['content_en']}

---
Reponds OK / OK FR / OK EN / SKIP"""
            send_email_notification(NOTIFY_EMAIL, f"[LinkedIn Recycle] Post bilingue ({recycled_post['pillar'].upper()})", body)
        recycled_log["recycled"].append({
            "date": date_str,
            "original_filename": post.get("_filename", ""),
            "new_format": recycled_post["format"],
            "strategy": recycled_post["recycle_strategy"],
        })
    save_recycled_log(recycled_log)
    print("[DONE]")


if __name__ == "__main__":
    main()
