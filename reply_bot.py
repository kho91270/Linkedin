import requests
import json
import os
import sys
import time
import random
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ============================================================
# REPLY BOT v4.0 - Repond aux commentaires LinkedIn
# IA : Groq (GRATUIT) - Modele Llama 3.3 70B
# Ton : Professionnel + touche d'humour
# Fixes : anti-doublon, anti-troll, filtre courts, log Sheet
# ============================================================

LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
LINKEDIN_PERSON_ID = None
TRACKING_FILE = "replied_comments.json"
SHEET_ID = "1k4G-v1-nEgtE256nKUYjq-KfQd4A3CvMn03S1cp8NSE"

# FIX 5 : Max 5 reponses par run (anti-shadow ban LinkedIn)
MAX_REPLIES_PER_RUN = 5

# FIX 2 : Longueur minimum pour repondre
MIN_COMMENT_LENGTH = 15

# ============================================================
# TRACKING DES COMMENTAIRES DEJA REPONDUS
# ============================================================
def load_replied():
    if os.path.exists(TRACKING_FILE):
        with open(TRACKING_FILE, "r") as f:
            return json.load(f)
    return []

def save_replied(replied_list):
    replied_list = replied_list[-500:]
    with open(TRACKING_FILE, "w") as f:
        json.dump(replied_list, f)

# ============================================================
# CONNEXION GOOGLE SHEETS (pour log des reponses)
# ============================================================
def connect_sheets():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        return None
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SHEET_ID)

    # Creer l'onglet Replies s'il n'existe pas
    try:
        sheet = spreadsheet.worksheet("Replies")
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title="Replies", rows=500, cols=6)
        sheet.update("A1:F1", [["Date", "Post (extrait)", "Commentaire", "Reponse IA", "Langue", "Sentiment"]])

    return sheet

# FIX 7 : Log dans Google Sheet
def log_reply(sheet, post_text, comment_text, reply_text, langue, sentiment):
    if not sheet:
        return
    from datetime import datetime
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    row = [now, post_text[:80], comment_text[:120], reply_text[:200], langue, sentiment]
    sheet.append_row(row)

# ============================================================
# RECUPERATION AUTOMATIQUE ID LINKEDIN
# ============================================================
def get_my_linkedin_id():
    headers = {"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"}
    resp1 = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers)
    if resp1.status_code == 200:
        return resp1.json().get("sub")
    resp2 = requests.get("https://api.linkedin.com/v2/me", headers=headers)
    if resp2.status_code == 200:
        return resp2.json().get("id")
    print("  Impossible de recuperer l'ID LinkedIn.")
    sys.exit(1)

# ============================================================
# RECUPERER LES POSTS RECENTS
# ============================================================
def get_my_recent_posts():
    url = (
        "https://api.linkedin.com/v2/ugcPosts"
        "?q=authors"
        "&authors=List(urn%3Ali%3Aperson%3A" + LINKEDIN_PERSON_ID + ")"
        "&sortBy=LAST_MODIFIED"
        "&count=10"
    )
    headers = {"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"}
    resp = requests.get(url, headers=headers)

    if resp.status_code != 200:
        url2 = (
            "https://api.linkedin.com/rest/posts"
            "?author=urn%3Ali%3Aperson%3A" + LINKEDIN_PERSON_ID
            + "&q=author&count=10&sortBy=LAST_MODIFIED"
        )
        headers2 = {
            "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
            "LinkedIn-Version": "202401",
            "X-Restli-Protocol-Version": "2.0.0"
        }
        resp = requests.get(url2, headers2)
        if resp.status_code != 200:
            print(f"  [!] Erreur recup posts: {resp.status_code}")
            return []

    data = resp.json()
    posts = data.get("elements", [])
    print(f"  [OK] {len(posts)} posts recents trouves")
    return posts

# ============================================================
# RECUPERER LES COMMENTAIRES D'UN POST (premier niveau seulement)
# ============================================================
def get_comments(post_urn):
    encoded_urn = requests.utils.quote(post_urn, safe='')
    url = (
        "https://api.linkedin.com/v2/socialActions/"
        + encoded_urn
        + "/comments?count=50"
    )
    headers = {"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return []
    data = resp.json()
    comments = data.get("elements", [])

    # FIX 6 : Garder uniquement les commentaires de premier niveau
    first_level = []
    for c in comments:
        # Les commentaires avec parentComment sont des reponses a d'autres
        if "parentComment" not in c or not c.get("parentComment"):
            first_level.append(c)

    return first_level

# ============================================================
# EXTRAIRE L'URN DU COMMENTAIRE
# ============================================================
def get_comment_urn(comment):
    urn = comment.get("$URN", "")
    if not urn:
        urn = comment.get("urn", "")
    if not urn:
        comment_id = comment.get("id", "")
        if comment_id:
            urn = comment_id
    return urn

# ============================================================
# FIX 3 : DETECTER TROLL / NEGATIF / SPAM via Groq
# ============================================================
def analyze_sentiment(comment_text):
    """
    Analyse le sentiment du commentaire.
    Retourne: 'positive', 'neutral', 'negative', ou 'spam'
    """
    if not GROQ_API_KEY:
        return "neutral"

    prompt = (
        "Analyse ce commentaire LinkedIn et reponds UNIQUEMENT par un seul mot: "
        "positive, neutral, negative, ou spam.\n\n"
        "Regles:\n"
        "- positive = compliment, accord, experience partagee\n"
        "- neutral = question, remarque factuelle\n"
        "- negative = critique, insulte, provocation, desaccord agressif\n"
        "- spam = pub, lien suspect, hors-sujet total\n\n"
        f"Commentaire: \"{comment_text}\"\n\n"
        "Reponse (un seul mot):"
    )

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 10,
        "temperature": 0.1
    }

    try:
        resp = requests.post(url, headers=headers, json=body)
        if resp.status_code == 200:
            result = resp.json()["choices"][0]["message"]["content"].strip().lower()
            # Nettoyer la reponse
            for sentiment in ["positive", "neutral", "negative", "spam"]:
                if sentiment in result:
                    return sentiment
            return "neutral"
    except:
        pass

    return "neutral"

