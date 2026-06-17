
"""
APPROVAL_WEBHOOK.PY — Serveur de validation par email
Verifie les reponses email pour approuver/refuser les posts.
Utilise IMAP pour lire les reponses a l'email de validation.
"""

import os
import json
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta

# ============================================================
# CONFIGURATION
# ============================================================
IMAP_EMAIL = os.environ.get("SMTP_EMAIL")
IMAP_PASSWORD = os.environ.get("SMTP_PASSWORD")
IMAP_SERVER = "imap.gmail.com"

PENDING_DIR = "pending_approval"
APPROVED_DIR = "approved_posts"
REJECTED_DIR = "rejected_posts"


# ============================================================
# LECTURE DES EMAILS
# ============================================================
def check_approval_emails():
    """Verifie les emails de reponse pour approbation."""
    if not IMAP_EMAIL or not IMAP_PASSWORD:
        print("[ERROR] Credentials email non configurees")
        return []

    results = []

    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(IMAP_EMAIL, IMAP_PASSWORD)
        mail.select("inbox")

        # Chercher les emails recents avec le sujet de validation
        since_date = (datetime.now() - timedelta(days=2)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(SINCE "{since_date}" SUBJECT "[LinkedIn]")')

        if status != "OK":
            print("[WARN] Pas de messages trouves")
            mail.logout()
            return []

        message_ids = messages[0].split()

        for msg_id in message_ids[-10:]:  # Derniers 10 max
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue

            msg = email.message_from_bytes(msg_data[0][1])

            # Verifier que c'est une reponse (Re:)
            subject = decode_header(msg["Subject"])[0][0]
            if isinstance(subject, bytes):
                subject = subject.decode()

            if "Re:" not in subject and "RE:" not in subject:
                continue

            # Extraire le corps
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode(errors="ignore")
                        break
            else:
                body = msg.get_payload(decode=True).decode(errors="ignore")

            body_clean = body.strip().split("\n")[0].strip().upper()

            # Extraire la date de publication du sujet
            publish_date = None
            if "pour le" in subject.lower():
                try:
                    date_part = subject.lower().split("pour le")[1].strip()[:10]
                    publish_date = date_part
                except Exception:
                    pass

            # Determiner l'action
            if body_clean in ["OK", "APPROVE", "APPROVED", "OUI", "YES", "GO", "VALIDE"]:
                results.append({"action": "approve", "publish_date": publish_date, "body": body})
            elif body_clean in ["SKIP", "REFUSE", "NO", "NON", "REFUSER", "CANCEL"]:
                results.append({"action": "reject", "publish_date": publish_date, "body": body})
            else:
                # C'est une modification
                results.append({"action": "modify", "publish_date": publish_date, "body": body})

        mail.logout()

    except Exception as e:
        print(f"[ERROR] IMAP: {e}")

    return results


# ============================================================
# TRAITEMENT DES APPROBATIONS
# ============================================================
def process_approval(action_data):
    """Traite une approbation/rejet/modification."""
    action = action_data.get("action")
    publish_date = action_data.get("publish_date")

    if not os.path.exists(PENDING_DIR):
        print("[WARN] Pas de dossier pending")
        return

    # Trouver le post pending
    pending_file = None
    for filename in os.listdir(PENDING_DIR):
        if filename.endswith(".json"):
            if publish_date and publish_date in filename:
                pending_file = filename
                break
            elif not publish_date:
                pending_file = filename
                break

    if not pending_file:
        print(f"[WARN] Pas de post pending trouve pour {publish_date}")
        return

    filepath = os.path.join(PENDING_DIR, pending_file)
    with open(filepath, "r", encoding="utf-8") as f:
        post = json.load(f)

    if action == "approve":
        # Deplacer vers approved
        os.makedirs(APPROVED_DIR, exist_ok=True)
        post["approval_status"] = "approved"
        post["approved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        approved_file = pending_file.replace("pending_", "approved_")
        approved_path = os.path.join(APPROVED_DIR, approved_file)
        with open(approved_path, "w", encoding="utf-8") as f:
            json.dump(post, f, ensure_ascii=False, indent=2)
        os.remove(filepath)
        print(f"[OK] Post APPROUVE -> {approved_path}")

    elif action == "reject":
        # Deplacer vers rejected
        os.makedirs(REJECTED_DIR, exist_ok=True)
        post["approval_status"] = "rejected"
        post["rejected_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        rejected_file = pending_file.replace("pending_", "rejected_")
        rejected_path = os.path.join(REJECTED_DIR, rejected_file)
        with open(rejected_path, "w", encoding="utf-8") as f:
            json.dump(post, f, ensure_ascii=False, indent=2)
        os.remove(filepath)
        print(f"[OK] Post REFUSE -> {rejected_path}")

    elif action == "modify":
        # Garder en pending mais noter la demande de modification
        post["modification_requested"] = action_data.get("body", "")
        post["modification_date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(post, f, ensure_ascii=False, indent=2)
        print(f"[OK] Modification demandee -- post reste en pending")
        print(f"     Demande: {action_data.get('body', '')[:200]}")


# ============================================================
# MAIN
# ============================================================
def main():
    print(f"[START] Approval Webhook -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    print("[1/2] Verification des emails de reponse...")
    actions = check_approval_emails()
    print(f"       -> {len(actions)} reponses trouvees")

    if not actions:
        print("[DONE] Aucune reponse a traiter.")
        return

    print("[2/2] Traitement des approbations...")
    for action_data in actions:
        print(f"\n  Action: {action_data['action']} | Date: {action_data.get('publish_date', '?')}")
        process_approval(action_data)

    print("\n[DONE] Approval Webhook termine.")


if __name__ == "__main__":
    main()

