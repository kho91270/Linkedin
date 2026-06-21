"""
APPROVAL_WEBHOOK.PY - Verifie les reponses email pour approuver/refuser.
Supporte les approbations bilingues: OK, OK FR, OK EN
Supporte: OK, OK FR, OK EN, HOOK A FR, HOOK B EN, SKIP
Utilise IMAP natif (pas besoin de rafraichir de token Google API).
"""

import os
import json
import imaplib
import email
from email.header import decode_header
import re
from datetime import datetime

# Configuration
SMTP_EMAIL = os.environ.get("SMTP_EMAIL")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")

PENDING_DIR = "pending_approval"
APPROVED_DIR = "approved_posts"

def parse_approval_response(body_text):
    """Parse la reponse email et determine l'action + langue."""
    if not body_text:
        return None
        
    first_line = body_text.strip().split("\n")[0].strip().upper()

    if first_line in ["OK", "APPROVE", "APPROVED", "OUI", "YES", "GO", "VALIDE"]:
        return {"action": "approve", "lang_approved": "both"}
    elif first_line in ["OK FR", "APPROVE FR", "YES FR"]:
        return {"action": "approve", "lang_approved": "fr"}
    elif first_line in ["OK EN", "APPROVE EN", "YES EN"]:
        return {"action": "approve", "lang_approved": "en"}
    elif "HOOK A FR" in first_line:
        return {"action": "approve", "lang_approved": "both", "use_hook": "hook_a_fr"}
    elif "HOOK B FR" in first_line:
        return {"action": "approve", "lang_approved": "both", "use_hook": "hook_b_fr"}
    elif "HOOK A EN" in first_line:
        return {"action": "approve", "lang_approved": "both", "use_hook": "hook_a_en"}
    elif "HOOK B EN" in first_line:
        return {"action": "approve", "lang_approved": "both", "use_hook": "hook_b_en"}
    elif first_line in ["SKIP", "REFUSE", "NO", "NON", "REFUSER", "CANCEL"]:
        return {"action": "reject", "lang_approved": None}
    else:
        # Si la reponse ne matche pas, on considere que ce sont des corrections manuelles
        return {"action": "edit", "corrections": body_text[:500]}


def check_emails_imap():
    """Se connecte a Gmail via IMAP et recupere les reponses d'approbation non lues."""
    results = []
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        print("[ERROR] SMTP_EMAIL ou SMTP_PASSWORD manquant.")
        return results

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(SMTP_EMAIL, SMTP_PASSWORD)
        mail.select("inbox")

        # Cherche les emails NON LUS avec "Posts a valider" dans le sujet
        status, messages = mail.search(None, '(UNSEEN SUBJECT "Posts a valider")')
        email_ids = messages[0].split()

        for e_id in email_ids:
            _, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Decoder le sujet pour extraire la date
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8")
                    
                    # Extraire la date du sujet (ex: 2026-10-25)
                    date_match = re.search(r'\d{4}-\d{2}-\d{2}', subject)
                    if not date_match:
                        continue
                    publish_date = date_match.group(0)

                    # Extraire le corps du message
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                break
                    else:
                        body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

                    # Parser l'action
                    action_data = parse_approval_response(body)
                    if action_data:
                        action_data["publish_date"] = publish_date
                        results.append(action_data)
            
            # Marquer l'email comme lu
            mail.store(e_id, '+FLAGS', '\\Seen')

        mail.logout()
    except Exception as e:
        print(f"[ERROR] IMAP Check: {e}")

    return results


def apply_hook_replacement(post, hook_key):
    """Remplace la premiere ligne du post par le hook alternatif choisi."""
    quality_report = post.get("quality_report", {})
    if "fr" in hook_key:
        hooks = quality_report.get("hooks_fr", {})
        key = "hook_a" if "a" in hook_key else "hook_b"
        new_hook = hooks.get(key, "")
        if new_hook and post.get("content_fr"):
            lines = post["content_fr"].split("\n")
            lines[0] = new_hook
            post["content_fr"] = "\n".join(lines)
    elif "en" in hook_key:
        hooks = quality_report.get("hooks_en", {})
        key = "hook_a" if "a" in hook_key else "hook_b"
        new_hook = hooks.get(key, "")
        if new_hook and post.get("content_en"):
            lines = post["content_en"].split("\n")
            lines[0] = new_hook
            post["content_en"] = "\n".join(lines)
    return post


def process_approval(action_data):
    """Traite l'action demandee sur le fichier JSON correspondant."""
    action = action_data.get("action")
    publish_date = action_data.get("publish_date")
    lang_approved = action_data.get("lang_approved", "both")
    use_hook = action_data.get("use_hook")
    
    if not os.path.exists(PENDING_DIR):
        return

    # Chercher le fichier correspondant a la date
    for filename in os.listdir(PENDING_DIR):
        if filename.startswith(f"pending_{publish_date}"):
            src = os.path.join(PENDING_DIR, filename)
            
            with open(src, "r", encoding="utf-8") as f:
                post = json.load(f)

            if action == "reject":
                os.remove(src)
                print(f"  -> Post du {publish_date} supprime (SKIP).")
                return
                
            elif action == "approve":
                os.makedirs(APPROVED_DIR, exist_ok=True)
                
                if use_hook:
                    post = apply_hook_replacement(post, use_hook)
                    
                post["approval_status"] = "approved"
                post["lang_approved"] = lang_approved
                post["approved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                
                dst = os.path.join(APPROVED_DIR, filename.replace("pending_", "approved_"))
                with open(dst, "w", encoding="utf-8") as f:
                    json.dump(post, f, ensure_ascii=False, indent=2)
                
                os.remove(src)
                print(f"  -> Post du {publish_date} deplace vers APPROVED ({lang_approved}).")
                return
                
            elif action == "edit":
                # Optionnel: on pourrait injecter les corrections dans le JSON ici
                print(f"  -> Demande de correction detectee pour le {publish_date}. Intervention manuelle requise.")
                return


def main():
    print(f"[START] Approval Check -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("[1/2] Verification des reponses email via IMAP...")
    actions = check_emails_imap()
    
    print(f"       -> {len(actions)} reponses trouvees")
    if not actions:
        print("[DONE] Aucune reponse non lue.")
        return
        
    print("[2/2] Traitement des fichiers JSON...")
    for action_data in actions:
        print(f"  Action detectee: {action_data.get('action')} | Lang: {action_data.get('lang_approved', 'N/A')} | Date: {action_data.get('publish_date', 'N/A')}")
        process_approval(action_data)
        
    print("[DONE] Termine.")

if __name__ == "__main__":
    main()