# ============================================================
# GENERER UNE REPONSE VIA GROQ (GRATUIT)
# ============================================================
def generate_reply(comment_text, post_context=""):
    if not GROQ_API_KEY:
        print("  [!] GROQ_API_KEY non configuree.")
        return None

    system_prompt = (
        "Tu es Mehdi Bekka, Senior Procurement Consultant base au Luxembourg. "
        "Tu reponds aux commentaires sur tes posts LinkedIn.\n\n"
        "REGLES DE TON:\n"
        "- Professionnel mais accessible\n"
        "- Touche d'humour legere quand c'est approprie (emojis avec moderation : 1-2 max)\n"
        "- Toujours apporter de la valeur ajoutee dans la reponse\n"
        "- Poser une question de suivi pour prolonger la conversation\n"
        "- Repondre dans la MEME LANGUE que le commentaire (FR si FR, EN si EN)\n"
        "- Maximum 3-4 phrases\n"
        "- Ne jamais etre condescendant ou generique\n"
        "- Montrer une vraie expertise procurement/supply chain\n"
        "- Tutoyer si le commentaire tutoie, vouvoyer sinon\n\n"
        "EXEMPLES DE BON TON:\n"
        "- Exactement ! Et le pire c'est que la plupart des equipes decouvrent ca "
        "apres la signature... Le TCO devrait etre obligatoire dans tout appel "
        "d'offres. Quel a ete ton facteur de surcout le plus inattendu ?\n"
        "- Great point! I've seen this pattern across 3 different industries. "
        "The key is starting small - one category, one supplier, one quick win. "
        "Then momentum builds itself. What was your first breakthrough?\n"
        "- Ha! Le fameux 'oui oui on fera un appel d'offres'... qui se transforme "
        "en reconduction tacite. Classic. Tu as reussi a casser ce reflexe ?\n\n"
        "INTERDITS:\n"
        "- Ne jamais commencer par 'Merci pour votre commentaire'\n"
        "- Ne jamais dire 'C est une excellente question'\n"
        "- Ne pas faire de reponse de plus de 4 phrases"
    )

    user_prompt = (
        f"Contexte du post: {post_context}\n\n"
        f"Commentaire recu: \"{comment_text}\"\n\n"
        "Genere une reponse naturelle, pro + humour leger. "
        "3-4 phrases max. Dans la meme langue que le commentaire. "
        "Ne mets pas de guillemets autour de ta reponse."
    )

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": 250,
        "temperature": 0.8
    }

    resp = requests.post(url, headers=headers, json=body)
    if resp.status_code != 200:
        print(f"  [!] Erreur Groq: {resp.status_code} - {resp.text}")
        return None

    data = resp.json()
    reply = data["choices"][0]["message"]["content"].strip()

    if reply.startswith('"') and reply.endswith('"'):
        reply = reply[1:-1]
    if reply.startswith("'") and reply.endswith("'"):
        reply = reply[1:-1]

    return reply

# ============================================================
# POSTER UNE REPONSE A UN COMMENTAIRE
# ============================================================
def post_reply(post_urn, comment_urn, reply_text):
    encoded_urn = requests.utils.quote(post_urn, safe='')
    url = (
        "https://api.linkedin.com/v2/socialActions/"
        + encoded_urn
        + "/comments"
    )
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    body = {
        "actor": f"urn:li:person:{LINKEDIN_PERSON_ID}",
        "message": {"text": reply_text},
        "parentComment": comment_urn
    }

    resp = requests.post(url, headers=headers, json=body)
    if resp.status_code in [200, 201]:
        print(f"  [OK] Reponse postee!")
        return True
    else:
        # Fallback sans parentComment
        print(f"  [!] Erreur reply (parentComment): {resp.status_code}")
        print(f"  [>] Tentative sans parentComment...")
        body2 = {
            "actor": f"urn:li:person:{LINKEDIN_PERSON_ID}",
            "message": {"text": reply_text}
        }
        resp2 = requests.post(url, headers=headers, json=body2)
        if resp2.status_code in [200, 201]:
            print(f"  [OK] Reponse postee (niveau 1)!")
            return True
        else:
            print(f"  [!] Erreur finale: {resp2.status_code} - {resp2.text}")
            return False

