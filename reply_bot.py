import requests
import json
import os
import sys
import time

# ============================================================
# REPLY BOT v3.0 - Repond aux commentaires LinkedIn
# IA : Groq (GRATUIT) - Modele Llama 3.3 70B
# Ton : Professionnel + touche d'humour
# Anti-doublon : tracking via fichier JSON
# ============================================================

LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
LINKEDIN_PERSON_ID = None
TRACKING_FILE = "replied_comments.json"

# ============================================================
# TRACKING DES COMMENTAIRES DEJA REPONDUS
# ============================================================
def load_replied():
    if os.path.exists(TRACKING_FILE):
        with open(TRACKING_FILE, "r") as f:
            return json.load(f)
    return []

def save_replied(replied_list):
    # Garder seulement les 500 derniers pour eviter un fichier trop gros
    replied_list = replied_list[-500:]
    with open(TRACKING_FILE, "w") as f:
        json.dump(replied_list, f)

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
        resp = requests.get(url2, headers=headers2)
        if resp.status_code != 200:
            print(f"  [!] Erreur recup posts: {resp.status_code}")
            return []

    data = resp.json()
    posts = data.get("elements", [])
    print(f"  [OK] {len(posts)} posts recents trouves")
    return posts

# ============================================================
# RECUPERER LES COMMENTAIRES D'UN POST
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
    return data.get("elements", [])

# ============================================================
# EXTRAIRE L'URN DU COMMENTAIRE (plusieurs formats possibles)
# ============================================================
def get_comment_urn(comment):
    # LinkedIn renvoie l'URN dans differents champs selon la version API
    urn = comment.get("$URN", "")
    if not urn:
        urn = comment.get("urn", "")
    if not urn:
        # Construire depuis le champ id si disponible
        comment_id = comment.get("id", "")
        if comment_id:
            urn = comment_id
    return urn

# ============================================================
# GENERER UNE REPONSE VIA GROQ (GRATUIT)
# ============================================================
def generate_reply(comment_text, post_context=""):
    if not GROQ_API_KEY:
        print("  [!] GROQ_API_KEY non configuree.")
        return None

    system_prompt = (
        "Tu es Mehdi Bekka, Senior Procurement Consultant base au Luxembourg. "
        "Tu reponds aux commentaires sur tes posts LinkedIn."
        "

"
        "REGLES DE TON:"
        "
"
        "- Professionnel mais accessible"
        "
"
        "- Touche d'humour legere quand c'est approprie (emojis avec moderation : 1-2 max)"
        "
"
        "- Toujours apporter de la valeur ajoutee dans la reponse"
        "
"
        "- Poser une question de suivi pour prolonger la conversation"
        "
"
        "- Repondre dans la MEME LANGUE que le commentaire (FR si FR, EN si EN)"
        "
"
        "- Maximum 3-4 phrases"
        "
"
        "- Ne jamais etre condescendant ou generique"
        "
"
        "- Montrer une vraie expertise procurement/supply chain"
        "
"
        "- Tutoyer si le commentaire tutoie, vouvoyer sinon"
        "

"
        "EXEMPLES DE BON TON:"
        "
"
        "- Exactement ! Et le pire c'est que la plupart des equipes decouvrent ca "
        "apres la signature... Le TCO devrait etre obligatoire dans tout appel "
        "d'offres. Quel a ete ton facteur de surcout le plus inattendu ?"
        "
"
        "- Great point! I've seen this pattern across 3 different industries. "
        "The key is starting small - one category, one supplier, one quick win. "
        "Then momentum builds itself. What was your first breakthrough?"
        "
"
        "- Ha! Le fameux 'oui oui on fera un appel d'offres'... qui se transforme "
        "en reconduction tacite. Classic. Tu as reussi a casser ce reflexe ?"
        "

"
        "INTERDITS:"
        "
"
        "- Ne jamais commencer par 'Merci pour votre commentaire'"
        "
"
        "- Ne jamais dire 'C est une excellente question'"
        "
"
        "- Ne pas faire de reponse de plus de 4 phrases"
    )

    user_prompt = (
        "Contexte du post: " + post_context
        + "

"
        + "Commentaire recu: \"" + comment_text + "\""
        + "

"
        + "Genere une reponse naturelle, pro + humour leger. "
        + "3-4 phrases max. Dans la meme langue que le commentaire. "
        + "Ne mets pas de guillemets autour de ta reponse."
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

    # Nettoyer les guillemets eventuels
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
        # Fallback : essayer sans parentComment (commentaire de premier niveau)
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
    print("LINKEDIN REPLY BOT v3.0 (Groq GRATUIT + Tracking)")
    print("=" * 50)

    # 1. ID LinkedIn
    LINKEDIN_PERSON_ID = get_my_linkedin_id()
    my_person_urn = f"urn:li:person:{LINKEDIN_PERSON_ID}"
    print(f"[OK] ID: {LINKEDIN_PERSON_ID}")

    # 2. Charger les commentaires deja traites
    replied = load_replied()
    print(f"[OK] {len(replied)} commentaires deja traites en memoire")

    # 3. Recuperer les posts recents
    posts = get_my_recent_posts()
    if not posts:
        print("[!] Aucun post recent trouve.")
        sys.exit(0)

    total_replies = 0
    max_replies_per_run = 10

    # 4. Pour chaque post, verifier les commentaires
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

        print(f"    {len(comments)} commentaire(s) trouve(s)")

        for comment in comments:
            if total_replies >= max_replies_per_run:
                print(f"")
                print(f"  [LIMIT] Max {max_replies_per_run} reponses atteint.")
                break

            # Ignorer nos propres commentaires
            actor = comment.get("actor", "")
            if my_person_urn in actor:
                continue

            comment_text = comment.get("message", {}).get("text", "")
            comment_urn = get_comment_urn(comment)

            if not comment_text or not comment_urn:
                continue

            # ANTI-DOUBLON : verifier si deja traite
            if comment_urn in replied:
                continue

            print(f"    [NEW] \"{comment_text[:80]}\"")

            # Generer la reponse IA via Groq
            reply = generate_reply(comment_text, post_text)
            if not reply:
                continue

            print(f"    [REPLY] \"{reply[:80]}\"")

            # Poster la reponse
            success = post_reply(post_urn, comment_urn, reply)
            if success:
                total_replies += 1
                replied.append(comment_urn)

            # Pause anti-spam
            time.sleep(5)

    # 5. Sauvegarder le tracking
    save_replied(replied)
    print(f"")
    print(f"[SAVE] Tracking mis a jour ({len(replied)} commentaires)")

    print(f"")
    print(f"{'=' * 50}")
    print(f"[DONE] {total_replies} reponse(s) postee(s)")
    print(f"{'=' * 50}")

if __name__ == "__main__":
    main()
