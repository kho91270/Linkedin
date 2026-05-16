import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os
import random
from datetime import datetime

# ============================================================
# ENGAGEMENT AUTOMATION BILINGUE (FR / EN)
# Chaque matin : propose 5 comptes a commenter
# avec 2 suggestions expertes dans la langue de la cible
# ============================================================

SHEET_ID = "1k4G-v1-nEgtE256nKUYjq-KfQd4A3CvMn03S1cp8NSE"

# ============================================================
# COMPTES CIBLES (Avec gestion de la langue)
# ============================================================
TARGET_ACCOUNTS = [
    {
        "name": "Tom Mills",
        "role": "Procurement Influencer",
        "url": "https://www.linkedin.com/in/tom-mills-procurement/",
        "lang": "en",
        "tone": "conversationnel et challenger"
    },
    {
        "name": "Bertrand Maltaverne",
        "role": "Procurement Digital Expert",
        "url": "https://www.linkedin.com/in/bmaltaverne/",
        "lang": "fr",
        "tone": "expert et francophone"
    },
    {
        "name": "Dipika Sharma",
        "role": "Procurement & Cost Modeling",
        "url": "https://www.linkedin.com/in/dipika-sharma-a1306a222/",
        "lang": "en",
        "tone": "analytique et orienté valeur"
    },
    {
        "name": "Faiq Ali",
        "role": "Procurement Leader",
        "url": "https://www.linkedin.com/in/faiq-supplychain-procurement/",
        "lang": "en",
        "tone": "analytique et data-driven"
    },
    {
        "name": "Marijn Overvest",
        "role": "Founder Procurement Tactics",
        "url": "https://www.linkedin.com/in/marijn-overvest-60683315/",
        "lang": "en",
        "tone": "pragmatique et orienté résultats"
    },
    {
        "name": "Chandhrika",
        "role": "Procurement Tech & Supplier Data",
        "url": "https://www.linkedin.com/in/chandhrika/",
        "lang": "en",
        "tone": "technique et orienté process"
    },
    {
        "name": "SupplyChainAIPRO",
        "role": "AI & Automation",
        "url": "https://www.linkedin.com/in/supplychainaipro/",
        "lang": "en",
        "tone": "visionnaire et technologique"
    },
    {
        "name": "Michael Lamoureux",
        "role": "Sourcing Doctor & Supply Chain",
        "url": "https://www.linkedin.com/in/sourcingdoctor/",
        "lang": "fr",
        "tone": "académique et expert"
    }
]

