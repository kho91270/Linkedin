
"""
BOT.PY — Publication Manager Intelligent
Gère la file de contenu, l'alternance des piliers, et la publication sur LinkedIn.
Publie le prochain post en queue aux créneaux optimaux.
"""

import os
import json
import requests
from datetime import datetime, timedelta
from openai import OpenAI

# ============================================================
# CONFIGURATION
# ============================================================
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_PERSON_ID = os.environ.get("LINKEDIN_PERSON_ID")  # Format: "urn:li:person:XXXXX"

client = OpenAI(api_key=OPENAI_API_KEY)

# Fichiers de données
QUEUE_FILE = "content_queue.json"
TRACKER_FILE = "tracker.json"
PUBLISHED_DIR = "published_posts"
BRIEF_DIR = "veille_briefs"

# Configuration des piliers
PILLAR_SCHEDULE = {
    # semaine paire
    "even": {
        "Tuesday": "terrain",
        "Thursday": "analyste",
        "Saturday": "conversation",
    },
    # semaine impaire
    "odd": {
        "Tuesday": "analyste",
        "Thursday": "terrain",
        "Saturday": "insight",
    },
}

# Hashtags par pilier
HASHTAGS = {
    "terrain": "#Procurement #Achats #CategoryManagement #SupplyChain #NégociationAchats",
    "analyste": "#Procuretech #AIprocurement #InnovationAchats #StartupTech #DigitalProcurement",
    "conversation": "#Procurement #Achats #Débat #CommunautéAchats",
    "insight": "#Procurement #LeçonDuJour #Achats #Leadership",
}


# ============================================================
# TRACKER DE PUBLICATION
# ============================================================
def load_tracker():
    """Charge le tracker de publication."""
    default_tracker = {
        "total_posts": 0,
        "current_streak": 0,
        "last_post_date": None,
        "last_pillar": None,
        "next_pillar": "terrain",
        "queue_size": 0,
        "posts_this_week": 0,
        "target_per_week": 3,
        "week_start": datetime.now().strftime("%Y-%m-%d"),
        "history": [],
    }
    if os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE, "r", encoding="utf-8") as f:
            tracker = json.load(f)
            # Remplir les champs manquants
            for key, value in default_tracker.items():
                if key not in tracker:
                    tracker[key] = value
            return tracker
    return default_tracker


def save_tracker(tracker):
    """Sauvegarde le tracker."""
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(tracker, f, ensure_ascii=False, indent=2)


def update_tracker_after_publish(tracker, post):
    """Met à jour le tracker après une publication."""
    today = datetime.now().strftime("%Y-%m-%d")
    tracker["total_posts"] += 1
    tracker["last_post_date"] = today
    tracker["last_pillar"] = post.get("pillar", "terrain")
    tracker["posts_this_week"] += 1

    # Streak
    if tracker.get("last_post_date"):
        last_date = datetime.strptime(tracker["last_post_date"], "%Y-%m-%d")
        if (datetime.now() - last_date).days <= 4:
            tracker["current_streak"] += 1
        else:
            tracker["current_streak"] = 1
    else:
        tracker["current_streak"] = 1

    # Reset compteur hebdo si nouvelle semaine
    week_start = tracker.get("week_start", today)
    if datetime.strptime(week_start, "%Y-%m-%d").isocalendar()[1] != datetime.now().isocalendar()[1]:
        tracker["posts_this_week"] = 1
        tracker["week_start"] = today

    # Historique (garder les 100 derniers)
    tracker["history"].append({
        "date": today,
        "pillar": post.get("pillar"),
        "format": post.get("format"),
        "hook": post.get("content", "")[:80],
    })
    tracker["history"] = tracker["history"][-100:]

    return tracker


# ============================================================
# FILE DE CONTENU
# ============================================================
def load_queue():
    """Charge la file de contenu."""
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_queue(queue):
    """Sauvegarde la file de contenu."""
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


def get_next_post(queue, target_pillar):
    """Récupère le prochain post à publier selon le pilier attendu."""
    # Chercher d'abord un post du bon pilier
    for i, post in enumerate(queue):
        if post.get("pillar") == target_pillar and post.get("status") == "ready":
            return i, post

    # Sinon prendre le premier post prêt
    for i, post in enumerate(queue):
        if post.get("status") == "ready":
            return i, post

    return None, None


def determine_today_pillar():
    """Détermine le pilier du jour selon le calendrier."""
    now = datetime.now()
    day_name = now.strftime("%A")
    week_number = now.isocalendar()[1]
    week_type = "even" if week_number % 2 == 0 else "odd"

    schedule = PILLAR_SCHEDULE.get(week_type, {})
    return schedule.get(day_name, None)


