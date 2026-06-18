"""
ANALYTICS.PY - Performance Dashboard + Rapport Email Hebdomadaire
Analyse par langue (FR vs EN), pilier, format, jour.
"""

import os
import json
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
            return True
        except Exception as e:
            print(f"[WARN] Gmail send: {e}")
    if SMTP_EMAIL and SMTP_PASSWORD:
        import smtplib
        try:
            msg = MIMEText(body_text, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = SMTP_EMAIL
            msg["To"] = to_email
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(SMTP_EMAIL, SMTP_PASSWORD)
                server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
            return True
        except Exception as e:
            print(f"[WARN] SMTP send: {e}")
    return False


def load_metrics():
    if os.path.exists(METRICS_FILE):
        with open(METRICS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"posts_metrics": [], "weekly_reports": []}


def save_metrics(metrics):
    with open(METRICS_FILE, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)


def fetch_post_analytics(post_id):
    if not LINKEDIN_ACCESS_TOKEN:
        return None
    url = f"https://api.linkedin.com/v2/socialActions/{post_id}"
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"[WARN] Fetch analytics: {e}")
    return None


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
                "published_time": post.get("published_time", "08:30"),
                "pillar": post.get("pillar", "unknown"),
                "format": post.get("format", "unknown"),
                "lang": lang,
                "likes": analytics.get("likesSummary", {}).get("totalLikes", 0),
                "comments": analytics.get("commentsSummary", {}).get("totalComments", 0),
                "shares": analytics.get("sharesSummary", {}).get("totalShares", 0),
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            entry["score"] = entry["likes"] + entry["comments"] * 3 + entry["shares"] * 5
            existing = next(
                (i for i, m in enumerate(metrics["posts_metrics"]) if m.get("post_id") == post_id),
                None,
            )
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
        pillar = p.get("pillar", "?")
        fmt = p.get("format", "?")
        lang = p.get("lang", "?")
        by_pillar[pillar]["count"] += 1
        by_pillar[pillar]["scores"].append(score)
        by_format[fmt]["count"] += 1
        by_format[fmt]["scores"].append(score)
        by_lang[lang]["count"] += 1
        by_lang[lang]["scores"].append(score)
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
                "total_score": sum(scores),
            }
        return result

    sorted_posts = sorted(posts, key=lambda x: x.get("score", 0), reverse=True)
    now = datetime.now()
    this_week = [
        p for p in posts
        if p.get("date", "") >= (now - timedelta(days=7)).strftime("%Y-%m-%d")
    ]
    prev_week = [
        p for p in posts
        if (now - timedelta(days=14)).strftime("%Y-%m-%d") <= p.get("date", "") < (now - timedelta(days=7)).strftime("%Y-%m-%d")
    ]
    trend = {}
    if this_week:
        trend["this_week_avg"] = round(sum(p.get("score", 0) for p in this_week) / len(this_week), 1)
        trend["this_week_count"] = len(this_week)
    if prev_week:
        trend["prev_week_avg"] = round(sum(p.get("score", 0) for p in prev_week) / len(prev_week), 1)
        trend["prev_week_count"] = len(prev_week)
    if trend.get("this_week_avg") and trend.get("prev_week_avg") and trend["prev_week_avg"] > 0:
        trend["change_pct"] = round(
            ((trend["this_week_avg"] - trend["prev_week_avg"]) / trend["prev_week_avg"]) * 100, 1
        )
    total_likes = sum(p.get("likes", 0) for p in posts)
    total_comments = sum(p.get("comments", 0) for p in posts)
    total_shares = sum(p.get("shares", 0) for p in posts)
    return {
        "total_posts": len(posts),
        "total_likes": total_likes,
        "total_comments": total_comments,
        "total_shares": total_shares,
        "by_pillar": summarize(by_pillar),
        "by_format": summarize(by_format),
        "by_day": summarize(by_day),
        "by_lang": summarize(by_lang),
        "top_3": sorted_posts[:3],
        "worst_3": sorted_posts[-3:] if len(sorted_posts) >= 3 else [],
        "trend": trend,
    }


