# breaking_news.py - Detection de news urgentes procuretech

import os
import json
import requests
import feedparser
import base64
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from groq import Groq
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS")
SMTP_EMAIL = os.environ.get("SMTP_EMAIL")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL")

client = Groq(api_key=GROQ_API_KEY)
GROQ_MODEL = "llama-3.3-70b-versatile"

PENDING_DIR = "pending_approval"
BREAKING_LOG = "breaking_news_log.json"

BREAKING_KEYWORDS = [
    "raises", "raised", "funding", "series A", "series B", "series C",
    "acquired", "acquisition", "merger", "IPO", "unicorn",
    "million", "billion", "leve", "levee de fonds",
    "partnership", "launches", "unveils",
]

PROCURETECH_COMPANIES = [
    "Coupa", "SAP Ariba", "Ivalua", "Jaggaer", "Zip HQ", "Zip",
    "Oro Labs", "Fairmarkit", "Levelpath", "Omnea", "GEP", "Zycus",
    "Globality", "Scoutbee", "Keelvar", "Pactum", "Arkestro",
    "Focal Point", "Procurify", "Precoro", "Order.co",
    "Sievo", "SpendHQ", "Simfoni", "Tradeshift",
    "Basware", "Medius", "Tipalti", "Brex", "Ramp",
]

RSS_BREAKING = {
    "TechCrunch": "https://techcrunch.com/feed/",
    "Spend Matters": "https://spendmatters.com/feed/",
}


def load_breaking_log():
    if os.path.exists(BREAKING_LOG):
        with open(BREAKING_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"alerts_sent": []}


def save_breaking_log(log):
    with open(BREAKING_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def send_breaking_email(to_email, subject, body_text):
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
        except Exception:
            pass
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
        except Exception:
            pass
    return False


def is_breaking_news(article):
    text = (article.get("title", "") + " " + article.get("summary", "")).lower()
    breaking_score = 0
    matched_company = None
    for company in PROCURETECH_COMPANIES:
        if company.lower() in text:
            matched_company = company
            breaking_score += 10
            break
    if not matched_company:
        if any(word in text for word in ["procurement", "sourcing", "procuretech", "spend management"]):
            breaking_score += 3
        else:
            return None
    for keyword in BREAKING_KEYWORDS:
        if keyword.lower() in text:
            breaking_score += 5
    if breaking_score >= 13:
        return {"score": breaking_score, "company": matched_company, "article": article}
    return None


def scan_for_breaking():
    breaking_items = []
    cutoff = datetime.now() - timedelta(hours=6)
    for source, url in RSS_BREAKING.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])
                else:
                    published = datetime.now()
                if published < cutoff:
                    continue
                article = {
                    "source": source,
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "summary": entry.get("summary", "")[:500],
                    "published": published.isoformat(),
                }
                result = is_breaking_news(article)
                if result:
                    breaking_items.append(result)
        except Exception as e:
            print("[WARN] RSS " + source + ": " + str(e))
    if NEWS_API_KEY:
        try:
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": "procurement OR procuretech OR sourcing funding OR acquisition",
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 15,
                "from": (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S"),
                "apiKey": NEWS_API_KEY,
            }
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 200:
                for item in r.json().get("articles", []):
                    article = {
                        "source": item.get("source", {}).get("name", "NewsAPI"),
                        "title": item.get("title", ""),
                        "link": item.get("url", ""),
                        "summary": (item.get("description") or "")[:500],
                        "published": item.get("publishedAt", ""),
                    }
                    result = is_breaking_news(article)
                    if result:
                        breaking_items.append(result)
        except Exception as e:
            print("[WARN] NewsAPI breaking: " + str(e))
    breaking_items.sort(key=lambda x: x["score"], reverse=True)
    return breaking_items[:3]


