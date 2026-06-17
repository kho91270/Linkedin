```python

"""
RECYCLER.PY — Content Rotator Intelligent
Identifie les posts recyclables, les transforme, et les soumet a validation.
"""

import os
import json
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from openai import OpenAI

# ============================================================
# CONFIGURATION
# ============================================================
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
SMTP_EMAIL = os.environ.get("SMTP_EMAIL")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL")

client = OpenAI(api_key=OPENAI_API_KEY)

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


# ============================================================
# CHARGEMENT
# ============================================================
def load_recycled_log():
    if os.path.exists(RECYCLED_LOG):
        with open(RECYCLED_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"recycled": [], "blacklist": []}


def save_recycled_log(log):
    with open(RECYCLED_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


# ============================================================
# IDENTIFICATION DES POSTS RECYCLABLES
# ============================================================
def find_recyclable_posts():
    """Trouve les posts prets a recycler."""
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


# ============================================================
# TRANSFORMATION
# ============================================================
def recycle_post(post):
    """Transforme un post avec un nouvel angle."""
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
            "Reformuler la question avec nouveau contexte",
            "Synthese des meilleures reponses",
            "Prendre position: donner MA reponse cette fois",
        ],
        "insight": [
            "Developper en post terrain complet",
            "Transformer en carrousel avec exemples",
            "Illustrer avec un cas reel recent",
        ],
    }

    strategy = random.choice(strategies.get(pillar, strategies["terrain"]))

    format_instructions = {
        "texte": "Post texte (800-1500 chars). Hook < 150 chars -> Vecu -> Insight -> Question ouverte. 3-5 hashtags.",
        "carrousel": "Format: SLIDE 1: [hook] / SLIDE 2: [probleme] / SLIDE 3-6: [points] / SLIDE 7: [CTA]. Court par slide.",
        "question": "Post court (300-600 chars). Contexte + Question ouverte engageante. 3-5 hashtags.",
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
- TRES DIFFERENT de l'original (pas une reformulation)
- Meme theme, NOUVEL angle
- Premiere personne, ton direct
- Le lecteur ne doit PAS reconnaitre un recyclage
- Accroche < 150 chars

Ecris UNIQUEMENT le nouveau post."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
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
        print(f"[ERROR] Recyclage: {e}")
        return None


# ============================================================
# EMAIL DE VALIDATION (recycle)
# ============================================================
def send_recycle_approval_email(recycled_post, original_post):
    """Envoie un email pour valider le post recycle."""
    if not SMTP_EMAIL or not SMTP_PASSWORD or not NOTIFY_EMAIL:
        print("[WARN] Email non configure")
        return False

    subject = f"[LinkedIn Recycle] Post a valider ({recycled_post['pillar'].upper()})"

    body = f"""POST RECYCLE A VALIDER
{'='*40}
Pilier: {recycled_post['pillar'].upper()} | Format: {recycled_post.get('format', 'texte')}
Strategie: {recycled_post.get('recycle_strategy', '?')}
Original publie il y a {original_post.get('_days_since', '?')} jours

--- NOUVEAU POST ---

{recycled_post['content']}

--- POST ORIGINAL (pour comparaison) ---

{original_post.get('content', '')[:500]}

--- FIN ---

Pour approuver: reponds OK ou APPROVE
Pour modifier: reponds avec tes corrections
Pour refuser: reponds SKIP ou REFUSE
"""

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = SMTP_EMAIL
    msg["To"] = NOTIFY_EMAIL

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, NOTIFY_EMAIL, msg.as_string())
        print(f"[OK] Email de validation recycle envoye")
        return True
    except Exception as e:
        print(f"[ERROR] Email: {e}")
        return False


# ============================================================
# SAUVEGARDE EN PENDING
# ============================================================
def save_as_pending(recycled_post):
    """Sauvegarde le post recycle en attente de validation."""
    os.makedirs(PENDING_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"pending_{date_str}_recycled_{recycled_post['pillar']}.json"
    filepath = os.path.join(PENDING_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(recycled_post, f, ensure_ascii=False, indent=2)

    print(f"[OK] Sauvegarde en pending: {filepath}")
    return filepath


# ============================================================
# MAIN
# ============================================================
def main():
    print(f"[START] Recycler -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Trouver les posts recyclables
    print("\n[1/3] Recherche des posts recyclables...")
    recyclable = find_recyclable_posts()
    print(f"       -> {len(recyclable)} posts recyclables trouves")

    if not recyclable:
        print("[DONE] Aucun post a recycler pour le moment.")
        return

    # Recycler max 2 posts
    print("\n[2/3] Recyclage...")
    recycled_log = load_recycled_log()
    recycled_count = 0
    max_recycle = 2

    for post in recyclable[:max_recycle]:
        print(f"\n  --- Recyclage: {post.get('_filename', '?')}")
        print(f"      Original: {post.get('pillar', '?')}/{post.get('format', '?')} | {post.get('_days_since', '?')}j")

        recycled_post = recycle_post(post)
        if not recycled_post:
            print(f"      [FAIL] Echec de recyclage")
            continue

        print(f"      [OK] Nouveau format: {recycled_post['format']}")
        print(f"      Preview: {recycled_post['content'][:100]}...")

        # Sauvegarder en pending
        save_as_pending(recycled_post)

        # Envoyer email de validation
        send_recycle_approval_email(recycled_post, post)

        # Logger
        recycled_log["recycled"].append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "original_filename": post.get("_filename", ""),
            "original_date": post.get("published_date", ""),
            "new_format": recycled_post["format"],
            "strategy": recycled_post.get("recycle_strategy", ""),
        })
        recycled_count += 1

    save_recycled_log(recycled_log)

    # Resume
    print(f"\n[3/3] Resume")
    print(f"       Recycles cette session: {recycled_count}")
    print(f"       Total historique: {len(recycled_log['recycled'])}")
    print(f"       Encore recyclables: {len(recyclable) - recycled_count}")
    print("[DONE] Recycler termine.")


if __name__ == "__main__":
    main()

