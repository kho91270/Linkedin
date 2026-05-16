import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import json
import os
from datetime import datetime

# ============================================================
# LINKEDIN ANALYTICS TRACKER
# Recupere les stats de chaque post publie
# Ecrit dans l onglet Analytics du Google Sheet
# ============================================================

LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_PERSON_ID = os.environ.get("LINKEDIN_PERSON_ID")
SHEET_ID = "1k4G-v1-nEgtE256nKUYjq-KfQd4A3CvMn03S1cp8NSE"

def connect_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID)

def get_recent_posts():
    """Recupere les 20 posts les plus recents"""
    url = "https://api.linkedin.com/v2/ugcPosts"
    params = {
        "q": "authors",
        "authors": f"List(urn:li:person:{LINKEDIN_PERSON_ID})",
        "count": 20
    }
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "X-Restli-Protocol-Version": "2.0.0"
    }

    try:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json().get("elements", [])
    except Exception as e:
        print(f"  [!] Erreur API posts: {e}")
        return []

def get_post_stats(post_urn):
    """Recupere likes, comments, shares d un post"""
    url = f"https://api.linkedin.com/v2/socialActions/{post_urn}"
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "X-Restli-Protocol-Version": "2.0.0"
    }

    stats = {"likes": 0, "comments": 0, "shares": 0}

    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            stats["likes"] = data.get("likesSummary", {}).get("totalLikes", 0)
            stats["comments"] = data.get("commentsSummary", {}).get("totalFirstLevelComments", 0)
            stats["shares"] = data.get("sharesSummary", {}).get("totalShares", 0)
    except Exception as e:
        print(f"  [!] Erreur stats {post_urn}: {e}")

    return stats

def calculate_engagement_score(stats):
    """Score pondere : comments x3, shares x5, likes x1"""
    return stats["likes"] + stats["comments"] * 3 + stats["shares"] * 5

def update_analytics_sheet(posts_data):
    """Met a jour l onglet Analytics"""
    spreadsheet = connect_sheets()

    try:
        ws = spreadsheet.worksheet("Analytics")
    except:
        ws = spreadsheet.add_worksheet(title="Analytics", rows=500, cols=10)
        ws.update("A1:J1", [["Date", "Post_URN", "Jour", "Categorie", "Likes", "Comments", "Shares", "Engagement_Score", "Top_Performer", "Action"]])

    existing = ws.get_all_values()
    next_row = len(existing) + 1

    rows = []
    for post in posts_data:
        score = calculate_engagement_score(post["stats"])
        top = "OUI" if score > 50 else ""
        action = ""
        if score > 50:
            action = "RECYCLER - fort engagement"
        elif score < 5:
            action = "ANALYSER - faible engagement"

        rows.append([
            post["date"],
            post["urn"][:50],
            post.get("jour", ""),
            post.get("categorie", ""),
            post["stats"]["likes"],
            post["stats"]["comments"],
            post["stats"]["shares"],
            score,
            top,
            action
        ])

    if rows:
        ws.update(f"A{next_row}:J{next_row + len(rows) - 1}", rows)
        print(f"  [OK] {len(rows)} posts analyses")

        # Top performer
        best = max(rows, key=lambda x: x[7])
        print(f"  [STAR] Top performer: score {best[7]} ({best[4]} likes, {best[5]} comments)")

        # Flops
        flops = [r for r in rows if r[7] < 5]
        if flops:
            print(f"  [!] {len(flops)} posts a faible engagement - a analyser")

        # Moyenne
        avg = sum(r[7] for r in rows) / len(rows)
        print(f"  [AVG] Score moyen: {avg:.1f}")

def main():
    print("=" * 50)
    print("LINKEDIN ANALYTICS TRACKER")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    posts = get_recent_posts()
    print(f"  [OK] {len(posts)} posts recuperes")

    posts_data = []
    for post in posts:
        urn = post.get("id", "")
        created = post.get("created", {}).get("time", 0)
        date = datetime.fromtimestamp(created/1000).strftime("%Y-%m-%d") if created else ""
        commentary = post.get("specificContent", {}).get("com.linkedin.ugc.ShareContent", {}).get("shareCommentary", {}).get("text", "")

        stats = get_post_stats(urn)

        posts_data.append({
            "urn": urn,
            "date": date,
            "stats": stats,
            "commentary": commentary[:50]
        })
        print(f"    {date} | L:{stats['likes']} C:{stats['comments']} S:{stats['shares']}")

    update_analytics_sheet(posts_data)

    print("")
    print("[DONE] Analytics mis a jour!")

if __name__ == "__main__":
    main()

