
"""
VEILLE.PY — Intelligence Procuretech Engine
Scanne les sources procurement, génère un brief quotidien structuré.
Stocke les résultats dans veille_briefs/ pour review avant publication.
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
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")  # newsapi.org

client = OpenAI(api_key=OPENAI_API_KEY)

# Sources RSS procurement / supply chain
RSS_FEEDS = {
    "Spend Matters": "https://spendmatters.com/feed/",
    "Procurement Magazine": "https://procurementmag.com/rss/feed",
    "Supply Chain Dive": "https://www.supplychaindive.com/feeds/news/",
    "Procurement Leaders": "https://www.procurementleaders.com/rss",
    "CPO Rising": "https://cporising.com/feed/",
    "The Hackett Group": "https://www.thehackettgroup.com/feed/",
}

# Mots-clés pour filtrer les articles pertinents
KEYWORDS = [
    "procurement", "sourcing", "achats", "spend management",
    "supplier", "fournisseur", "procuretech", "P2P",
    "purchase-to-pay", "category management", "supply chain",
    "e-procurement", "AI procurement", "procurement automation",
    "contract management", "spend analytics", "RFP", "RFI",
    "strategic sourcing", "tail spend", "Coupa", "SAP Ariba",
    "Ivalua", "Jaggaer", "Zip HQ", "Oro Labs", "Fairmarkit",
    "Levelpath", "Omnea", "GEP", "Zycus", "procurement startup",
    "funding procurement", "series A procurement", "series B procurement",
]

# Répertoire de sortie
OUTPUT_DIR = "veille_briefs"
ARCHIVE_DIR = "veille_archive"


# ============================================================
# FONCTIONS DE COLLECTE
# ============================================================
def fetch_rss_articles():
    """Récupère les articles des flux RSS des dernières 48h."""
    articles = []
    cutoff_date = datetime.now() - timedelta(hours=48)

    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:20]:
                # Parser la date de publication
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6])
                else:
                    published = datetime.now()

                if published >= cutoff_date:
                    article = {
                        "source": source_name,
                        "title": entry.get("title", ""),
                        "link": entry.get("link", ""),
                        "summary": entry.get("summary", "")[:500],
                        "published": published.isoformat(),
                    }
                    articles.append(article)
        except Exception as e:
            print(f"[WARN] Erreur RSS {source_name}: {e}")

    return articles


def fetch_news_api():
    """Récupère les news procurement via NewsAPI."""
    if not NEWS_API_KEY:
        print("[WARN] NEWS_API_KEY non configurée, skip NewsAPI")
        return []

    articles = []
    queries = [
        "procurement technology startup funding",
        "procuretech AI sourcing",
        "procurement software Series A B",
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
            print(f"[WARN] Erreur NewsAPI query '{query}': {e}")

    return articles


def fetch_crunchbase_procurement():
    """Scrape les levées de fonds procurement récentes (simulation via recherche)."""
    # Note: En production, utiliser Crunchbase API (payante) ou PitchBook
    # Ici on utilise une recherche web via un proxy gratuit
    articles = []
    try:
        url = "https://newsapi.org/v2/everything"
        if NEWS_API_KEY:
            params = {
                "q": "procurement startup raised funding million",
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 5,
                "from": (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d"),
                "apiKey": NEWS_API_KEY,
            }
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                for item in data.get("articles", []):
                    articles.append({
                        "source": "Funding Alert",
                        "title": item.get("title", ""),
                        "link": item.get("url", ""),
                        "summary": (item.get("description") or "")[:500],
                        "published": item.get("publishedAt", ""),
                    })
    except Exception as e:
        print(f"[WARN] Erreur Crunchbase fetch: {e}")

    return articles


# ============================================================
# FILTRAGE ET SCORING
# ============================================================
def score_article(article):
    """Score un article selon sa pertinence procurement."""
    text = f"{article['title']} {article['summary']}".lower()
    score = 0

    # Points pour mots-clés
    for keyword in KEYWORDS:
        if keyword.lower() in text:
            score += 2

    # Bonus pour les levées de fonds
    funding_words = ["raises", "raised", "funding", "series", "million", "lève", "levée"]
    for word in funding_words:
        if word in text:
            score += 5

    # Bonus pour startups/nouveaux outils
    startup_words = ["startup", "launch", "new platform", "announces", "unveils"]
    for word in startup_words:
        if word in text:
            score += 3

    # Bonus pour l'IA
    ai_words = ["ai", "artificial intelligence", "machine learning", "automation"]
    for word in ai_words:
        if word in text:
            score += 2

    return score


def filter_and_rank_articles(articles):
    """Filtre et classe les articles par pertinence."""
    scored = []
    for article in articles:
        score = score_article(article)
        if score >= 4:  # Seuil minimum de pertinence
            article["relevance_score"] = score
            scored.append(article)

    # Dédupliquer par titre similaire
    seen_titles = set()
    unique = []
    for article in scored:
        title_key = article["title"][:50].lower()
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique.append(article)

    # Trier par score décroissant
    unique.sort(key=lambda x: x["relevance_score"], reverse=True)
    return unique[:15]  # Top 15


# ============================================================
# GÉNÉRATION DU BRIEF
# ============================================================
def generate_brief(articles):
    """Génère un brief structuré via OpenAI."""
    if not articles:
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "status": "NO_NEWS",
            "message": "Aucun article pertinent trouvé aujourd'hui.",
        }

    articles_text = ""
    for i, art in enumerate(articles[:10], 1):
        articles_text += f"\n{i}. [{art['source']}] {art['title']}\n   {art['summary'][:200]}\n   Score: {art['relevance_score']}\n"

    prompt = f"""Tu es un analyste marché procurement/procuretech. 
