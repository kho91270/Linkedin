import os
import requests

token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
headers = {"Authorization": f"Bearer {token}"}

# Test 1 : Nouvelle méthode (OpenID)
r1 = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers)
if r1.status_code == 200:
    print(f"\n✅ TON VRAI ID EST : {r1.json().get('sub')}\n")
else:
    # Test 2 : Ancienne méthode
    r2 = requests.get("https://api.linkedin.com/v2/me", headers=headers)
    if r2.status_code == 200:
        print(f"\n✅ TON VRAI ID EST : {r2.json().get('id')}\n")
    else:
        print(f"Erreur : {r1.text} | {r2.text}")
