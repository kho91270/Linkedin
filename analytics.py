
"""
ANALYTICS.PY — Performance Dashboard
Suivi des metriques LinkedIn, analyse des tendances,
et generation de rapports hebdomadaires avec suggestions.
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

PUBLISHED_DIR = "published_posts"
ANALYTICS_DIR = "analytics_reports"
METRICS_FILE = "metrics_history.json"
TRACKER_FILE = "tracker.json"

# Seuils d'alerte
ALERT_THRESHOLDS = {
    "impressions_low": 500,
    "engagement_rate_low": 0.02,
    "comments_high": 15,
    "followers_decline_days": 14,
}


# ============================================================
# COLLECTE DES METRIQUES
# ============================================================
def fetch_post_analytics(post_id):
    """Recupere les analytics d'un post via l'API LinkedIn."""
    if not LINKEDIN_ACCESS_TOKEN:
        return None

    url = f"https://api.linkedin.com/v2/socialActions/{post_id}"
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"[WARN] Fetch analytics: {e}")
    return None


def fetch_profile_followers():
    """Recupere le nombre de followers."""
    if not LINKEDIN_ACCESS_TOKEN or not LINKEDIN_PERSON_ID:
        return None

    url = f"https://api.linkedin.com/v2/networkSizes/urn:li:person:{LINKEDIN_PERSON_ID}"
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    try:
        response = requests.get(
            url, headers=headers,
            params={"edgeType": "CompanyFollowedByMember"},
            timeout=15
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("firstDegreeSize", 0)
    except Exception as e:
        print(f"[WARN] Fetch followers: {e}")
    return None


# ============================================================
# CHARGEMENT DES DONNEES
# ============================================================
def load_metrics_history():
    """Charge l'historique des metriques."""
    if os.path.exists(METRICS_FILE):
        with open(METRICS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"daily": [], "weekly_reports": [], "posts_metrics": []}


def save_metrics_history(metrics):
    """Sauvegarde l'historique."""
    with open(METRICS_FILE, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)


