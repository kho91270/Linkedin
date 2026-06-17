
"""
ANALYTICS.PY — Performance Dashboard
Suivi des metriques, analyse des tendances, rapport hebdomadaire.
"""

import os
import json
import requests
from datetime import datetime, timedelta
from collections import defaultdict

# ============================================================
# CONFIGURATION
# ============================================================
LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_PERSON_ID = os.environ.get("LINKEDIN_PERSON_ID")
SMTP_EMAIL = os.environ.get("SMTP_EMAIL")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL")

PUBLISHED_DIR = "published_posts"
ANALYTICS_DIR = "analytics_reports"
METRICS_FILE = "metrics_history.json"
TRACKER_FILE = "tracker.json"


# ============================================================
# COLLECTE
# ============================================================
def fetch_post_analytics(post_id):
    """Recupere les analytics d'un post LinkedIn."""
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


# ============================================================
# MISE A JOUR DES METRIQUES
# ============================================================
def update_all_metrics():
    """Met a jour les metriques de tous les posts."""
    posts = load_published_posts()
    metrics = load_metrics()
    updated = 0

    for post in posts:
        post_id = post.get("linkedin_response", {}).get("id")
        if not post_id:
            continue

        analytics = fetch_post_analytics(post_id)
        if not analytics:
            continue

        entry = {
            "post_id": post_id,
            "filename": post.get("_filename", ""),
            "date": post.get("published_date", ""),
            "pillar": post.get("pillar", "unknown"),
            "format": post.get("format", "unknown"),
            "likes": analytics.get("likesSummary", {}).get("totalLikes", 0),
            "comments": analytics.get("commentsSummary", {}).get("totalComments", 0),
            "shares": analytics.get("sharesSummary", {}).get("totalShares", 0),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        entry["score"] = entry["likes"] + entry["comments"] * 3 + entry["shares"] * 5

        # Upsert
        existing = next((i for i, m in enumerate(metrics["posts_metrics"]) if m.get("post_id") == post_id), None)
        if existing is not None:
            metrics["posts_metrics"][existing] = entry
        else:
            metrics["posts_metrics"].append(entry)
        updated += 1

    save_metrics(metrics)
    return updated


# ============================================================
# ANALYSE
# ============================================================
def analyze(metrics):
    """Analyse complete des performances."""
    posts = metrics.get("posts_metrics", [])
    if not posts:
        return {"status": "no_data"}

    # Par pilier
    by_pillar = defaultdict(lambda: {"count": 0, "scores": []})
    by_format = defaultdict(lambda: {"count": 0, "scores": []})
    by_day = defaultdict(lambda: {"count": 0, "scores": []})

    for p in posts:
        score = p.get("score", 0)
        by_pillar[p.get("pillar", "?")]["count"] += 1
        by_pillar[p.get("pillar", "?")]["scores"].append(score)
        by_format[p.get("format", "?")]["count"] += 1
        by_format[p.get("format", "?")]["scores"].append(score)
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

    # Top posts
    sorted_posts = sorted(posts, key=lambda x: x.get("score", 0), reverse=True)

    # Tendances (semaine actuelle vs precedente)
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
        "top_3": sorted_posts[:3],
        "trend": trend,
    }


# ============================================================
# SUGGESTIONS
# ============================================================
def generate_suggestions(analysis):
    """Genere des suggestions actionables."""
    suggestions = []

    pillar_data = analysis.get("by_pillar", {})
    if pillar_data:
        best = max(pillar_data.items(), key=lambda x: x[1].get("avg_score", 0))
        suggestions.append(f"Pilier '{best[0]}' = meilleur score moyen ({best[1]['avg_score']}). Augmente sa frequence.")

    format_data = analysis.get("by_format", {})
    if format_data:
        best = max(format_data.items(), key=lambda x: x[1].get("avg_score", 0))
        suggestions.append(f"Format '{best[0]}' performe le mieux (score {best[1]['avg_score']}). A prioriser.")

    day_data = analysis.get("by_day", {})
    if day_data:
        best = max(day_data.items(), key=lambda x: x[1].get("avg_score", 0))
        suggestions.append(f"Meilleur jour: {best[0]} (score moyen {best[1]['avg_score']})")

    trend = analysis.get("trend", {})
    if trend.get("change_pct") is not None:
        if trend["change_pct"] > 0:
            suggestions.append(f"Engagement en hausse de +{trend['change_pct']}% cette semaine !")
        elif trend["change_pct"] < -20:
            suggestions.append(f"Attention: engagement en baisse de {trend['change_pct']}%. Revoir le contenu.")

    return suggestions


# ============================================================
# RAPPORT EMAIL
# ============================================================
def send_weekly_report(report):
    """Envoie le rapport par email."""
    if not SMTP_EMAIL or not SMTP_PASSWORD or not NOTIFY_EMAIL:
        return False

    import smtplib
    from email.mime.text import MIMEText

    analysis = report.get("analysis", {})
    suggestions = report.get("suggestions", [])

    body = f"""RAPPORT HEBDOMADAIRE LINKEDIN
{'='*40}
Periode: {report.get('period', '?')}
Posts suivis: {analysis.get('total_posts', 0)}

PERFORMANCE PAR PILIER:
"""
    for pillar, data in analysis.get("by_pillar", {}).items():
        body += f"  {pillar}: {data['count']} posts | Score moy: {data['avg_score']}\n"

    body += f"\nTENDANCE:\n"
    trend = analysis.get("trend", {})
    if trend.get("change_pct") is not None:
        body += f"  Evolution: {'+' if trend['change_pct'] > 0 else ''}{trend['change_pct']}% vs semaine precedente\n"

    body += f"\nSUGGESTIONS:\n"
    for s in suggestions:
        body += f"  -> {s}\n"

    body += f"\nTOP 3 POSTS:\n"
    for i, p in enumerate(analysis.get("top_3", [])[:3], 1):
        body += f"  #{i} [{p.get('pillar','?')}] Score: {p.get('score',0)} | {p.get('date','?')}\n"

    msg = MIMEText(body)
    msg["Subject"] = f"[LinkedIn Analytics] Rapport semaine {datetime.now().strftime('%W')}"
    msg["From"] = SMTP_EMAIL
    msg["To"] = NOTIFY_EMAIL

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, NOTIFY_EMAIL, msg.as_string())
        print("[OK] Rapport envoye par email")
        return True
    except Exception as e:
        print(f"[ERROR] Email: {e}")
        return False


# ============================================================
# MAIN
# ============================================================
def main():
    print(f"[START] Analytics -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    print("[1/4] Mise a jour des metriques...")
    updated = update_all_metrics()
    print(f"       -> {updated} posts mis a jour")

    print("[2/4] Analyse...")
    metrics = load_metrics()
    analysis = analyze(metrics)

    print("[3/4] Suggestions...")
    suggestions = generate_suggestions(analysis)
    for s in suggestions:
        print(f"       -> {s}")

    # Sauvegarder le rapport
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

    print(f"[4/4] Envoi du rapport email...")
    send_weekly_report(report)

    print(f"\n[DONE] Analytics termine. Rapport: {report_file}")


if __name__ == "__main__":
    main()

