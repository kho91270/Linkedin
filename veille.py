import feedparser
import json
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import random

# ============================================================
# VEILLE AUTOMATIQUE PROCUREMENT
# Scan les flux RSS chaque lundi et propose des idees de posts
# ============================================================

RSS_FEEDS = [
    "https://www.supplychaindive.com/feeds/news/",
    "https://spendmatters.com/feed/",
    "https://procurementmag.com/feed",
    "https://www.cips.org/supply-management/news/rss/",
    "https://www.mckinsey.com/capabilities/operations/our-insights/rss",
]

KEYWORDS = [
    "procurement", "supply chain", "sourcing", "negotiation",
    "supplier", "ESG", "AI procurement", "nearshoring",
    "cost reduction", "risk management", "digital procurement",
    "CBAM", "scope 3", "tail spend", "category management",
    "achats", "fournisseur", "approvisionnement"
]

SHEET_ID = "1k4G-v1-nEgtE256nKUYjq-KfQd4A3CvMn03S1cp8NSE"

TEMPLATES = [
    "Hot take : {title} - voici ce que ca change pour les acheteurs",
    "Reagissez : {title}. Mon analyse en 3 points.",
    "Breaking : {title}. Impact sur votre strategie sourcing ?",
    "Trend alert : {title}. Faut-il s inquieter ou se rejouir ?",
    "Decryptage : {title}. Ce que personne ne vous dit.",
]

def connect_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID)

def fetch_news():
    """Recupere les articles recents des flux RSS"""
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:5]:
                title = entry.get("title", "")
                link = entry.get("link", "")
                summary = entry.get("summary", "")[:200]

                # Filtrer par mots-cles
                text = (title + " " + summary).lower()
                if any(kw.lower() in text for kw in KEYWORDS):
                    articles.append({
                        "title": title,
                        "link": link,
                        "summary": summary,
                        "source": feed_url.split("/")[2],
                        "date": datetime.now().strftime("%Y-%m-%d")
                    })
        except Exception as e:
            print(f"  [!] Erreur flux {feed_url}: {e}")
    return articles

def generate_post_ideas(articles):
    """Transforme les articles en idees de posts"""
    ideas = []
    for article in articles[:10]:
        template = random.choice(TEMPLATES)
        idea = template.format(title=article["title"][:60])
        ideas.append([
            article["source"],
            article["title"][:80],
            idea,
            article["link"],
            article["date"],
            ""
        ])
    return ideas

def write_to_sheet(ideas):
    """Ecrit les idees dans l onglet Veille"""
    spreadsheet = connect_sheets()

    try:
        ws = spreadsheet.worksheet("Veille")
    except:
        ws = spreadsheet.add_worksheet(title="Veille", rows=500, cols=6)
        ws.update("A1:F1", [["Source", "Sujet", "Hook Propose", "Lien", "Date", "Utilise"]])

    existing = ws.get_all_values()
    next_row = len(existing) + 1

    if ideas:
        ws.update(f"A{next_row}:F{next_row + len(ideas) - 1}", ideas)
        print(f"  [OK] {len(ideas)} nouvelles idees ajoutees (lignes {next_row}-{next_row + len(ideas) - 1})")
    else:
        print(f"  [!] Aucune nouvelle idee trouvee cette semaine")

def main():
    print("=" * 50)
    print("VEILLE PROCUREMENT AUTOMATIQUE")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    articles = fetch_news()
    print(f"  [OK] {len(articles)} articles pertinents trouves")

    ideas = generate_post_ideas(articles)
    print(f"  [OK] {len(ideas)} idees de posts generees")

    write_to_sheet(ideas)

    print("")
    print("[DONE] Veille terminee!")

if __name__ == "__main__":
    main()