# ============================================================
# QUALITÉ DU POST
# ============================================================
def quality_check(post):
    """Vérifie la qualité d'un post avant publication."""
    content = post.get("content", "")
    issues = []

    # Vérifications
    if not content:
        issues.append("Contenu vide")
        return False, issues

    lines = content.strip().split("\n")
    first_line = lines[0] if lines else ""

    # Accroche
    if len(first_line) > 150:
        issues.append(f"Accroche trop longue ({len(first_line)} chars, max 150)")

    # Longueur totale
    if len(content) < 200:
        issues.append("Post trop court (< 200 chars)")
    if len(content) > 3000:
        issues.append("Post trop long (> 3000 chars)")

    # CTA (question ou appel à l'action)
    last_lines = "\n".join(lines[-5:]).lower()
    cta_indicators = ["?", "partagez", "commentez", "et vous", "qu'en pensez",
                      "votre avis", "dites-moi", "tag", "enregistre"]
    has_cta = any(indicator in last_lines for indicator in cta_indicators)
    if not has_cta:
        issues.append("Pas de CTA détecté (question ou appel)")

    # Hashtags
    hashtag_count = content.count("#")
    if hashtag_count == 0:
        issues.append("Aucun hashtag")
    elif hashtag_count > 7:
        issues.append(f"Trop de hashtags ({hashtag_count}, max 5-7)")

    # Résultat
    is_valid = len(issues) == 0
    return is_valid, issues