# ============================================================
# CONTENU D'EXPERTISE BILINGUE (Orthographe parfaite)
# ============================================================
CONTENT = {
    "fr": {
        "templates": [
            "Totalement d'accord {name}. J'ajouterais que {value_add}. Dans mon expérience, {example}.",
            "Excellente perspective {name}. Ce que je constate aussi sur le terrain : {value_add}. La clé reste {insight}.",
            "Perspective très intéressante {name}. Je nuancerais cependant : {nuance}. Qu'en pensez-vous ?",
            "C'est un vrai sujet. Comment gérez-vous le cas où {edge_case} ? Curieux d'avoir votre retour d'expert.",
            "Les chiffres de l'industrie confirment ce point : {data}. Cela renforce l'idée que {conclusion}."
        ],
        "value_adds": [
            "la maturité Achats se mesure aujourd'hui à son influence au COMEX, et non plus aux simples 'savings'",
            "le 'Should-Cost' modélisé élimine près de 80 % des frictions théâtrales en négociation",
            "l'adoption technologique prime sur la fonctionnalité : 70 % des échecs digitaux sont d'origine humaine",
            "l'IA est un excellent copilote analytique, mais la décision finale et le relationnel restent 100 % humains",
            "une victoire rapide (quick win) à 30 jours suscite plus d'adhésion que 100 slides de stratégie théorique"
        ],
        "examples": [
            "rationaliser un panel de 2000 à 400 fournisseurs m'a permis de libérer 25 % de temps stratégique pour mes équipes",
            "introduire 47 secondes de silence intentionnel lors d'une négociation difficile a sécurisé 340K €",
            "utiliser le 'Value Engineering' a permis de réduire un coût unitaire de 45 € à 28 € sans toucher à la marge du fournisseur",
            "dire 'non' à un contrat mal aligné m'a fait économiser 1,7M € de TCO sur 3 ans",
            "lancer un 'Innovation Day' Fournisseurs pour seulement 5K € a généré 400K € de valeur et un nouveau brevet"
        ],
        "insights": [
            "la préparation minutieuse représente 90 % du succès final d'une négociation",
            "votre réseau interne rapporte souvent bien plus de valeur que vos négociations externes",
            "le Scope 3 est définitivement le nouveau champ de bataille stratégique de la fonction Achats",
            "l'influence sans autorité formelle est la compétence numéro un du CPO de demain"
        ],
        "nuances": [
            "dans le contexte européen, des réglementations strictes comme le CBAM ou la CSRD modifient complètement cette équation",
            "l'applicabilité de ce modèle se heurte très souvent au manque de ressources dans les équipes achats de taille moyenne",
            "il faut impérativement intégrer le facteur culturel et humain avant d'essayer de digitaliser un processus défaillant"
        ],
        "edge_cases": [
            "le fournisseur clé est en position de monopole et utilise pleinement ce levier de pression",
            "les prescripteurs internes (stakeholders) court-circuitent systématiquement les procédures d'achats",
            "le budget alloué est drastiquement coupé mais les attentes de performance du Board restent identiques"
        ],
        "data": [
            "selon la dernière étude Deloitte CPO, plus de 65 % des directions Achats placent la gestion du risque fournisseur en priorité absolue",
            "Gartner indique que 50 % des entreprises intégreront l'IA générative dans leurs process Source-to-Pay d'ici 2026",
            "le BCG démontre que les entreprises très performantes en RSE peuvent réduire leur coût du capital de près de 10 %"
        ],
        "conclusions": [
            "la fonction Achats évolue massivement d'un centre de coûts vers un véritable rôle d'orchestrateur de la chaîne de valeur",
            "une donnée fournisseur propre et actionnable vaut infiniment plus qu'un logiciel sophistiqué mais vide",
            "la durabilité et la rentabilité ne s'opposent plus : elles s'alignent aujourd'hui parfaitement via le prisme du TCO"
        ]
    },
    "en": {
        "templates": [
            "Completely agree {name}. I would add that {value_add}. In my experience, {example}.",
            "Excellent perspective {name}. What I also observe in the field: {value_add}. The real key is {insight}.",
            "Very interesting take {name}. I might add a nuance here: {nuance}. What are your thoughts?",
            "Great topic. How do you handle situations where {edge_case}? Would love your expert view on this.",
            "Industry data strongly supports your point: {data}. This reinforces the idea that {conclusion}."
        ],
        "value_adds": [
            "Procurement maturity is now measured by C-suite influence, not just pure cost savings",
            "Should-Cost modeling eliminates nearly 80% of the traditional negotiation theater",
            "User adoption matters more than software features: 70% of digital transformation failures are human-driven",
            "AI is an outstanding analytical co-pilot, but the final strategic decision and relationship-building remain 100% human",
            "A 30-day quick win builds much more stakeholder trust than 100 slides of theoretical procurement strategy"
        ],
        "examples": [
            "rationalizing a supplier base from 2,000 to 400 freed up 25% of my team's time for high-level strategic work",
            "using 47 seconds of intentional silence during a tough negotiation historically secured €340K in retained value",
            "applying Value Engineering reduced a specific component cost from €45 to €28 without squeezing the supplier's margin",
            "saying 'no' to a misaligned CEO mandate effectively saved €1.7M in TCO over a 3-year period",
            "hosting a €5K Supplier Innovation Day generated €400K in actionable value and a shared patent"
        ],
        "insights": [
            "thorough preparation ultimately accounts for 90% of your negotiation success",
            "your internal stakeholder network often generates more value than your external supplier negotiations",
            "Scope 3 emissions are undoubtedly the new strategic battlefield for Procurement leaders",
            "influence without formal authority is the absolute number one skill for tomorrow's CPO"
        ],
        "nuances": [
            "in the European context, strict regulations like CBAM and CSRD completely change this equation",
            "the practical application of this model often hits a wall when resources in mid-sized teams are heavily constrained",
            "you must integrate the cultural and human factors well before attempting to digitize a broken process"
        ],
        "edge_cases": [
            "the key supplier holds a strict monopoly and is fully aware of their leverage",
            "internal stakeholders consistently bypass the formal procurement channels to go direct",
            "budgets are drastically cut, yet the performance expectations from the board remain identical"
        ],
        "data": [
            "according to the latest Deloitte CPO Survey, over 65% of Procurement leaders place supplier risk management as their absolute top priority",
            "Gartner reports that 50% of organizations will have integrated Generative AI into their source-to-pay processes by 2026",
            "BCG research shows that companies with strong ESG performance can reduce their cost of capital by up to 10%"
        ],
        "conclusions": [
            "Procurement is rapidly shifting from a back-office cost center to a true value chain orchestrator",
            "clean, actionable supplier data is worth infinitely more than a sophisticated but empty software tool",
            "sustainability and profitability are no longer mutually exclusive; they align perfectly through a TCO mindset"
        ]
    }
}

