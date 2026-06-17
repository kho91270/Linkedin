
"""
APPROVAL_WEBHOOK.PY - Verifie les reponses email pour approuver/refuser.
Utilise Gmail API (Google Credentials) ou fallback IMAP.
"""

import os
import json
import imaplib
import email
import base64
from email.header import decode_header
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS")
SMTP_EMAIL = os.environ.get("SMTP_EMAIL")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")

PENDING_DIR = "pending_approval"
APPROVED_DIR = "approved_posts"
REJECTED_DIR = "rejected_posts"


def get_gmail_service():
    if not GOOGLE_CREDENTIALS:
        return None
    try:
        creds_data = json.loads(GOOGLE_CREDENTIALS)
        creds = Credentials.from_authorized_user_info(creds_data)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build("gmail", "v1", credentials=creds)
    except Exception as e:
        print(f"[WARN] Gmail service: {e}")
        return None


def check_emails_gmail():
    service = get_gmail_service()
    if not service:
        return check_emails_imap()
    results = []
    try:
        query = 'subject:"Re: [LinkedIn]" newer_than:2d'
        response = service.users().messages().list(userId="me", q=query, maxResults=10).execute()
        messages = response.get("messages", [])
        for msg_meta in messages:
            msg = service.users().messages().get(userId="me", id=msg_meta["id"], format="full").execute()
            headers = msg.get("payload", {}).get("headers", [])
            subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")
            body = ""
            payload = msg.get("payload", {})
            if payload.get("body", {}).get("data"):
                body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
            elif payload.get("parts"):
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                        body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
                        break
            first_line = body.strip().split("\n")[0].strip().upper()
            publish_date = None
            if "pour le" in subject.lower():
                try:
                    publish_date = subject.lower().split("pour le")[1].strip()[:10]
                except Exception:
                    pass
            if first_line in ["OK", "APPROVE", "APPROVED", "OUI", "YES", "GO", "VALIDE"]:
                results.append({"action": "approve", "publish_date": publish_date})
            elif first_line in ["SKIP", "REFUSE", "NO", "NON", "REFUSER", "CANCEL"]:
                results.append({"action": "reject", "publish_date": publish_date})
            else:
                results.append({"action": "modify", "publish_date": publish_date, "body": body.strip()})
    except Exception as e:
        print(f"[ERROR] Gmail API: {e}")
        return check_emails_imap()
    return results


def check_emails_imap():
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        print("[ERROR] Pas de credentials email")
        return []
    results = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(SMTP_EMAIL, SMTP_PASSWORD)
        mail.select("inbox")
        since_date = (datetime.now() - timedelta(days=2)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(SINCE "{since_date}" SUBJECT "[LinkedIn]")')
        if status != "OK":
            mail.logout()
            return []
        for msg_id in messages[0].split()[-10:]:
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            subject = decode_header(msg["Subject"])[0][0]
            if isinstance(subject, bytes):
                subject = subject.decode()
            if "Re:" not in subject and "RE:" not in subject:
                continue
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode(errors="ignore")
                        break
            else:
                body = msg.get_payload(decode=True).decode(errors="ignore")
            first_line = body.strip().split("\n")[0].strip().upper()
            publish_date = None
            if "pour le" in subject.lower():
                try:
                    publish_date = subject.lower().split("pour le")[1].strip()[:10]
                except Exception:
                    pass
            if first_line in ["OK", "APPROVE", "APPROVED", "OUI", "YES", "GO", "VALIDE"]:
                results.append({"action": "approve", "publish_date": publish_date})
            elif first_line in ["SKIP", "REFUSE", "NO", "NON", "REFUSER", "CANCEL"]:
                results.append({"action": "reject", "publish_date": publish_date})
            else:
                results.append({"action": "modify", "publish_date": publish_date, "body": body.strip()})
        mail.logout()
    except Exception as e:
        print(f"[ERROR] IMAP: {e}")
    return results


def process_approval(action_data):
    action = action_data.get("action")
    publish_date = action_data.get("publish_date")
    if not os.path.exists(PENDING_DIR):
        return
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
        print(f"[WARN] Pas de post pending pour {publish_date}")
        return
    filepath = os.path.join(PENDING_DIR, pending_file)
    with open(filepath, "r", encoding="utf-8") as f:
        post = json.load(f)
    if action == "approve":
        os.makedirs(APPROVED_DIR, exist_ok=True)
        post["approval_status"] = "approved"
        post["approved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        approved_path = os.path.join(APPROVED_DIR, pending_file.replace("pending_", "approved_"))
        with open(approved_path, "w", encoding="utf-8") as f:
            json.dump(post, f, ensure_ascii=False, indent=2)
        os.remove(filepath)
        print(f"[OK] APPROUVE -> {approved_path}")
    elif action == "reject":
        os.makedirs(REJECTED_DIR, exist_ok=True)
        post["approval_status"] = "rejected"
        post["rejected_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        rejected_path = os.path.join(REJECTED_DIR, pending_file.replace("pending_", "rejected_"))
        with open(rejected_path, "w", encoding="utf-8") as f:
            json.dump(post, f, ensure_ascii=False, indent=2)
        os.remove(filepath)
        print(f"[OK] REFUSE -> {rejected_path}")
    elif action == "modify":
        post["modification_requested"] = action_data.get("body", "")
        post["modification_date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(post, f, ensure_ascii=False, indent=2)
        print(f"[OK] MODIFICATION demandee")


def main():
    print(f"[START] Approval Check -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("[1/2] Verification des reponses email...")
    actions = check_emails_gmail()
    print(f"       -> {len(actions)} reponses trouvees")
    if not actions:
        print("[DONE] Aucune reponse.")
        return
    print("[2/2] Traitement...")
    for action_data in actions:
        print(f"  Action: {action_data['action']} | Date: {action_data.get('publish_date', '?')}")
        process_approval(action_data)
    print("[DONE] Termine.")


if __name__ == "__main__":
    main()