# ============================================================
# MAIN
# ============================================================
def main():
    global LINKEDIN_PERSON_ID

    print("=" * 50)
    print("LINKEDIN REPLY BOT v4.0 (Groq + Anti-Troll + Log)")
    print("=" * 50)

    # 1. ID LinkedIn
    LINKEDIN_PERSON_ID = get_my_linkedin_id()
    my_person_urn = f"urn:li:person:{LINKEDIN_PERSON_ID}"
    print(f"[OK] ID: {LINKEDIN_PERSON_ID}")

    # 2. Charger tracking
    replied = load_replied()
    print(f"[OK] {len(replied)} commentaires deja traites")

    # 3. Connexion Google Sheet pour log
    replies_sheet = connect_sheets()
    if replies_sheet:
        print("[OK] Connecte a Google Sheet (onglet Replies)")
    else:
        print("[!] Pas de connexion Sheet (log desactive)")

    # 4. Recuperer les posts recents
    posts = get_my_recent_posts()
    if not posts:
        print("[!] Aucun post recent trouve.")
        sys.exit(0)

    total_replies = 0

    # 5. Pour chaque post, verifier les commentaires
    for post in posts:
        post_urn = post.get("id") or post.get("urn") or ""
        post_text = ""

        specific = post.get("specificContent", {})
        if specific:
            share = specific.get("com.linkedin.ugc.ShareContent", {})
            commentary = share.get("shareCommentary", {})
            post_text = commentary.get("text", "")[:200]
        elif post.get("commentary"):
            post_text = post.get("commentary", "")[:200]

        if not post_urn:
            continue

        print(f"")
        print(f"  [POST] {post_urn[:60]}...")
        comments = get_comments(post_urn)

        if not comments:
            print(f"    Pas de commentaires.")
            continue

        print(f"    {len(comments)} commentaire(s) premier niveau")

        for comment in comments:
            if total_replies >= MAX_REPLIES_PER_RUN:
                print(f"")
                print(f"  [LIMIT] Max {MAX_REPLIES_PER_RUN} reponses atteint.")
                break

            # Ignorer nos propres commentaires
            actor = comment.get("actor", "")
            if my_person_urn in actor:
                continue

            comment_text = comment.get("message", {}).get("text", "")
            comment_urn = get_comment_urn(comment)

            if not comment_text or not comment_urn:
                continue

            # ANTI-DOUBLON
            if comment_urn in replied:
                continue

            # FIX 2 : Ignorer les commentaires trop courts
            if len(comment_text.strip()) < MIN_COMMENT_LENGTH:
                print(f"    [SKIP] Trop court ({len(comment_text)} car): \"{comment_text}\"")
                replied.append(comment_urn)  # Marquer comme traite pour ne pas re-checker
                continue

            # FIX 3 : Analyser le sentiment
            print(f"    [ANALYSE] \"{comment_text[:60]}\"...")
            sentiment = analyze_sentiment(comment_text)
            print(f"    [SENTIMENT] {sentiment}")

            # Ne pas repondre aux negatifs et spam
            if sentiment in ["negative", "spam"]:
                print(f"    [SKIP] Commentaire {sentiment} - pas de reponse")
                replied.append(comment_urn)
                # Log quand meme dans le Sheet
                langue = "FR" if any(c in comment_text for c in ["je", "le", "la", "les", "un", "une"]) else "EN"
                log_reply(replies_sheet, post_text, comment_text, "[NON REPONDU - " + sentiment + "]", langue, sentiment)
                continue

            # Generer la reponse IA
            reply = generate_reply(comment_text, post_text)
            if not reply:
                continue

            print(f"    [REPLY] \"{reply[:80]}\"")

            # Detecter la langue pour le log
            langue = "FR" if any(c in comment_text.lower() for c in [" je ", " le ", " la ", " les ", " un ", " une ", " des "]) else "EN"

            # Poster la reponse
            success = post_reply(post_urn, comment_urn, reply)
            if success:
                total_replies += 1
                replied.append(comment_urn)
                # FIX 7 : Log dans Google Sheet
                log_reply(replies_sheet, post_text, comment_text, reply, langue, sentiment)

            # FIX 5 : Delai random entre 5 et 15 secondes (anti-shadow ban)
            delay = random.randint(5, 15)
            print(f"    [WAIT] Pause {delay}s...")
            time.sleep(delay)

    # 6. Sauvegarder le tracking
    save_replied(replied)
    print(f"")
    print(f"[SAVE] Tracking mis a jour ({len(replied)} commentaires)")

    print(f"")
    print(f"{'=' * 50}")
    print(f"[DONE] {total_replies} reponse(s) postee(s)")
    print(f"{'=' * 50}")

if __name__ == "__main__":
    main()
