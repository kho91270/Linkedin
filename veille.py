
"""
VEILLE.PY — Intelligence Procuretech Engine
Scanne les sources procurement automatiquement.
Genere un brief quotidien pour alimenter la redaction.
"""

import os
import json
import requests
import feedparser
from datetime import datetime, timedelta
from openai import OpenAI

# ============================================================
# CONFIGURATION
# ============================================================
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

RSS_FEEDS = {
    "Spend Matters": "https://spendmatters.com/feed/",
    "Procurement Magazine": "https://procurementmag.com/rss/feed",
    "Supply Chain Dive": "https://www.supplychaindive.com/feeds/news/",
    "CPO Rising": "https://cporising.com/feed/",
}

KEYWORDS = [
    "procurement", "sourcing", "achats", "spend management",
    "supplier", "fournisseur", "procuretech", "P2P",
    "category management", "supply chain", "AI procurement",
    "procurement automation", "contract management", "spend analytics",
    "RFP", "RFI", "strategic sourcing", "tail spend",
    "Coupa", "SAP Ariba", "Ivalua", "Jaggaer", "Zip HQ",
    "Oro Labs", "Fairmarkit", "Levelpath", "Omnea", "GEP", "Zycus",
    "procurement startup", "funding procurement", "series A procurement",
]

OUTPUT_DIR = "veille_briefs"
ARCHIVE_DIR = "veille_archive"


# ============================================================
# COLLECTE
# ============================================================
def fetch_rss_articles():
    """Recupere les articles RSS des 48 dernieres heures."""
    articles = []
    cutoff = datetime.now() - timedelta(hours=48)

    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:20]:
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6])
                else:
                    published = datetime.now()

                if published >= cutoff:
                    articles.append({
                        "source": source_name,
                        "title": entry.get("title", ""),
                        "link": entry.get("link", ""),
                        "summary": entry.get("summary", "")[:500],
                        "published": published.isoformat(),
                    })
        except Exception as e:
            print(f"[WARN] RSS {source_name}: {e}")

    return articles


def fetch_news_api():
    """Recupere les news via NewsAPI."""
    if not NEWS_API_KEY:
        return []

    articles = []
    queries = [
        "procurement technology startup funding",
        "procuretech AI sourcing automation",
        "procurement software Series funding",
    ]

    for query in queries:
        try:
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 10,
                "from": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
                "apiKey": NEWS_API_KEY,
            }
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                for item in data.get("articles", []):
                    articles.append({
                        "source": item.get("source", {}).get("name", "NewsAPI"),
                        "title": item.get("title", ""),
                        "link": item.get("url", ""),
                        "summary": (item.get("description") or "")[:500],
                        "published": item.get("publishedAt", ""),
                    })
        except Exception as e:
            print(f"[WARN] NewsAPI: {e}")

    return articles


# ============================================================
# SCORING & FILTRAGE
# ============================================================
def score_article(article):
    """Score de pertinence procurement."""
    text = f"{article['title']} {article['summary']}".lower()
    score = 0

    for keyword in KEYWORDS:
        if keyword.lower() in text:
            score += 2

    funding_words = ["raises", "raised", "funding", "series", "million", "leve", "levee"]
    for word in funding_words:
        if word in text:
            score += 5

    startup_words = ["startup", "launch", "new platform", "announces", "unveils"]
    for word in startup_words:
        if word in text:
            score += 3

    ai_words = ["ai", "artificial intelligence", "machine learning", "automation"]
    for word in ai_words:
        if word in text:
            score += 2

    return score


def filter_and_rank(articles):
    """Filtre et classe par pertinence."""
    scored = []
    for article in articles:
        s = score_article(article)
        if s >= 4:
            article["relevance_score"] = s
            scored.append(article)

    seen = set()
    unique = []
    for a in scored:
        key = a["title"][:50].lower()
        if key not in seen:
            seen.add(key)
            unique.append(a)

    unique.sort(key=lambda x: x["relevance_score"], reverse=True)
    return unique[:15]


# ============================================================
# GENERATION DU BRIEF
# ============================================================
def generate_brief(articles):
    """Genere un brief structure via OpenAI."""
    if not articles:
        return {"date": datetime.now().strftime("%Y-%m-%d"), "status": "NO_NEWS"}

    articles_text = ""
    for i, art in enumerate(articles[:10], 1):
        articles_text += f"\n{i}. [{art['source']}] {art['title']}\n   {art['summary'][:200]}\n"

    prompt = f"""Tu es un analyste marche procurement/procuretech.
Voici les articles pertinents des 48 dernieres heures:

{articles_text}

Genere un brief en JSON:
{{
    "date": "YYYY-MM-DD",
    "funding_alert": {{"startup": "nom ou null", "amount": "montant ou null", "focus": "description ou null"}},
    "key_stat": {{"value": "chiffre cle", "context": "explication 1 phrase"}},
    "new_tool": {{"name": "nom ou null", "description": "1 ligne ou null"}},
    "hot_topic": {{"subject": "sujet chaud", "why_it_matters": "importance pour un acheteur"}},
    "post_angles": [
        {{"pillar": "terrain ou analyste", "hook": "accroche LinkedIn", "format": "texte ou carrousel ou question"}},
        {{"pillar": "terrain ou analyste", "hook": "accroche LinkedIn", "format": "texte ou carrousel ou question"}}
    ],
    "sources": ["liste des sources"]
}}

Reponds UNIQUEMENT avec le JSON."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1500,
        )
        text = response.choices[0].message.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        brief = json.loads(text)
        brief["raw_articles"] = articles[:10]
        return brief
    except Exception as e:
        print(f"[ERROR] Brief generation: {e}")
        return {"date": datetime.now().strftime("%Y-%m-%d"), "status": "ERROR", "error": str(e), "raw_articles": articles[:10]}


# ============================================================
# SAUVEGARDE
# ============================================================
def save_brief(brief):
    """Sauvegarde le brief."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"brief_{date_str}.json"

    for directory in [OUTPUT_DIR, ARCHIVE_DIR]:
        filepath = os.path.join(directory, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(brief, f, ensure_ascii=False, indent=2)

    print(f"[OK] Brief sauvegarde: {OUTPUT_DIR}/{filename}")
    return os.path.join(OUTPUT_DIR, filename)


# ============================================================
# MAIN
# ============================================================
def main():
    print(f"[START] Veille -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    print("[1/4] Collecte RSS...")
    rss = fetch_rss_articles()
    print(f"       -> {len(rss)} articles RSS")

    print("[2/4] Collecte NewsAPI...")
    news = fetch_news_api()
    print(f"       -> {len(news)} articles NewsAPI")

    print("[3/4] Filtrage et scoring...")
    all_articles = rss + news
    top = filter_and_rank(all_articles)
    print(f"       -> {len(top)} articles retenus")

    print("[4/4] Generation du brief...")
    brief = generate_brief(top)
    save_brief(brief)

    print("[DONE] Veille terminee.")


if __name__ == "__main__":
    main()

