
"""
REPLY_BOT.PY - Reponse automatique aux commentaires sur tes posts LinkedIn
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

PUBLISHED_DIR = "published_posts"
REPLY_LOG = "reply_log.json"


def load_reply_log():
    if os.path.exists(REPLY_LOG):
        with open(REPLY_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"replies_sent": [], "last_check": None}


def save_reply_log(log):
    with open(REPLY_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def get_post_comments(post_id):
    if not LINKEDIN_ACCESS_TOKEN:
        return []
    url = f"https://api.linkedin.com/v2/socialActions/{post_id}/comments"
    headers = {"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}", "X-Restli-Protocol-Version": "2.0.0"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.json().get("elements", [])
    except Exception:
        pass
    return []


def detect_language(text):
    french_words = ["je", "tu", "il", "elle", "nous", "les", "des", "une", "est", "pour", "dans", "avec", "sur", "pas"]
    text_lower = text.lower().split()
    french_count = sum(1 for w in text_lower if w in french_words)
    return "fr" if french_count >= 2 else "en"


def generate_reply(comment_text, post_content, lang="fr"):
    if lang == "fr":
        prompt = f"""Tu es Mehdi, Category Manager en procurement.
Quelqu'un a commente ton post LinkedIn.

TON POST (extrait): {post_content[:200]}
COMMENTAIRE: {comment_text}

Ecris une REPONSE courte et engageante:
- Remercie ou reagis au point specifique
- Ajoute de la valeur
- Pose une question de relance si pertinent
- 1-3 phrases MAX
- Ton naturel
- PAS de hashtags

Ecris UNIQUEMENT la reponse."""
    else:
        prompt = f"""You are Mehdi, a Category Manager in procurement.
Someone commented on your LinkedIn post.

YOUR POST (excerpt): {post_content[:200]}
COMMENT: {comment_text}

Write a SHORT engaging REPLY:
- Acknowledge their specific point
- Add value
- Ask a follow-up question if relevant
- 1-3 sentences MAX
- Natural tone
- NO hashtags

Write ONLY the reply."""

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=200,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ERROR] Generate reply: {e}")
        return None


def post_reply(post_id, comment_id, reply_text):
    if not LINKEDIN_ACCESS_TOKEN or not LINKEDIN_PERSON_ID:
        print(f"[SIMULATE] Reply: {reply_text[:80]}...")
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
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code == 201:
            return {"status": "posted"}
        else:
            return {"status": "error", "code": r.status_code}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def main():
    print(f"[START] Reply Bot -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log = load_reply_log()
    already_replied = set(r.get("comment_id", "") for r in log.get("replies_sent", []))

    if not os.path.exists(PUBLISHED_DIR):
        print("[SKIP] Aucun post publie.")
        return

    recent_posts = []
    for fn in sorted(os.listdir(PUBLISHED_DIR), reverse=True)[:5]:
        if fn.endswith(".json"):
            with open(os.path.join(PUBLISHED_DIR, fn), "r", encoding="utf-8") as f:
                post = json.load(f)
                post["_filename"] = fn
                recent_posts.append(post)

    replies_made = 0
    for post in recent_posts:
        for lang_key in ["linkedin_response_fr", "linkedin_response_en"]:
            response_data = post.get(lang_key)
            if not response_data:
                continue
            post_id = response_data.get("id")
            if not post_id or post_id.startswith("sim_"):
                continue

            comments = get_post_comments(post_id)
            post_content = post.get("content_fr") or post.get("content_en") or ""

            for comment in comments:
                comment_id = comment.get("$URN", comment.get("id", ""))
                if comment_id in already_replied:
                    continue
                actor = comment.get("actor", "")
                if LINKEDIN_PERSON_ID and LINKEDIN_PERSON_ID in actor:
                    continue

                comment_text = comment.get("message", {}).get("text", "")
                if not comment_text or len(comment_text) < 5:
                    continue

                lang = detect_language(comment_text)
                reply_text = generate_reply(comment_text, post_content, lang)
                if not reply_text:
                    continue

                result = post_reply(post_id, comment_id, reply_text)
                log["replies_sent"].append({
                    "comment_id": comment_id,
                    "comment_text": comment_text[:100],
                    "reply_text": reply_text,
                    "post_filename": post.get("_filename", ""),
                    "lang": lang,
                    "result": result.get("status"),
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                })
                replies_made += 1
                if replies_made >= 10:
                    break
        if replies_made >= 10:
            break

    log["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    log["replies_sent"] = log["replies_sent"][-200:]
    save_reply_log(log)
    print(f"[DONE] {replies_made} replies envoyees.")


if __name__ == "__main__":
    main()