def load_published_posts():
    """Charge les posts publies avec leurs metadonnees."""
    posts = []
    if not os.path.exists(PUBLISHED_DIR):
        return posts

    for filename in sorted(os.listdir(PUBLISHED_DIR)):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(PUBLISHED_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            post = json.load(f)
            post["_filename"] = filename
            posts.append(post)
    return posts


# ============================================================
# COLLECTE DES METRIQUES PAR POST
# ============================================================
def update_post_metrics():
    """Met a jour les metriques de tous les posts publies."""
    posts = load_published_posts()
    metrics_history = load_metrics_history()
    updated_count = 0

    for post in posts:
        post_id = post.get("linkedin_response", {}).get("id")
        if not post_id:
            continue

        # Recuperer les metriques live
        analytics = fetch_post_analytics(post_id)
        if not analytics:
            continue

        metrics = {
            "post_id": post_id,
            "filename": post.get("_filename", ""),
            "date": post.get("published_date", ""),
            "pillar": post.get("pillar", "unknown"),
            "format": post.get("format", "unknown"),
            "likes": analytics.get("likesSummary", {}).get("totalLikes", 0),
            "comments": analytics.get("commentsSummary", {}).get("totalComments", 0),
            "shares": analytics.get("sharesSummary", {}).get("totalShares", 0),
            "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        # Calculer l'engagement (likes + comments*3 + shares*5)
        metrics["engagement_score"] = (
            metrics["likes"] + metrics["comments"] * 3 + metrics["shares"] * 5
        )

        # Ajouter ou mettre a jour dans l'historique
        existing_idx = None
        for i, existing in enumerate(metrics_history["posts_metrics"]):
            if existing.get("post_id") == post_id:
                existing_idx = i
                break

        if existing_idx is not None:
            metrics_history["posts_metrics"][existing_idx] = metrics
        else:
            metrics_history["posts_metrics"].append(metrics)

        updated_count += 1

    save_metrics_history(metrics_history)
    print(f"[INFO] {updated_count} posts mis a jour")
    return metrics_history


# ============================================================
# ANALYSE DES PERFORMANCES
# ============================================================
def analyze_by_dimension(posts_metrics, dimension):
    """Analyse les performances selon une dimension (pillar, format, day)."""
    groups = defaultdict(lambda: {
        "count": 0, "total_likes": 0, "total_comments": 0,
        "total_shares": 0, "total_score": 0
    })

    for post in posts_metrics:
        if dimension == "day":
            try:
                key = datetime.strptime(post["date"], "%Y-%m-%d").strftime("%A")
            except (ValueError, KeyError):
                continue
        else:
            key = post.get(dimension, "unknown")

        groups[key]["count"] += 1
        groups[key]["total_likes"] += post.get("likes", 0)
        groups[key]["total_comments"] += post.get("comments", 0)
        groups[key]["total_shares"] += post.get("shares", 0)
        groups[key]["total_score"] += post.get("engagement_score", 0)

    # Calculer les moyennes
    results = {}
    for key, data in groups.items():
        count = data["count"]
        if count > 0:
            results[key] = {
                "count": count,
                "avg_likes": round(data["total_likes"] / count, 1),
                "avg_comments": round(data["total_comments"] / count, 1),
                "avg_shares": round(data["total_shares"] / count, 1),
                "avg_score": round(data["total_score"] / count, 1),
            }

    return results


def get_top_and_worst_posts(posts_metrics, n=5):
    """Identifie les top et worst posts."""
    sorted_posts = sorted(
        posts_metrics,
        key=lambda x: x.get("engagement_score", 0),
        reverse=True
    )
    return {
        "top": sorted_posts[:n],
        "worst": sorted_posts[-n:] if len(sorted_posts) >= n else sorted_posts,
    }


def calculate_trends(posts_metrics):
    """Calcule les tendances sur les dernieres semaines."""
    if len(posts_metrics) < 4:
        return {"status": "insufficient_data", "message": "Pas assez de posts pour analyser les tendances"}

    # Trier par date
    sorted_posts = sorted(posts_metrics, key=lambda x: x.get("date", ""))

    # Derniere semaine vs semaine precedente
    now = datetime.now()
    last_week = [(now - timedelta(days=7)).strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")]
    prev_week = [(now - timedelta(days=14)).strftime("%Y-%m-%d"), (now - timedelta(days=7)).strftime("%Y-%m-%d")]

    last_week_posts = [p for p in sorted_posts if last_week[0] <= p.get("date", "") <= last_week[1]]
    prev_week_posts = [p for p in sorted_posts if prev_week[0] <= p.get("date", "") <= prev_week[1]]

    trends = {
        "last_week_posts": len(last_week_posts),
        "prev_week_posts": len(prev_week_posts),
    }

    if last_week_posts:
        trends["last_week_avg_score"] = round(
            sum(p.get("engagement_score", 0) for p in last_week_posts) / len(last_week_posts), 1
        )
    if prev_week_posts:
        trends["prev_week_avg_score"] = round(
            sum(p.get("engagement_score", 0) for p in prev_week_posts) / len(prev_week_posts), 1
        )

    # Evolution
    if trends.get("last_week_avg_score") and trends.get("prev_week_avg_score"):
        prev = trends["prev_week_avg_score"]
        if prev > 0:
            change = ((trends["last_week_avg_score"] - prev) / prev) * 100
            trends["score_change_pct"] = round(change, 1)
            trends["trend_direction"] = "up" if change > 0 else "down"

    return trends


# ============================================================
# GENERATION DE SUGGESTIONS
# ============================================================
def generate_suggestions(pillar_analysis, format_analysis, day_analysis, trends):
    """Genere des suggestions actionables."""
    suggestions = []

    # Meilleur pilier
    if pillar_analysis:
        best_pillar = max(pillar_analysis.items(), key=lambda x: x[1].get("avg_score", 0))
        suggestions.append({
            "type": "pillar",
            "priority": "high",
            "message": f"Pilier '{best_pillar[0]}' = meilleur engagement (score moy: {best_pillar[1]['avg_score']})",
            "action": f"Augmenter la frequence du pilier '{best_pillar[0]}'",
        })

    # Meilleur format
    if format_analysis:
        best_format = max(format_analysis.items(), key=lambda x: x[1].get("avg_score", 0))
        suggestions.append({
            "type": "format",
            "priority": "medium",
            "message": f"Format '{best_format[0]}' performe le mieux (score moy: {best_format[1]['avg_score']})",
            "action": f"Prioriser le format '{best_format[0]}'",
        })

    # Meilleur jour
    if day_analysis:
        best_day = max(day_analysis.items(), key=lambda x: x[1].get("avg_score", 0))
        suggestions.append({
            "type": "timing",
            "priority": "medium",
            "message": f"Meilleur jour: {best_day[0]} (score moy: {best_day[1]['avg_score']})",
            "action": f"Publier tes meilleurs contenus le {best_day[0]}",
        })

    # Tendance
    if trends.get("trend_direction") == "down" and abs(trends.get("score_change_pct", 0)) > 20:
        suggestions.append({
            "type": "alert",
            "priority": "high",
            "message": f"Engagement en baisse de {abs(trends['score_change_pct'])}% cette semaine",
            "action": "Revoir la qualite du contenu ou tester un nouveau format",
        })
    elif trends.get("trend_direction") == "up":
        suggestions.append({
            "type": "positive",
            "priority": "low",
            "message": f"Engagement en hausse de {trends.get('score_change_pct', 0)}% !",
            "action": "Continue sur cette lancee, analyse ce qui a change",
        })

    # Regularite (via tracker)
    if os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE, "r", encoding="utf-8") as f:
            tracker = json.load(f)
        posts_this_week = tracker.get("posts_this_week", 0)
        target = tracker.get("target_per_week", 3)
        if posts_this_week < target:
            suggestions.append({
                "type": "consistency",
                "priority": "high",
                "message": f"Seulement {posts_this_week}/{target} posts cette semaine",
                "action": "Publier pour maintenir la regularite",
            })

    return suggestions


# ============================================================
# GENERATION DU RAPPORT HEBDOMADAIRE
# ============================================================
def generate_weekly_report():
    """Genere le rapport hebdomadaire complet."""
    metrics_history = load_metrics_history()
    posts_metrics = metrics_history.get("posts_metrics", [])

    # Analyses
    pillar_analysis = analyze_by_dimension(posts_metrics, "pillar")
    format_analysis = analyze_by_dimension(posts_metrics, "format")
    day_analysis = analyze_by_dimension(posts_metrics, "day")
    top_worst = get_top_and_worst_posts(posts_metrics)
    trends = calculate_trends(posts_metrics)
    suggestions = generate_suggestions(pillar_analysis, format_analysis, day_analysis, trends)

    # Followers
    followers = fetch_profile_followers()

    # Construire le rapport
    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "period": f"{(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')} -> {datetime.now().strftime('%Y-%m-%d')}",
        "summary": {
            "total_posts_tracked": len(posts_metrics),
            "followers": followers,
        },
        "performance_by_pillar": pillar_analysis,
        "performance_by_format": format_analysis,
        "performance_by_day": day_analysis,
        "top_posts": top_worst["top"],
        "worst_posts": top_worst["worst"],
        "trends": trends,
        "suggestions": suggestions,
    }

    # Sauvegarder le rapport
    os.makedirs(ANALYTICS_DIR, exist_ok=True)
    report_filename = f"report_{datetime.now().strftime('%Y-%m-%d')}.json"
    report_filepath = os.path.join(ANALYTICS_DIR, report_filename)
    with open(report_filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Ajouter au historique
    metrics_history["weekly_reports"].append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "file": report_filepath,
    })
    # Garder les 52 derniers rapports
    metrics_history["weekly_reports"] = metrics_history["weekly_reports"][-52:]
    save_metrics_history(metrics_history)

    return report


