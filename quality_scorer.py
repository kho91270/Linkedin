# quality_scorer.py - Score qualite pre-publication + A/B testing hooks

import os
import json
import re
from datetime import datetime
from groq import Groq

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)
GROQ_MODEL = "llama-3.3-70b-versatile"

PUBLISHED_DIR = "published_posts"
MIN_QUALITY_SCORE = 70


def score_post(content, pillar, format_type):
    lines = content.strip().split("\n")
    non_empty_lines = [l for l in lines if l.strip()]
    scores = {}
    hook = non_empty_lines[0] if non_empty_lines else ""
    hook_score = 0
    if len(hook) <= 150:
        hook_score += 10
    if len(hook) >= 30:
        hook_score += 5
    if any(c in hook for c in ["?", "!", "..."]):
        hook_score += 5
    if any(word in hook.lower() for word in ["j ai", "je", "i ", "i ve", "my"]):
        hook_score += 5
    scores["hook"] = min(hook_score, 25)
    structure_score = 0
    if len(non_empty_lines) >= 5:
        structure_score += 10
    blank_lines = sum(1 for l in lines if not l.strip())
    if blank_lines >= 3:
        structure_score += 8
    if any("?" in l for l in non_empty_lines[-3:]):
        structure_score += 7
    scores["structure"] = min(structure_score, 25)
    char_count = len(content)
    length_score = 0
    if format_type in ["texte", "breaking"]:
        if 800 <= char_count <= 1500:
            length_score = 20
        elif 600 <= char_count <= 1800:
            length_score = 12
        elif char_count > 300:
            length_score = 5
    elif format_type == "question":
        if 300 <= char_count <= 600:
            length_score = 20
        elif 200 <= char_count <= 800:
            length_score = 12
    elif format_type == "insight":
        if 200 <= char_count <= 400:
            length_score = 20
        elif 150 <= char_count <= 500:
            length_score = 12
    else:
        if 500 <= char_count <= 1500:
            length_score = 20
    scores["longueur"] = length_score
    engagement_score = 0
    questions = sum(1 for l in non_empty_lines if "?" in l)
    if questions >= 1:
        engagement_score += 8
    if questions >= 2:
        engagement_score += 4
    hashtags = re.findall(r"#\w+", content)
    if 3 <= len(hashtags) <= 5:
        engagement_score += 3
    scores["engagement"] = min(engagement_score, 15)
    auth_score = 0
    personal_words = ["j ai", "je ", "mon ", "ma ", "mes ", "i ", "i ve", "my "]
    personal_count = sum(1 for w in personal_words if w in content.lower())
    if personal_count >= 2:
        auth_score += 8
    corporate_bs = ["synergy", "leverage", "paradigm", "disruptif", "game-changer"]
    bs_count = sum(1 for w in corporate_bs if w in content.lower())
    if bs_count == 0:
        auth_score += 7
    elif bs_count <= 1:
        auth_score += 3
    scores["authenticite"] = min(auth_score, 15)
    total = sum(scores.values())
    return {"total": total, "details": scores, "char_count": char_count}


def check_similarity_with_recent(content, max_similar=0.3):
    if not os.path.exists(PUBLISHED_DIR):
        return True
    recent_posts = []
    for fn in sorted(os.listdir(PUBLISHED_DIR), reverse=True)[:10]:
        if fn.endswith(".json"):
            with open(os.path.join(PUBLISHED_DIR, fn), "r", encoding="utf-8") as f:
                post = json.load(f)
                for key in ["content_fr", "content_en", "content"]:
                    if post.get(key):
                        recent_posts.append(post[key])
    if not recent_posts:
        return True
    content_words = set(content.lower().split())
    for recent in recent_posts:
        recent_words = set(recent.lower().split())
        if not content_words or not recent_words:
            continue
        intersection = content_words & recent_words
        union = content_words | recent_words
        similarity = len(intersection) / len(union) if union else 0
        if similarity > max_similar:
            return False
    return True


def generate_alternative_hooks(content, pillar, lang="fr"):
    current_hook = content.strip().split("\n")[0]
    if lang == "fr":
        prompt = (
            "Tu es Mehdi, Category Manager en procurement.\n"
            "Voici un post LinkedIn dont le hook actuel est:\n"
            "\"" + current_hook + "\"\n\n"
            "Le post complet:\n"
            + content[:500] + "\n\n"
            "Genere 2 HOOKS ALTERNATIFS pour ce meme post.\n"
            "- Moins de 150 caracteres chacun\n"
            "- Percutants, directs, premiere personne\n"
            "- Differents entre eux et de l original\n\n"
            "Reponds en JSON: {\"hook_a\": \"...\", \"hook_b\": \"...\"}"
        )
    else:
        prompt = (
            "You are Mehdi, a Category Manager in procurement.\n"
            "Here is a LinkedIn post with the current hook:\n"
            "\"" + current_hook + "\"\n\n"
            "Full post:\n"
            + content[:500] + "\n\n"
            "Generate 2 ALTERNATIVE HOOKS for this same post.\n"
            "- Less than 150 chars each\n"
            "- Punchy, direct, first person\n"
            "- Different from each other and the original\n\n"
            "Respond in JSON: {\"hook_a\": \"...\", \"hook_b\": \"...\"}"
        )
    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=300,
        )
        text = response.choices[0].message.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        hooks = json.loads(text)
        return {"original": current_hook, "hook_a": hooks.get("hook_a", ""), "hook_b": hooks.get("hook_b", "")}
    except Exception:
        return {"original": current_hook, "hook_a": "", "hook_b": ""}


def evaluate_post(post):
    report = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"), "passed": True}
    pillar = post.get("pillar", "terrain")
    format_type = post.get("format", "texte")
    if post.get("content_fr"):
        score_fr = score_post(post["content_fr"], pillar, format_type)
        report["score_fr"] = score_fr
        is_unique_fr = check_similarity_with_recent(post["content_fr"])
        report["unique_fr"] = is_unique_fr
        hooks_fr = generate_alternative_hooks(post["content_fr"], pillar, "fr")
        report["hooks_fr"] = hooks_fr
        if score_fr["total"] < MIN_QUALITY_SCORE or not is_unique_fr:
            report["passed"] = False
    if post.get("content_en"):
        score_en = score_post(post["content_en"], pillar, format_type)
        report["score_en"] = score_en
        is_unique_en = check_similarity_with_recent(post["content_en"])
        report["unique_en"] = is_unique_en
        hooks_en = generate_alternative_hooks(post["content_en"], pillar, "en")
        report["hooks_en"] = hooks_en
        if score_en["total"] < MIN_QUALITY_SCORE or not is_unique_en:
            report["passed"] = False
    return report


def format_quality_report(report):
    text = "RAPPORT QUALITE\n" + "=" * 30 + "\n"
    if report.get("score_fr"):
        s = report["score_fr"]
        status = "PASS" if s["total"] >= MIN_QUALITY_SCORE else "FAIL"
        text += "\nFR: " + str(s["total"]) + "/100 " + status + "\n"
        for k, v in s["details"].items():
            text += "  " + k + ": " + str(v) + "\n"
    if report.get("score_en"):
        s = report["score_en"]
        status = "PASS" if s["total"] >= MIN_QUALITY_SCORE else "FAIL"
        text += "\nEN: " + str(s["total"]) + "/100 " + status + "\n"
        for k, v in s["details"].items():
            text += "  " + k + ": " + str(v) + "\n"
    return text


if __name__ == "__main__":
    print("Quality Scorer ready.")
