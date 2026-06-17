"""
ANALYTICS.PY - Performance Dashboard + Rapport Email Hebdomadaire
Supporte les posts bilingues (FR + EN). Analyse par langue.
"""

import os
import json
import smtplib
import requests
import base64
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from collections import defaultdict
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_PERSON_ID = os.environ.get("LINKEDIN_PERSON_ID")
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS")
SMTP_EMAIL = os.environ.get("SMTP_EMAIL")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL")

PUBLISHED_DIR = "published_posts"
ANALYTICS_DIR = "analytics_reports"
METRICS_FILE = "metrics_history.json"
TRACKER_FILE = "tracker.json"


def send_report_email(to_email, subject, body_text):
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
            print("[OK] Rapport envoye (Gmail API)")
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
            print("[OK] Rapport envoye (SMTP)")
            return True
        except Exception as e:
            print(f"[ERROR] SMTP: {e}")
    return False


def fetch_post_analytics(post_id):
    if not LINKEDIN_ACCESS_TOKEN:
        return None
    url = f"https://api.linkedin.com/v2/socialActions/{post_id}"
    headers = {"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}", "X-Restli-Protocol-Version": "2.0.0"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def load_metrics():
    if os.path.exists(METRICS_FILE):
        with open(METRICS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"posts_metrics": [], "weekly_reports": []}


def save_metrics(metrics):
    with open(METRICS_FILE, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)


def load_published_posts():
    posts = []
    if not os.path.exists(PUBLISHED_DIR):
        return posts
    for fn in sorted(os.listdir(PUBLISHED_DIR)):
        if fn.endswith(".json"):
            with open(os.path.join(PUBLISHED_DIR, fn), "r", encoding="utf-8") as f:
                post = json.load(f)
                post["_filename"] = fn
                posts.append(post)
    return posts


def update_all_metrics():
    posts = load_published_posts()
    metrics = load_metrics()
    updated = 0
    for post in posts:
        for lang_key in ["linkedin_response_fr", "linkedin_response_en", "linkedin_response"]:
            response_data = post.get(lang_key)
            if not response_data:
                continue
            post_id = response_data.get("id")
            if not post_id or post_id.startswith("sim_"):
                continue
            analytics = fetch_post_analytics(post_id)
            if not analytics:
                continue
            lang = "fr" if "fr" in lang_key else ("en" if "en" in lang_key else "unknown")
            entry = {
                "post_id": post_id,
                "filename": post.get("_filename", ""),
                "date": post.get("published_date", ""),
                "pillar": post.get("pillar", "unknown"),
                "format": post.get("format", "unknown"),
                "lang": lang,
                "likes": analytics.get("likesSummary", {}).get("totalLikes", 0),
                "comments": analytics.get("commentsSummary", {}).get("totalComments", 0),
                "shares": analytics.get("sharesSummary", {}).get("totalShares", 0),
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            entry["score"] = entry["likes"] + entry["comments"] * 3 + entry["shares"] * 5
            existing = next((i for i, m in enumerate(metrics["posts_metrics"]) if m.get("post_id") == post_id), None)
            if existing is not None:
                metrics["posts_metrics"][existing] = entry
            else:
                metrics["posts_metrics"].append(entry)
            updated += 1
    save_metrics(metrics)
    return updated


def analyze(metrics):
    posts = metrics.get("posts_metrics", [])
    if not posts:
        return {"status": "no_data", "total_posts": 0}

    by_pillar = defaultdict(lambda: {"count": 0, "scores": []})
    by_format = defaultdict(lambda: {"count": 0, "scores": []})
    by_day = defaultdict(lambda: {"count": 0, "scores": []})
    by_lang = defaultdict(lambda: {"count": 0, "scores": []})

    for p in posts:
        score = p.get("score", 0)
        by_pillar[p.get("pillar", "?")]["count"] += 1
        by_pillar[p.get("pillar", "?")]["scores"].append(score)
        by_format[p.get("format", "?")]["count"] += 1
        by_format[p.get("format", "?")]["scores"].append(score)
        by_lang[p.get("lang", "?")]["count"] += 1
        by_lang[p.get("lang", "?")]["scores"].append(score)
        try:
            day = datetime.strptime(p["date"], "%Y-%m-%d").strftime("%A")
            by_day[day]["count"] += 1
            by_day[day]["scores"].append(score)
        except (ValueError, KeyError):
            pass

    def summarize(groups):
        result = {}
        for k, v in groups.items():
            scores = v["scores"]
            result[k] = {
                "count": v["count"],
                "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
                "max_score": max(scores) if scores else 0,
            }
        return result

    sorted_posts = sorted(posts, key=lambda x: x.get("score", 0), reverse=True)

    now = datetime.now()
    this_week = [p for p in posts if p.get("date", "") >= (now - timedelta(days=7)).strftime("%Y-%m-%d")]
    prev_week = [p for p in posts if (now - timedelta(days=14)).strftime("%Y-%m-%d") <= p.get("date", "") < (now - timedelta(days=7)).strftime("%Y-%m-%d")]

    trend = {}
    if this_week:
        trend["this_week_avg"] = round(sum(p.get("score", 0) for p in this_week) / len(this_week), 1)
    if prev_week:
        trend["prev_week_avg"] = round(sum(p.get("score", 0) for p in prev_week) / len(prev_week), 1)
    if trend.get("this_week_avg") and trend.get("prev_week_avg") and trend["prev_week_avg"] > 0:
        trend["change_pct"] = round(((trend["this_week_avg"] - trend["prev_week_avg"]) / trend["prev_week_avg"]) * 100, 1)

    return {
        "total_posts": len(posts),
        "by_pillar": summarize(by_pillar),
        "by_format": summarize(by_format),
        "by_day": summarize(by_day),
        "by_lang": summarize(by_lang),
        "top_3": sorted_posts[:3],
        "trend": trend,
    }


def generate_suggestions(analysis):
    suggestions = []
    pillar_data = analysis.get("by_pillar", {})
    if pillar_data:
        best = max(pillar_data.items(), key=lambda x: x[1].get("avg_score", 0))
        suggestions.append(f"Pilier '{best[0]}' = meilleur score moyen ({best[1]['avg_score']}). Augmente sa frequence.")
    format_data = analysis.get("by_format", {})
    if format_data:
        best = max(format_data.items(), key=lambda x: x[1].get("avg_score", 0))
        suggestions.append(f"Format '{best[0]}' performe le mieux (score {best[1]['avg_score']}).")
    day_data = analysis.get("by_day", {})
    if day_data:
        best = max(day_data.items(), key=lambda x: x[1].get("avg_score", 0))
        suggestions.append(f"Meilleur jour: {best[0]} (score moyen {best[1]['avg_score']})")
    lang_data = analysis.get("by_lang", {})
    if lang_data and len(lang_data) > 1:
        best_lang = max(lang_data.items(), key=lambda x: x[1].get("avg_score", 0))
        worst_lang = min(lang_data.items(), key=lambda x: x[1].get("avg_score", 0))
        suggestions.append(f"Langue: '{best_lang[0].upper()}' score {best_lang[1]['avg_score']} vs '{worst_lang[0].upper()}' score {worst_lang[1]['avg_score']}")
    trend = analysis.get("trend", {})
    if trend.get("change_pct") is not None:
        if trend["change_pct"] > 0:
            suggestions.append(f"Engagement en hausse de +{trend['change_pct']}% cette semaine !")
        elif trend["change_pct"] < -20:
            suggestions.append(f"Attention: engagement en baisse de {trend['change_pct']}%.")
    return suggestions


def build_report_text(analysis, suggestions):
    body = f"""RAPPORT HEBDOMADAIRE LINKEDIN (BILINGUE)
{'='*50}
Genere le: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Periode: {(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')} -> {datetime.now().strftime('%Y-%m-%d')}
Posts suivis: {analysis.get('total_posts', 0)}

PERFORMANCE PAR PILIER:
{'-'*30}
"""
    for pillar, data in analysis.get("by_pillar", {}).items():
        body += f"  {pillar.upper():15} | {data['count']} posts | Score moy: {data['avg_score']} | Max: {data['max_score']}\n"

    body += f"""
PERFORMANCE PAR FORMAT:
{'-'*30}
"""
    for fmt, data in analysis.get("by_format", {}).items():
        body += f"  {fmt:15} | {data['count']} posts | Score moy: {data['avg_score']} | Max: {data['max_score']}\n"

    body += f"""
PERFORMANCE PAR LANGUE:
{'-'*30}
"""
    for lang, data in analysis.get("by_lang", {}).items():
        body += f"  {lang.upper():15} | {data['count']} posts | Score moy: {data['avg_score']} | Max: {data['max_score']}\n"

    body += f"""
PERFORMANCE PAR JOUR:
{'-'*30}
"""
    for day, data in analysis.get("by_day", {}).items():
        body += f"  {day:15} | {data['count']} posts | Score moy: {data['avg_score']}\n"

    body += f"""
TENDANCE:
{'-'*30}
"""
    trend = analysis.get("trend", {})
    if trend.get("this_week_avg"):
        body += f"  Cette semaine: {trend['this_week_avg']} (score moyen)\n"
    if trend.get("prev_week_avg"):
        body += f"  Semaine precedente: {trend['prev_week_avg']}\n"
    if trend.get("change_pct") is not None:
        body += f"  Evolution: {'+' if trend['change_pct'] > 0 else ''}{trend['change_pct']}%\n"

    body += f"""
TOP 3 POSTS:
{'-'*30}
"""
    for i, p in enumerate(analysis.get("top_3", [])[:3], 1):
        body += f"  #{i} [{p.get('pillar','?').upper()}] [{p.get('lang','?').upper()}] Score: {p.get('score',0)} | {p.get('date','?')} | Likes: {p.get('likes',0)} Comments: {p.get('comments',0)} Shares: {p.get('shares',0)}\n"

    body += f"""
SUGGESTIONS:
{'-'*30}
"""
    for s in suggestions:
        body += f"  -> {s}\n"

    body += f"""
{'='*50}
Genere automatiquement par LinkedIn Bot Analytics
"""
    return body


def main():
    print(f"[START] Analytics -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    print("[1/4] Mise a jour des metriques...")
    updated = update_all_metrics()
    print(f"       -> {updated} posts mis a jour")

    print("[2/4] Analyse...")
    metrics = load_metrics()
    analysis = analyze(metrics)

    if analysis.get("status") == "no_data":
        print("[SKIP] Pas encore de donnees a analyser.")
        return

    print("[3/4] Suggestions...")
    suggestions = generate_suggestions(analysis)
    for s in suggestions:
        print(f"       -> {s}")

    print("[4/4] Generation et envoi du rapport...")
    report_text = build_report_text(analysis, suggestions)

    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "period": f"{(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')} -> {datetime.now().strftime('%Y-%m-%d')}",
        "analysis": analysis,
        "suggestions": suggestions,
    }

    os.makedirs(ANALYTICS_DIR, exist_ok=True)
    report_file = os.path.join(ANALYTICS_DIR, f"report_{datetime.now().strftime('%Y-%m-%d')}.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"       Rapport sauvegarde: {report_file}")

    if NOTIFY_EMAIL:
        subject = f"[LinkedIn Analytics] Rapport semaine {datetime.now().strftime('%W')} - {datetime.now().strftime('%Y')}"
        sent = send_report_email(NOTIFY_EMAIL, subject, report_text)
        if sent:
            print("       Rapport envoye par email")
        else:
            print("       [WARN] Email non envoye")

    print(f"\n--- RESUME ---")
    print(f"Posts analyses: {analysis['total_posts']}")
    if analysis.get("by_pillar"):
        best_pillar = max(analysis["by_pillar"].items(), key=lambda x: x[1].get("avg_score", 0))
        print(f"Meilleur pilier: {best_pillar[0]}")
    if analysis.get("by_lang"):
        best_lang = max(analysis["by_lang"].items(), key=lambda x: x[1].get("avg_score", 0))
        print(f"Meilleure langue: {best_lang[0].upper()}")
    if trend.get("change_pct") is not None:
        print(f"Tendance: {'+' if trend['change_pct'] > 0 else ''}{trend['change_pct']}%")
    print("[DONE] Analytics termine.")


if __name__ == "__main__":
    main()