def generate_breaking_post(breaking_item):
    article = breaking_item["article"]
    company = breaking_item.get("company", "une entreprise procuretech")
    prompt_fr = (
        "Tu es Mehdi, Category Manager en procurement. Une NEWS URGENTE vient de tomber.\n\n"
        "NEWS:\n"
        "Titre: " + article["title"] + "\n"
        "Resume: " + article["summary"] + "\n"
        "Source: " + article["source"] + "\n"
        "Entreprise: " + company + "\n\n"
        "Ecris un post LinkedIn REACTIF en FRANCAIS:\n"
        "- Hook percutant qui montre que tu es au courant AVANT tout le monde\n"
        "- Ton analyse rapide en tant que praticien\n"
        "- Ce que ca change concretement pour un acheteur\n"
        "- Question ouverte\n"
        "- 3-5 hashtags\n"
        "- 800-1200 chars max\n\n"
        "Ecris UNIQUEMENT le post."
    )
    prompt_en = (
        "You are Mehdi, a Category Manager in procurement. BREAKING NEWS just dropped.\n\n"
        "NEWS:\n"
        "Title: " + article["title"] + "\n"
        "Summary: " + article["summary"] + "\n"
        "Source: " + article["source"] + "\n"
        "Company: " + company + "\n\n"
        "Write a REACTIVE LinkedIn post in ENGLISH:\n"
        "- Punchy hook showing you are ahead of the curve\n"
        "- Your quick analysis as a practitioner\n"
        "- What this concretely changes for a buyer\n"
        "- Open question\n"
        "- 3-5 hashtags\n"
        "- 800-1200 chars max\n\n"
        "Write ONLY the post."
    )
    try:
        resp_fr = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt_fr}],
            temperature=0.8,
            max_tokens=1200,
        )
        resp_en = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt_en}],
            temperature=0.8,
            max_tokens=1200,
        )
        return {
            "content_fr": resp_fr.choices[0].message.content.strip(),
            "content_en": resp_en.choices[0].message.content.strip(),
            "pillar": "analyste",
            "format": "breaking",
            "status": "pending_approval",
            "lang": "both",
            "source": "breaking_news",
            "news_title": article["title"],
            "news_link": article["link"],
            "news_company": company,
            "generated_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    except Exception as e:
        print("[ERROR] Generation breaking: " + str(e))
        return None


def main():
    print("[START] Breaking News Scanner -- " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    log = load_breaking_log()
    already_sent = [a.get("title", "") for a in log.get("alerts_sent", [])]
    print("[1/3] Scan des sources...")
    breaking = scan_for_breaking()
    print("       -> " + str(len(breaking)) + " breaking news detectees")
    if not breaking:
        print("[DONE] Rien d urgent.")
        return
    new_breaking = [b for b in breaking if b["article"]["title"] not in already_sent]
    if not new_breaking:
        print("[DONE] Deja traite.")
        return
    print("[2/3] Generation post pour: " + new_breaking[0]["article"]["title"][:60] + "...")
    item = new_breaking[0]
    post = generate_breaking_post(item)
    if not post:
        print("[ERROR] Echec generation")
        return
    os.makedirs(PENDING_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d_%H%M")
    filename = "pending_" + date_str + "_breaking.json"
    with open(os.path.join(PENDING_DIR, filename), "w", encoding="utf-8") as f:
        json.dump(post, f, ensure_ascii=False, indent=2)
    if NOTIFY_EMAIL:
        body = (
            "BREAKING NEWS PROCURETECH - POST A PUBLIER RAPIDEMENT\n\n"
            "News: " + item["article"]["title"] + "\n"
            "Source: " + item["article"]["source"] + "\n"
            "Lien: " + item["article"]["link"] + "\n\n"
            "=" * 40 + "\n"
            "VERSION FRANCAISE\n"
            "=" * 40 + "\n"
            + post["content_fr"] + "\n\n"
            + "=" * 40 + "\n"
            "ENGLISH VERSION\n"
            "=" * 40 + "\n"
            + post["content_en"] + "\n\n"
            + "=" * 40 + "\n"
            "Reponds OK pour publier / SKIP pour ignorer"
        )
        send_breaking_email(NOTIFY_EMAIL, "[LinkedIn URGENT] Breaking: " + str(item.get("company", "Procuretech")), body)
    log["alerts_sent"].append({
        "title": item["article"]["title"],
        "company": item.get("company"),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    log["alerts_sent"] = log["alerts_sent"][-50:]
    save_breaking_log(log)
    print("[DONE] Alerte envoyee.")


if __name__ == "__main__":
    main()