def enhance_post_if_needed(post):
    """Améliore un post via IA si le quality check échoue."""
    is_valid, issues = quality_check(post)
    if is_valid:
        return post

    print(f"[ENHANCE] Problèmes détectés: {issues}")

    prompt = f"""Tu es un expert LinkedIn spécialisé en procurement/achats.
Voici un post qui a des problèmes: {issues}

POST ORIGINAL:
{post['content']}

PILIER: {post.get('pillar', 'terrain')}

Corrige les problèmes identifiés en gardant le même message et le même ton.
Règles :
- Accroche < 150 caractères (première ligne percutante)
- Longueur entre 200 et 2500 caractères
- Termine par une question ouverte (CTA)
- Ajoute 3-5 hashtags pertinents à la fin
- Écris à la première personne
- Ton professionnel mais humain
- Pas de emojis excessifs (max 3-4 dans tout le post)

Réponds UNIQUEMENT avec le post corrigé, rien d'autre."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500,
        )
        enhanced_content = response.choices[0].message.content.strip()
        post["content"] = enhanced_content
        post["enhanced"] = True
        print("[OK] Post amélioré par IA")
    except Exception as e:
        print(f"[WARN] Échec amélioration: {e}")

    return post


# ============================================================
# PUBLICATION LINKEDIN
# ============================================================
def publish_to_linkedin(post):
    """Publie un post texte sur LinkedIn via l'API officielle."""
    if not LINKEDIN_ACCESS_TOKEN or not LINKEDIN_PERSON_ID:
        print("[ERROR] LinkedIn credentials manquantes")
        print("[SIMULATE] Publication simulée:")
        print(f"  Pilier: {post.get('pillar')}")
        print(f"  Format: {post.get('format')}")
        print(f"  Contenu (preview): {post.get('content', '')[:200]}...")
        return {"status": "simulated", "id": "sim_" + datetime.now().strftime("%Y%m%d%H%M")}

    url = "https://api.linkedin.com/v2/ugcPosts"
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    payload = {
        "author": f"urn:li:person:{LINKEDIN_PERSON_ID}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": post["content"]
                },
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 201:
            result = response.json()
            print(f"[OK] Post publié avec succès! ID: {result.get('id', 'N/A')}")
            return {"status": "published", "id": result.get("id"), "response": result}
        else:
            print(f"[ERROR] LinkedIn API {response.status_code}: {response.text}")
            return {"status": "error", "code": response.status_code, "message": response.text}
    except Exception as e:
        print(f"[ERROR] Publication: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================
# ARCHIVAGE
# ============================================================
def archive_published_post(post, publish_result):
    """Archive un post publié."""
    os.makedirs(PUBLISHED_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"post_{today}_{post.get('pillar', 'unknown')}.json"
    filepath = os.path.join(PUBLISHED_DIR, filename)

    archive = {
        "published_date": today,
        "published_time": datetime.now().strftime("%H:%M"),
        "pillar": post.get("pillar"),
        "format": post.get("format"),
        "content": post.get("content"),
        "hashtags": post.get("hashtags"),
        "enhanced": post.get("enhanced", False),
        "linkedin_response": publish_result,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)

    print(f"[OK] Post archivé: {filepath}")


# ============================================================
# GÉNÉRATION DE POST À PARTIR DU BRIEF
# ============================================================
def generate_post_from_brief():
    """Génère un post à partir du dernier brief de veille (si pas de post en queue)."""
    today = datetime.now().strftime("%Y-%m-%d")
    brief_file = os.path.join(BRIEF_DIR, f"brief_{today}.json")

    if not os.path.exists(brief_file):
        # Essayer le brief d'hier
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        brief_file = os.path.join(BRIEF_DIR, f"brief_{yesterday}.json")

    if not os.path.exists(brief_file):
        print("[WARN] Aucun brief trouvé pour générer un post")
        return None

    with open(brief_file, "r", encoding="utf-8") as f:
        brief = json.load(f)

    if brief.get("status") in ["NO_NEWS", "ERROR"]:
        return None

    # Déterminer le pilier du jour
    pillar = determine_today_pillar() or "terrain"
    angles = brief.get("post_angles", [])

    # Trouver un angle qui correspond au pilier
    chosen_angle = None
    for angle in angles:
        if angle.get("pillar") == pillar:
            chosen_angle = angle
            break
    if not chosen_angle and angles:
        chosen_angle = angles[0]

    if not chosen_angle:
        return None

    # Générer le post via IA
    prompt = f"""Tu es Mehdi, un Category Manager expérimenté en procurement.
Tu publies sur LinkedIn avec le positionnement "Praticien terrain + Analyste procuretech".

BRIEF DU JOUR:
- Funding: {json.dumps(brief.get('funding_alert'), ensure_ascii=False)}
- Stat clé: {json.dumps(brief.get('key_stat'), ensure_ascii=False)}
- Nouvel outil: {json.dumps(brief.get('new_tool'), ensure_ascii=False)}
- Sujet chaud: {json.dumps(brief.get('hot_topic'), ensure_ascii=False)}

ANGLE CHOISI:
- Pilier: {chosen_angle.get('pillar')}
- Hook: {chosen_angle.get('hook')}
- Format: {chosen_angle.get('format')}

CONSIGNES:
- Écris à la première personne (je suis Mehdi, Category Manager)
- Pilier "{pillar}": {"partage ton expérience terrain réelle, sois concret" if pillar == "terrain" else "analyse une tendance/startup/outil, donne ton avis d'expert"}
- Structure HVIA: Hook (1 ligne choc) → Vécu/Contexte → Insight → Appel (question ouverte)
- Accroche < 150 caractères
- Longueur: 800-1500 caractères
- Termine par une question ouverte
- Ajoute 3-5 hashtags pertinents à la fin
- Ton: professionnel, direct, pas de bullshit
- Max 3 emojis dans tout le post
- Sauts de ligne pour aérer

Écris le post LinkedIn complet. UNIQUEMENT le post, rien d'autre."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=1500,
        )
        content = response.choices[0].message.content.strip()
        return {
            "content": content,
            "pillar": pillar,
            "format": chosen_angle.get("format", "texte"),
            "source": "auto_from_brief",
            "brief_date": today,
            "status": "ready",
        }
    except Exception as e:
        print(f"[ERROR] Génération de post: {e}")
        return None


# ============================================================
# MAIN
# ============================================================
def main():
    print(f"[START] Bot LinkedIn — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Charger le tracker
    tracker = load_tracker()

    # Vérifier si on a déjà publié aujourd'hui
    today = datetime.now().strftime("%Y-%m-%d")
    if tracker.get("last_post_date") == today:
        print("[SKIP] Déjà publié aujourd'hui.")
        return

    # Déterminer le pilier du jour
    target_pillar = determine_today_pillar()
    if not target_pillar:
        print(f"[SKIP] Pas de publication prévue aujourd'hui ({datetime.now().strftime('%A')})")
        return

    print(f"[INFO] Pilier du jour: {target_pillar}")

    # Charger la queue
    queue = load_queue()
    tracker["queue_size"] = len([p for p in queue if p.get("status") == "ready"])

    # Récupérer le prochain post
    idx, post = get_next_post(queue, target_pillar)

    # Si pas de post en queue, essayer de générer depuis le brief
    if post is None:
        print("[INFO] Queue vide, génération depuis le brief de veille...")
        post = generate_post_from_brief()
        if post is None:
            print("[ERROR] Impossible de générer un post. Queue vide et pas de brief.")
            save_tracker(tracker)
            return
        # Ajouter à la queue
        queue.append(post)
        idx = len(queue) - 1

    print(f"[INFO] Post sélectionné: pilier={post.get('pillar')}, format={post.get('format')}")

    # Quality check & enhancement
    post = enhance_post_if_needed(post)
    is_valid, issues = quality_check(post)
    if not is_valid:
        print(f"[WARN] Post non conforme après amélioration: {issues}")
        print("[PUBLISH ANYWAY] Publication avec avertissements...")

    # Publication
    result = publish_to_linkedin(post)

    # Si succès, mettre à jour la queue et le tracker
    if result.get("status") in ["published", "simulated"]:
        # Marquer comme publié dans la queue
        if idx is not None and idx < len(queue):
            queue[idx]["status"] = "published"
            queue[idx]["published_date"] = today
        save_queue(queue)

        # Archiver
        archive_published_post(post, result)

        # Mettre à jour le tracker
        tracker = update_tracker_after_publish(tracker, post)
        print(f"[STATS] Total: {tracker['total_posts']} posts | Streak: {tracker['current_streak']} | Cette semaine: {tracker['posts_this_week']}/{tracker['target_per_week']}")

    save_tracker(tracker)
    print("[DONE] Bot terminé.")


if __name__ == "__main__":
    main()

