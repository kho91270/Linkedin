import os
import requests

token = os.environ.get("LINKEDIN_ACCESS_TOKEN")

if not token:
    print("[ERROR] Pas de LINKEDIN_ACCESS_TOKEN trouvé.")
else:
    url = "https://api.linkedin.com/v2/me"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        print("\n" + "="*50)
        print(f"✅ TON VRAI LINKEDIN_PERSON_ID EST : {data.get('id')}")
        print("="*50 + "\n")
    else:
        print(f"Erreur API: {response.status_code} - {response.text}")