# ============================================================
# AFFICHAGE DU RAPPORT
# ============================================================
def print_report(report):
    """Affiche le rapport de maniere lisible."""
    print("\n" + "=" * 60)
    print(f"  RAPPORT HEBDOMADAIRE -- {report['period']}")
    print("=" * 60)

    # Resume
    summary = report.get("summary", {})
    print(f"\n  Posts suivis: {summary.get('total_posts_tracked', 0)}")
    if summary.get("followers"):
        print(f"  Followers: {summary['followers']}")

    # Par pilier
    print(f"\n  --- PERFORMANCE PAR PILIER ---")
    for pillar, data in report.get("performance_by_pillar", {}).items():
        print(f"  {pillar:15} | {data['count']} posts | Likes moy: {data['avg_likes']} | Comments moy: {data['avg_comments']} | Score: {data['avg_score']}")

    # Par format
    print(f"\n  --- PERFORMANCE PAR FORMAT ---")
    for fmt, data in report.get("performance_by_format", {}).items():
        print(f"  {fmt:15} | {data['count']} posts | Likes moy: {data['avg_likes']} | Comments moy: {data['avg_comments']} | Score: {data['avg_score']}")

    # Par jour
    print(f"\n  --- PERFORMANCE PAR JOUR ---")
    for day, data in report.get("performance_by_day", {}).items():
        print(f"  {day:15} | {data['count']} posts | Score moy: {data['avg_score']}")

    # Top posts
    print(f"\n  --- TOP 3 POSTS ---")
    for i, post in enumerate(report.get("top_posts", [])[:3], 1):
        print(f"  #{i} [{post.get('pillar', '?')}/{post.get('format', '?')}] Score: {post.get('engagement_score', 0)} | {post.get('date', '?')}")

    # Tendances
    trends = report.get("trends", {})
    if trends.get("score_change_pct") is not None:
        direction = "+" if trends["score_change_pct"] > 0 else ""
        print(f"\n  --- TENDANCE ---")
        print(f"  Evolution: {direction}{trends['score_change_pct']}% vs semaine precedente")

    # Suggestions
    suggestions = report.get("suggestions", [])
    if suggestions:
        print(f"\n  --- SUGGESTIONS ({len(suggestions)}) ---")
        for s in suggestions:
            priority_icon = {"high": "!!!", "medium": " ! ", "low": "   "}.get(s["priority"], "   ")
            print(f"  [{priority_icon}] {s['message']}")
            print(f"        -> Action: {s['action']}")

    print("\n" + "=" * 60)


# ============================================================
# MAIN
# ============================================================
def main():
    print(f"[START] Analytics -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Mise a jour des metriques
    print("\n[1/3] Mise a jour des metriques...")
    if LINKEDIN_ACCESS_TOKEN:
        update_post_metrics()
    else:
        print("       [SIMULATE] Pas de token LinkedIn -- metriques locales uniquement")

    # Generation du rapport
    print("\n[2/3] Generation du rapport hebdomadaire...")
    report = generate_weekly_report()

    # Affichage
    print("\n[3/3] Rapport:")
    print_report(report)

    print("\n[DONE] Analytics termine.")
    print(f"       Rapport sauvegarde dans: {ANALYTICS_DIR}/")


if __name__ == "__main__":
    main()

