
"""
RECYCLER.PY — Content Rotator Intelligent
Identifie les posts recyclables, les transforme avec un nouvel angle,
et les remet dans la queue de publication.
"""

import os
import json
import random
from datetime import datetime, timedelta
from openai import OpenAI

# ============================================================
# CONFIGURATION
# ============================================================
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

PUBLISHED_DIR = "published_posts"
QUEUE_FILE = "content_queue.json"
RECYCLED_LOG = "recycled_log.json"

# Delais minimums avant recyclage (en jours)
RECYCLE_DELAYS = {
    "terrain": 90,
    "analyste": 60,
    "conversation": 45,
    "insight": 45,
}

# Transformations possibles par format
FORMAT_TRANSFORMS = {
    "texte": ["carrousel", "question", "insight"],
    "carrousel": ["texte", "insight"],
    "question": ["texte", "carrousel"],
    "insight": ["texte", "carrousel"],
}


# ============================================================
# CHARGEMENT DES DONNEES
# ============================================================
def load_published_posts():
    """Charge tous les posts publies."""
    posts = []
    if not os.path.exists(PUBLISHED_DIR):
        return posts

    for filename in os.listdir(PUBLISHED_DIR):
        if filename.endswith(".json"):
            filepath = os.path.join(PUBLISHED_DIR, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                post = json.load(f)
                post["_filename"] = filename
                posts.append(post)

    return posts


def load_recycled_log():
    """Charge le log des posts deja recycles."""
    if os.path.exists(RECYCLED_LOG):
        with open(RECYCLED_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"recycled": [], "blacklist": []}


def save_recycled_log(log):
    """Sauvegarde le log."""
    with open(RECYCLED_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def load_queue():
    """Charge la queue de contenu."""
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_queue(queue):
    """Sauvegarde la queue."""
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


# ============================================================
# IDENTIFICATION DES POSTS RECYCLABLES
# ============================================================
def is_recyclable(post, recycled_log):
    """Determine si un post est recyclable."""
    published_date = post.get("published_date")
    if not published_date:
        return False, "pas de date"

    # Verifier le delai minimum
    try:
        pub_date = datetime.strptime(published_date, "%Y-%m-%d")
    except ValueError:
        return False, "date invalide"

    pillar = post.get("pillar", "terrain")
    min_delay = RECYCLE_DELAYS.get(pillar, 90)
    days_since = (datetime.now() - pub_date).days

    if days_since < min_delay:
        return False, f"trop recent ({days_since}j < {min_delay}j)"

    # Verifier si deja recycle
    filename = post.get("_filename", "")
    already_recycled = any(
        r.get("original_filename") == filename
        for r in recycled_log.get("recycled", [])
    )
    if already_recycled:
        return False, "deja recycle"

    # Verifier la blacklist
    if filename in recycled_log.get("blacklist", []):
        return False, "blackliste"

    # Post doit avoir du contenu suffisant
    if not post.get("content") or len(post.get("content", "")) < 100:
        return False, "contenu insuffisant"

    return True, f"recyclable ({days_since}j)"


def find_recyclable_posts():
    """Trouve tous les posts prets a etre recycles."""
    posts = load_published_posts()
    recycled_log = load_recycled_log()
    recyclable = []

    for post in posts:
        can_recycle, reason = is_recyclable(post, recycled_log)
        if can_recycle:
            recyclable.append(post)
            print(f"  [OK] {post.get('_filename', '?')} -- {reason}")

    return recyclable


# ============================================================
# TRANSFORMATION DU CONTENU
# ============================================================
def determine_new_format(original_format):
    """Determine le nouveau format pour le recyclage."""
    options = FORMAT_TRANSFORMS.get(original_format, ["texte"])
    return random.choice(options)


def recycle_post(post, new_format=None):
    """Recycle un post avec un nouvel angle et/ou format."""
    original_content = post.get("content", "")
    original_pillar = post.get("pillar", "terrain")
    original_format = post.get("format", "texte")
    published_date = post.get("published_date", "2025-01-01")

    if not new_format:
        new_format = determine_new_format(original_format)

    # Calculer le nombre de jours depuis publication
    try:
        days_ago = (datetime.now() - datetime.strptime(published_date, "%Y-%m-%d")).days
    except ValueError:
        days_ago = 90

    # Strategies de recyclage par pilier
    strategies = {
        "terrain": [
            "Meme histoire mais focus sur UNE seule lecon differente",
            "Transformer en conseil actionnable (framework/checklist)",
            "Prendre le contre-pied : qu'est-ce qui aurait pu mal tourner ?",
            "Contextualiser avec une actualite recente du secteur",
            "Generaliser la lecon : de mon cas specifique a un principe universel",
        ],
        "analyste": [
            "Update avec des nouvelles informations (levee, pivot, acquisition)",
            "Comparer avec un concurrent ou une alternative",
            "Donner ton retour apres X mois d'observation",
            "Elargir l'analyse a un trend plus large",
            "Prendre position : est-ce que ta prediction s'est verifiee ?",
        ],
        "conversation": [
            "Reformuler la question avec un nouveau contexte",
            "Transformer les meilleures reponses en post de synthese",
            "Prendre position : donner TA reponse cette fois",
            "Ajouter un sondage avec des options concretes",
        ],
        "insight": [
            "Developper l'insight en post terrain complet avec une histoire",
            "Transformer en carrousel avec exemples concrets",
            "Combiner avec un autre insight pour un post plus riche",
            "Illustrer avec un cas reel recent",
        ],
    }

    strategy_options = strategies.get(original_pillar, strategies["terrain"])
    chosen_strategy = random.choice(strategy_options)

    # Instructions par format de sortie
    format_instructions = {
        "texte": """Post texte LinkedIn (800-1500 caracteres).
Structure HVIA: Hook (1 ligne choc < 150 chars) -> Vecu/Contexte (3-5 lignes) -> Insight (la lecon) -> Appel (question ouverte)
Aere avec des sauts de ligne. Max 3 emojis. 3-5 hashtags a la fin.""",
        "carrousel": """Texte pour un carrousel LinkedIn (slide par slide).
Format OBLIGATOIRE:
SLIDE 1: [titre hook percutant - max 10 mots]
SLIDE 2: [le probleme ou la question]
SLIDE 3: [point 1]
SLIDE 4: [point 2]
SLIDE 5: [point 3]
SLIDE 6: [recap / synthese]
SLIDE 7: [CTA - question ouverte + "Enregistre ce post"]
Chaque slide = 1-3 phrases max. Phrases courtes et percutantes.""",
        "question": """Post court (300-600 caracteres) qui pose une question ouverte engageante.
Structure: 2-3 lignes de contexte personnel + LA question + 3-5 hashtags.
La question doit etre polarisante ou faire reflechir.""",
        "insight": """Post tres court (200-400 caracteres).
Structure: 1 phrase de contexte + 1 lecon percutante (en gras possible) + 1 question courte.
3-5 hashtags a la fin. Max 1 emoji.""",
    }

    prompt = f"""Tu es Mehdi, Category Manager en procurement, expert LinkedIn.
Tu dois RECYCLER un ancien post avec un nouvel angle COMPLETEMENT DIFFERENT.

POST ORIGINAL (publie il y a {days_ago} jours):
---
{original_content}
---

STRATEGIE DE RECYCLAGE:
"{chosen_strategy}"

NOUVEAU FORMAT: {new_format}
INSTRUCTIONS FORMAT:
{format_instructions.get(new_format, format_instructions['texte'])}

REGLES STRICTES:
- Le nouveau post doit etre TRES DIFFERENT de l'original (pas une simple reformulation)
- Garder le meme sujet/theme mais avec un NOUVEL ANGLE selon la strategie
- Ecrire a la premiere personne (je suis Mehdi, Category Manager)
- Ton professionnel mais humain, direct, pas de bullshit corporate
- Ne JAMAIS copier des phrases de l'original
- Le lecteur ne doit PAS reconnaitre que c'est un recyclage

Ecris UNIQUEMENT le nouveau post. Rien d'autre autour."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85,
            max_tokens=1500,
        )
        new_content = response.choices[0].message.content.strip()

        recycled_post = {
            "content": new_content,
            "pillar": original_pillar,
            "format": new_format,
            "status": "ready",
            "source": "recycled",
            "original_filename": post.get("_filename", ""),
            "original_date": post.get("published_date", ""),
            "recycle_strategy": chosen_strategy,
            "recycled_date": datetime.now().strftime("%Y-%m-%d"),
        }
        return recycled_post

    except Exception as e:
        print(f"[ERROR] Recyclage: {e}")
        return None


# ============================================================
# AJOUT A LA QUEUE
# ============================================================
def add_to_queue(recycled_post):
    """Ajoute le post recycle a la queue de publication."""
    queue = load_queue()
    queue.append(recycled_post)
    save_queue(queue)
    return len(queue)


# ============================================================
# MAIN
# ============================================================
def main():
    print(f"[START] Recycler -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Trouver les posts recyclables
    print("\n[1/3] Recherche des posts recyclables...")
    recyclable = find_recyclable_posts()
    print(f"       -> {len(recyclable)} posts recyclables trouves")

    if not recyclable:
        print("[DONE] Aucun post a recycler pour le moment.")
        return

    # Recycler les meilleurs candidats (max 2 par execution)
    print("\n[2/3] Recyclage en cours...")
    recycled_log = load_recycled_log()
    recycled_count = 0
    max_recycle = 2

    for post in recyclable[:max_recycle]:
        print(f"\n  --- Recyclage de: {post.get('_filename', '?')}")
        print(f"  Original: pilier={post.get('pillar', '?')} | format={post.get('format', '?')}")
        print(f"  Preview: {post.get('content', '')[:80]}...")

        new_format = determine_new_format(post.get("format", "texte"))
        print(f"  Nouveau format: {new_format}")

        recycled_post = recycle_post(post, new_format)
        if recycled_post:
            # Ajouter a la queue
            queue_size = add_to_queue(recycled_post)
            print(f"  [OK] Ajoute a la queue (taille queue: {queue_size})")
            print(f"  Nouveau post preview: {recycled_post['content'][:100]}...")

            # Logger le recyclage
            recycled_log["recycled"].append({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "original_filename": post.get("_filename", ""),
                "original_date": post.get("published_date", ""),
                "new_format": new_format,
                "strategy": recycled_post.get("recycle_strategy", ""),
            })
            recycled_count += 1
        else:
            print(f"  [FAIL] Echec du recyclage")

    # Sauvegarder le log
    save_recycled_log(recycled_log)

    # Resume
    print(f"\n[3/3] Resume")
    print(f"       Posts recycles cette session: {recycled_count}/{max_recycle}")
    print(f"       Total recycles (historique): {len(recycled_log['recycled'])}")
    print(f"       Posts encore recyclables: {len(recyclable) - recycled_count}")
    print("[DONE] Recycler termine.")


if __name__ == "__main__":
    main()

