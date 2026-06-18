# engagement_bot.py - Commentaires strategiques sur les posts du reseau

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
        url = "https://api.linkedin.com/v2/search?q=hashtag&hashtag=" + hashtag + "&count=5"
        headers = {
            "Authorization": "Bearer " + LINKEDIN_ACCESS_TOKEN,
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
            print("[WARN] Search " + hashtag + ": " + str(e))
    return posts_found


def detect_language(text):
    french_words = ["je", "tu", "il", "elle", "nous", "les", "des", "une", "est", "pour", "dans", "avec"]
    text_lower = text.lower().split()
    french_count = sum(1 for w in text_lower if w in french_words)
    return "fr" if french_count >= 2 else "en"


def generate_strategic_comment(post_content, lang="en"):
    if lang == "fr":
        prompt = (
            "Tu es Mehdi, Category Manager en procurement.\n"
            "Tu veux commenter un post LinkedIn de maniere strategique.\n\n"
            "POST:\n" + post_content[:400] + "\n\n"
            "Ecris un COMMENTAIRE strategique:\n"
            "- Apporte de la valeur (pas juste super post)\n"
            "- Partage une experience complementaire ou un point de vue\n"
            "- 2-4 phrases\n"
            "- Montre ton expertise sans etre pretentieux\n"
            "- Ton naturel et collegial\n"
            "- PAS de hashtags dans le commentaire\n\n"
            "Ecris UNIQUEMENT le commentaire."
        )
    else:
        prompt = (
            "You are Mehdi, a Category Manager in procurement.\n"
            "You want to comment on a LinkedIn post strategically.\n\n"
            "POST:\n" + post_content[:400] + "\n\n"
            "Write a STRATEGIC COMMENT:\n"
            "- Add value (not just great post)\n"
            "- Share a complementary experience or point of view\n"
            "- 2-4 sentences\n"
            "- Show expertise without being pretentious\n"
            "- Natural, collegial tone\n"
            "- NO hashtags in the comment\n\n"
            "Write ONLY the comment."
        )
    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=250,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("[ERROR] Generate comment: " + str(e))
        return None


def post_comment(post_id, comment_text):
    if not LINKEDIN_ACCESS_TOKEN or not LINKEDIN_PERSON_ID:
        print("[SIMULATE] Comment: " + comment_text[:80] + "...")
        return {"status": "simulated"}
    url = "https://api.linkedin.com/v2/socialActions/" + post_id + "/comments"
    headers = {
        "Authorization": "Bearer " + LINKEDIN_ACCESS_TOKEN,
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    payload = {
        "actor": "urn:li:person:" + LINKEDIN_PERSON_ID,
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
    print("[START] Engagement Bot -- " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    log = load_engagement_log()
    already_commented = set(c.get("post_id", "") for c in log.get("comments_posted", []))
    print("[1/3] Recherche de posts pertinents...")
    posts = search_relevant_posts()
    print("       -> " + str(len(posts)) + " posts trouves")
    if not posts:
        print("[DONE] Aucun post trouve.")
        return
    print("[2/3] Filtrage...")
    new_posts = [p for p in posts if p.get("post_id") and p["post_id"] not in already_commented]
    if not new_posts:
        print("[DONE] Tous deja commentes.")
        return
    max_comments = min(3, len(new_posts))
    print("[3/3] Generation de commentaires (" + str(max_comments) + " max)...")
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
        print("  [" + str(comments_made) + "] " + str(result.get("status")) + " | " + comment_text[:60] + "...")
    log["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    log["comments_posted"] = log["comments_posted"][-200:]
    save_engagement_log(log)
    print("[DONE] " + str(comments_made) + " commentaires strategiques publies.")


if __name__ == "__main__":
    main()
