"""
ENGAGEMENT_BOT.PY - Commentaires strategiques sur les posts du reseau cible
Augmente ta visibilite en commentant les posts des influenceurs procurement.
"""

import os
import json
import requests
from datetime import datetime
from groq import Groq

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_PERSON_ID = os.environ.get("LINKEDIN_PERSON_ID")

client = Groq(api_key=GROQ_API_KEY)
GROQ_MODEL = "llama-3.3-70b-versatile"

ENGAGEMENT_LOG = "engagement_log.json"

TARGET_HASHTAGS = [
    "procurement", "sourcing", "procuretech", "categorymanagement",
    "achats", "supplychain", "spendmanagement", "purchasingexcellence",
]


def load_engagement_log():
    if os.path.exists(ENGAGEMENT_LOG):
        with open(ENGAGEMENT_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"comments_posted": [], "last_run": None}


def save_engagement_log(log):
    with open(ENGAGEMENT_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def search_relevant_posts():
    if not LINKEDIN_ACCESS_TOKEN:
        print("[SIMULATE] Recherche de posts simulee")
        return []
    posts_found = []
    for hashtag in TARGET_HASHTAGS[:3]:
        url = f"https://api.linkedin.com/v2/search?q=hashtag&hashtag={hashtag}&count=5"
        headers = {
            "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
            "X-Restli-Protocol-Version": "2.0.0",
        }
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                elements = data.get("elements", [])
                for elem in elements:
                    posts_found.append({
                        "post_id": elem.get("id", ""),
                        "author": elem.get("actor", ""),
                        "content": elem.get("commentary", elem.get("text", ""))[:500],
                        "hashtag": hashtag,
                    })
        except Exception as e:
            print(f"[WARN] Search {hashtag}: {e}")
    return posts_found


def detect_language(text):
    french_words = ["je", "tu", "il", "elle", "nous", "les", "des", "une", "est", "pour", "dans", "avec"]
    text_lower = text.lower().split()
    french_count = sum(1 for w in text_lower if w in french_words)
    return "fr" if french_count >= 2 else "en"


def generate_strategic_comment(post_content, lang="en"):
    if lang == "fr":
        prompt = f"""Tu es Mehdi, Category Manager en procurement.
Tu veux commenter un post LinkedIn de maniere strategique pour augmenter ta visibilite.

POST:
{post_content[:400]}

Ecris un COMMENTAIRE strategique:
- Apporte de la valeur (pas juste "super post!")
- Partage une experience complementaire ou un point de vue
- 2-4 phrases
- Montre ton expertise sans etre pretentieux
- Ton naturel et collegial
- PAS de hashtags dans le commentaire

Ecris UNIQUEMENT le commentaire."""
    else:
        prompt = f"""You are Mehdi, a Category Manager in procurement.
You want to comment on a LinkedIn post strategically to increase your visibility.

POST:
{post_content[:400]}

Write a STRATEGIC COMMENT:
- Add value (not just "great post!")
- Share a complementary experience or point of view
- 2-4 sentences
- Show expertise without being pretentious
- Natural, collegial tone
- NO hashtags in the comment

Write ONLY the comment."""

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=250,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ERROR] Generate comment: {e}")
        return None


def post_comment(post_id, comment_text):
    if not LINKEDIN_ACCESS_TOKEN or not LINKEDIN_PERSON_ID:
        print(f"[SIMULATE] Comment: {comment_text[:80]}...")
        return {"status": "simulated"}
    url = f"https://api.linkedin.com/v2/socialActions/{post_id}/comments"
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    payload = {
        "actor": f"urn:li:person:{LINKEDIN_PERSON_ID}",
        "message": {"text": comment_text},
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code == 201:
            return {"status": "posted"}
        else:
            return {"status": "error", "code": r.status_code}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def main():
    print(f"[START] Engagement Bot -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log = load_engagement_log()
    already_commented = set(c.get("post_id", "") for c in log.get("comments_posted", []))

    print("[1/3] Recherche de posts pertinents...")
    posts = search_relevant_posts()
    print(f"       -> {len(posts)} posts trouves")

    if not posts:
        print("[DONE] Aucun post trouve.")
        return

    print("[2/3] Filtrage...")
    new_posts = [p for p in posts if p.get("post_id") and p["post_id"] not in already_commented]
    if not new_posts:
        print("[DONE] Tous deja commentes.")
        return

    print(f"[3/3] Generation de commentaires ({min(3, len(new_posts))} max)...")
    comments_made = 0
    for post in new_posts[:3]:
        post_content = post.get("content", "")
        if not post_content or len(post_content) < 30:
            continue

        if LINKEDIN_PERSON_ID and LINKEDIN_PERSON_ID in post.get("author", ""):
            continue

        lang = detect_language(post_content)
        comment_text = generate_strategic_comment(post_content, lang)
        if not comment_text:
            continue

        result = post_comment(post["post_id"], comment_text)
        log["comments_posted"].append({
            "post_id": post["post_id"],
            "hashtag": post.get("hashtag", ""),
            "comment_text": comment_text,
            "lang": lang,
            "result": result.get("status"),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        comments_made += 1
        print(f"  [{comments_made}] {result.get('status')} | {comment_text[:60]}...")

    log["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    log["comments_posted"] = log["comments_posted"][-200:]
    save_engagement_log(log)
    print(f"[DONE] {comments_made} commentaires strategiques publies.")


if __name__ == "__main__":
    main()