def connect_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID)

def generate_comment(target):
    """Génère un commentaire expert dans la langue de la cible"""
    lang = target.get("lang", "en")  # Par defaut en anglais si non specifié
    content = CONTENT[lang]
    
    template = random.choice(content["templates"])
    
    comment = template.format(
        name=target["name"].split()[0],
        value_add=random.choice(content["value_adds"]),
        example=random.choice(content["examples"]),
        insight=random.choice(content["insights"]),
        nuance=random.choice(content["nuances"]),
        edge_case=random.choice(content["edge_cases"]),
        data=random.choice(content["data"]),
        conclusion=random.choice(content["conclusions"])
    )
    
    # Capitalisation propre de la premiere lettre (sécurité)
    comment = comment[0].upper() + comment[1:]
    return f"Expert Insight ({lang.upper()})", comment

def generate_daily_plan():
    """Génère le plan d'engagement du jour : 5 comptes + 2 suggestions expertes"""
    today = datetime.now().strftime("%Y-%m-%d")
    day_number = datetime.now().timetuple().tm_yday

    shuffled = TARGET_ACCOUNTS.copy()
    random.seed(day_number)
    random.shuffle(shuffled)
    selected = shuffled[:5]

    plan = []
    for target in selected:
        type1, comment1 = generate_comment(target)
        type2, comment2 = generate_comment(target)

        # S'assurer que les 2 suggestions sont différentes
        attempts = 0
        while comment1 == comment2 and attempts < 5:
            type2, comment2 = generate_comment(target)
            attempts += 1

        plan.append([
            today,
            target["name"],
            target["role"],
            type1,
            comment1,
            type2,
            comment2,
            target["tone"],
            ""
        ])

    return plan

def write_plan(plan):
    """Ecrit le plan dans l'onglet Engagement"""
    spreadsheet = connect_sheets()

    try:
        ws = spreadsheet.worksheet("Engagement")
    except:
        ws = spreadsheet.add_worksheet(title="Engagement", rows=500, cols=9)
        ws.update("A1:I1", [["Date", "Compte", "Role", "Type_Comment_1", "Suggestion_1", "Type_Comment_2", "Suggestion_2", "Ton", "Fait"]])

    existing = ws.get_all_values()
    next_row = len(existing) + 1

    ws.update(f"A{next_row}:I{next_row + len(plan) - 1}", plan)
    print(f"  [OK] Plan écrit dans le Sheet (lignes {next_row}-{next_row + len(plan) - 1})")

def main():
    print("=" * 50)
    print("ENGAGEMENT AUTOMATION BILINGUE - PLAN DU JOUR")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)
    print("")

    plan = generate_daily_plan()

    print("  PLAN DU JOUR (15 min):")
    print("  " + "-" * 50)
    for entry in plan:
        print(f"")
        print(f"  >>> {entry[1]} ({entry[2][:35]})")
        print(f"      Ton: {entry[7]}")
        print(f"      Option 1 [{entry[3]}]:")
        print(f"        {entry[4][:150]}...")
        print(f"      Option 2 [{entry[5]}]:")
        print(f"        {entry[6][:150]}...")
    print("")
    print("  " + "-" * 50)

    write_plan(plan)

    print("")
    print("[DONE] Suggestions générées avec succès en respectant la langue et la typographie.")

if __name__ == "__main__":
    main()