Voici les articles les plus pertinents des dernières 48h :

{articles_text}

Génère un brief structuré en JSON avec les champs suivants :
{{
    "date": "YYYY-MM-DD",
    "funding_alert": {{
        "startup": "nom ou null",
        "amount": "montant ou null",
        "focus": "description courte ou null"
    }},
    "key_stat": {{
        "value": "le chiffre clé",
        "context": "explication en 1 phrase"
    }},
    "new_tool": {{
        "name": "nom de l'outil/startup ou null",
        "description": "ce qu'il fait en 1 ligne ou null"
    }},
    "hot_topic": {{
        "subject": "le sujet chaud du jour",
        "why_it_matters": "pourquoi c'est important pour un acheteur"
    }},
    "post_angles": [
        {{
            "pillar": "terrain ou analyste",
            "hook": "accroche possible pour un post LinkedIn",
            "format": "texte ou carrousel ou question"
        }},
        {{
            "pillar": "terrain ou analyste",
            "hook": "accroche possible pour un post LinkedIn",
            "format": "texte ou carrousel ou question"
        }}
    ],
    "sources": ["liste des sources utilisées"]
}}

Sois factuel. Ne fais pas de spéculation. Si un champ n'a pas d'info, mets null.
Réponds UNIQUEMENT avec le JSON, sans texte autour."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1500,
        )
        brief_text = response.choices[0].message.content.strip()
        # Nettoyer le JSON (enlever les ```json si présent)
        if brief_text.startswith("```"):
            brief_text = brief_text.split("\n", 1)[1]
        if brief_text.endswith("```"):
            brief_text = brief_text.rsplit("```", 1)[0]
        brief = json.loads(brief_text)
        brief["raw_articles"] = articles[:10]
        return brief
    except Exception as e:
        print(f"[ERROR] Génération brief: {e}")
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "status": "ERROR",
            "error": str(e),
            "raw_articles": articles[:10],
        }


# ============================================================
# SAUVEGARDE
# ============================================================
def save_brief(brief):
    """Sauvegarde le brief dans le répertoire de sortie."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"brief_{date_str}.json"

    # Sauvegarde principale
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(brief, f, ensure_ascii=False, indent=2)

    # Archive
    archive_path = os.path.join(ARCHIVE_DIR, filename)
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(brief, f, ensure_ascii=False, indent=2)

    print(f"[OK] Brief sauvegardé: {filepath}")
    return filepath


def print_brief_summary(brief):
    """Affiche un résumé lisible du brief."""
    print("\n" + "=" * 60)
    print(f"📋 BRIEF DU JOUR — {brief.get('date', 'N/A')}")
    print("=" * 60)

    if brief.get("status") == "NO_NEWS":
        print("Aucun article pertinent aujourd'hui.")
        return

    if brief.get("status") == "ERROR":
        print(f"Erreur: {brief.get('error')}")
        return

    # Funding
    funding = brief.get("funding_alert", {})
    if funding and funding.get("startup"):
        print(f"🔥 LEVÉE: {funding['startup']} — {funding.get('amount', '?')}")
        print(f"   Focus: {funding.get('focus', 'N/A')}")

    # Stat clé
    stat = brief.get("key_stat", {})
    if stat and stat.get("value"):
        print(f"📊 CHIFFRE CLÉ: {stat['value']}")
        print(f"   {stat.get('context', '')}")

    # Nouvel outil
    tool = brief.get("new_tool", {})
    if tool and tool.get("name"):
        print(f"🆕 OUTIL: {tool['name']} — {tool.get('description', '')}")

    # Hot topic
    topic = brief.get("hot_topic", {})
    if topic and topic.get("subject"):
        print(f"💬 SUJET CHAUD: {topic['subject']}")
        print(f"   Pourquoi: {topic.get('why_it_matters', '')}")

    # Angles de post
    angles = brief.get("post_angles", [])
    if angles:
        print("\n→ ANGLES DE POST POSSIBLES:")
        for angle in angles:
            print(f"  [{angle.get('pillar', '?').upper()}] [{angle.get('format', '?')}]")
            print(f"  Hook: \"{angle.get('hook', '')}\"")

    print("=" * 60 + "\n")


# ============================================================
# MAIN
# ============================================================
def main():
    print(f"[START] Veille procurement — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Collecte depuis toutes les sources
    print("[1/5] Collecte RSS...")
    rss_articles = fetch_rss_articles()
    print(f"       → {len(rss_articles)} articles RSS")

    print("[2/5] Collecte NewsAPI...")
    news_articles = fetch_news_api()
    print(f"       → {len(news_articles)} articles NewsAPI")

    print("[3/5] Collecte funding alerts...")
    funding_articles = fetch_crunchbase_procurement()
    print(f"       → {len(funding_articles)} articles funding")

    # Fusion de toutes les sources
    all_articles = rss_articles + news_articles + funding_articles
    print(f"\n[4/5] Total brut: {len(all_articles)} articles")

    # Filtrage et scoring
    top_articles = filter_and_rank_articles(all_articles)
    print(f"       → {len(top_articles)} articles après filtrage")

    # Génération du brief
    print("[5/5] Génération du brief IA...")
    brief = generate_brief(top_articles)

    # Sauvegarde
    save_brief(brief)
    print_brief_summary(brief)

    print("[DONE] Veille terminée.")


if __name__ == "__main__":
    main()