def generate_suggestions(analysis):
    suggestions = []
    pillar_data = analysis.get("by_pillar", {})
    if pillar_data:
        best = max(pillar_data.items(), key=lambda x: x[1].get("avg_score", 0))
        worst = min(pillar_data.items(), key=lambda x: x[1].get("avg_score", 0))
        suggestions.append(
            f"Meilleur pilier: '{best[0]}' (score moy {best[1]['avg_score']}). Augmente sa frequence."
        )
        if best[0] != worst[0]:
            suggestions.append(
                f"Pilier faible: '{worst[0]}' (score moy {worst[1]['avg_score']}). A ameliorer ou reduire."
            )
    format_data = analysis.get("by_format", {})
    if format_data:
        best = max(format_data.items(), key=lambda x: x[1].get("avg_score", 0))
        suggestions.append(f"Format gagnant: '{best[0]}' (score moy {best[1]['avg_score']}).")
    day_data = analysis.get("by_day", {})
    if day_data:
        best = max(day_data.items(), key=lambda x: x[1].get("avg_score", 0))
        worst = min(day_data.items(), key=lambda x: x[1].get("avg_score", 0))
        suggestions.append(f"Meilleur jour: {best[0]} (score moy {best[1]['avg_score']})")
        if best[0] != worst[0]:
            suggestions.append(f"Jour faible: {worst[0]} (score moy {worst[1]['avg_score']})")
    lang_data = analysis.get("by_lang", {})
    if lang_data and len(lang_data) > 1:
        best_lang = max(lang_data.items(), key=lambda x: x[1].get("avg_score", 0))
        worst_lang = min(lang_data.items(), key=lambda x: x[1].get("avg_score", 0))
        diff = best_lang[1]["avg_score"] - worst_lang[1]["avg_score"]
        suggestions.append(
            f"Langue: '{best_lang[0].upper()}' score {best_lang[1]['avg_score']} vs "
            f"'{worst_lang[0].upper()}' score {worst_lang[1]['avg_score']} (delta: {round(diff, 1)})"
        )
        if diff > 10:
            suggestions.append(
                f"Ecart significatif entre langues. Investis plus sur le {best_lang[0].upper()}."
            )
    trend = analysis.get("trend", {})
    if trend.get("change_pct") is not None:
        if trend["change_pct"] > 0:
            suggestions.append(f"Engagement en HAUSSE de +{trend['change_pct']}% cette semaine!")
        elif trend["change_pct"] < -20:
            suggestions.append(f"ATTENTION: engagement en baisse de {trend['change_pct']}%. Ajuste ton contenu.")
        elif trend["change_pct"] < 0:
            suggestions.append(f"Legere baisse de {trend['change_pct']}%. Surveiller.")
    if analysis.get("total_posts", 0) >= 20:
        avg_score = sum(p.get("score", 0) for p in analysis.get("top_3", [])) / max(len(analysis.get("top_3", [])), 1)
        suggestions.append(f"Score moyen top 3: {round(avg_score, 1)}. Objectif: depasser ce seuil regulierement.")
    return suggestions


