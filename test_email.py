import smtplib
from email.mime.text import MIMEText

SMTP_EMAIL = "mehdi.bekka.perso@gmail.com"
SMTP_PASSWORD = [PASSWORD]i"  # 16 chars sans espaces
NOTIFY_EMAIL = "mehdi.bekka.perso@gmail.com"

msg = MIMEText("Ceci est un test du bot LinkedIn. Si tu recois cet email, tout fonctionne !")
msg["Subject"] = "[LinkedIn Bot] Test de configuration"
msg["From"] = SMTP_EMAIL
msg["To"] = NOTIFY_EMAIL

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
    server.login(SMTP_EMAIL, SMTP_PASSWORD)
    server.sendmail(SMTP_EMAIL, NOTIFY_EMAIL, msg.as_string())

print("Email envoye avec succes !")