def build_report_text(analysis, suggestions):
    now = datetime.now()
    body = f"""{'='*50}
RAPPORT HEBDOMADAIRE LINKEDIN (BILINGUE)
{'='*50}
Genere le: {now.strftime('%Y-%m-%d %H:%M')}
Posts suivis: {analysis.get('total_posts', 0)}
Total likes: {analysis.get('total_likes', 0)}
Total comments: {analysis.get('total_comments', 0)}
Total shares: {analysis.get('total_shares', 0)}

{'='*50}
PERFORMANCE PAR PILIER
{'-'*50}
"""
    for pillar, data in sorted(analysis.get("by_pillar", {}).items(), key=lambda x: x[1]["avg_score"], reverse=True):
        body += f"  {pillar.upper():15} | {data['count']:3} posts | Score moy: {data['avg_score']:6} | Max: {data['max_score']}\n"

    body += f"""
{'='*50}
PERFORMANCE PAR LANGUE
{'-'*50}
"""
    for lang, data in sorted(analysis.get("by_lang", {}).items(), key=lambda x: x[1]["avg_score"], reverse=True):
        body += f"  {lang.upper():15} | {data['count']:3} posts | Score moy: {data['avg_score']:6} | Max: {data['max_score']}\n"

    body += f"""
{'='*50}
PERFORMANCE PAR FORMAT
{'-'*50}
"""
    for fmt, data in sorted(analysis.get("by_format", {}).items(), key=lambda x: x[1]["avg_score"], reverse=True):
        body += f"  {fmt:15} | {data['count']:3} posts | Score moy: {data['avg_score']:6} | Max: {data['max_score']}\n"

    body += f"""
{'='*50}
PERFORMANCE PAR JOUR
{'-'*50}
"""
    for day, data in sorted(analysis.get("by_day", {}).items(), key=lambda x: x[1]["avg_score"], reverse=True):
        body += f"  {day:15} | {data['count']:3} posts | Score moy: {data['avg_score']:6}\n"

    body += f"""
{'='*50}
TENDANCE SEMAINE
{'-'*50}
"""
    trend = analysis.get("trend", {})
    if trend.get("this_week_avg"):
        body += f"  Cette semaine:     {trend['this_week_avg']} ({trend.get('this_week_count', 0)} posts)\n"
    if trend.get("prev_week_avg"):
        body += f"  Semaine precedente: {trend['prev_week_avg']} ({trend.get('prev_week_count', 0)} posts)\n"
    if trend.get("change_pct") is not None:
        arrow = "+" if trend["change_pct"] > 0 else ""
        body += f"  Evolution:          {arrow}{trend['change_pct']}%\n"

    body += f"""
{'='*50}
TOP 3 POSTS
{'-'*50}
"""
    for i, p in enumerate(analysis.get("top_3", [])[:3], 1):
        body += f"  #{i} [{p.get('pillar','?').upper()}] [{p.get('lang','?').upper()}] Score: {p.get('score',0)} | {p.get('date','?')} | L:{p.get('likes',0)} C:{p.get('comments',0)} S:{p.get('shares',0)}\n"

    if analysis.get("worst_3"):
        body += f"""
{'='*50}
WORST 3 POSTS (a ameliorer)
{'-'*50}
"""
        for i, p in enumerate(analysis.get("worst_3", [])[:3], 1):
            body += f"  #{i} [{p.get('pillar','?').upper()}] [{p.get('lang','?').upper()}] Score: {p.get('score',0)} | {p.get('date','?')}\n"

    body += f"""
{'='*50}
SUGGESTIONS D'OPTIMISATION
{'-'*50}
"""
    for i, s in enumerate(suggestions, 1):
        body += f"  {i}. {s}\n"

    body += f"""
{'='*50}
PROCHAINES ACTIONS RECOMMANDEES
{'-'*50}
"""
    if trend.get("change_pct") is not None and trend["change_pct"] < -10:
        body += "  -> Changer le format ou le pilier du prochain post\n"
        body += "  -> Tester un nouveau creneau horaire\n"
    else:
        body += "  -> Continuer la strategie actuelle\n"
        body += "  -> Tester un carrousel si pas fait recemment\n"

    return body


def save_report(analysis, suggestions):
    os.makedirs(ANALYTICS_DIR, exist_ok=True)
    report_file = os.path.join(
        ANALYTICS_DIR, f"report_{datetime.now().strftime('%Y-%m-%d')}.json"
    )
    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "analysis": analysis,
        "suggestions": suggestions,
    }
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[OK] Rapport sauvegarde: {report_file}")
    return report_file


def main():
    print(f"[START] Analytics -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    print("[1/5] Chargement des posts publies...")
    posts = load_published_posts()
    print(f"       -> {len(posts)} posts trouves")

    print("[2/5] Mise a jour des metriques LinkedIn...")
    updated = update_all_metrics()
    print(f"       -> {updated} posts mis a jour depuis LinkedIn API")

    print("[3/5] Analyse des performances...")
    metrics = load_metrics()
    analysis = analyze(metrics)
    if analysis.get("status") == "no_data":
        print("[SKIP] Pas encore de donnees suffisantes.")
        return

    print(f"       -> {analysis['total_posts']} posts analyses")
    print(f"       -> {analysis['total_likes']} likes | {analysis['total_comments']} comments | {analysis['total_shares']} shares")

    print("[4/5] Generation des suggestions...")
    suggestions = generate_suggestions(analysis)
    for s in suggestions:
        print(f"       -> {s}")

    print("[5/5] Construction et envoi du rapport...")
    report_text = build_report_text(analysis, suggestions)
    save_report(analysis, suggestions)

    if NOTIFY_EMAIL:
        week_num = datetime.now().strftime("%W")
        subject = f"[LinkedIn Analytics] Rapport semaine {week_num} - Score moy: {analysis.get('trend', {}).get('this_week_avg', '?')}"
        success = send_report_email(NOTIFY_EMAIL, subject, report_text)
        if success:
            print("[OK] Rapport envoye par email")
        else:
            print("[WARN] Echec envoi email")

    print("[DONE] Analytics termine.")


if __name__ == "__main__":
    main()
