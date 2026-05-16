import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os
import random
from datetime import datetime

# ============================================================
# ENGAGEMENT AUTOMATION
# Chaque matin : propose 5 comptes a commenter
# avec 2 suggestions de commentaires personnalises
# ============================================================

SHEET_ID = "1k4G-v1-nEgtE256nKUYjq-KfQd4A3CvMn03S1cp8NSE"

# ============================================================
# COMPTES CIBLES (Mis à jour avec vos nouvelles cibles)
# ============================================================
TARGET_ACCOUNTS = [
    {
        "name": "Tom Mills",
        "role": "Procurement Influencer - Procure Bites",
        "url": "https://www.linkedin.com/in/tom-mills-procurement/",
        "topics": ["procurement strategy", "negotiation", "leadership"],
        "tone": "conversationnel et challenger"
    },
    {
        "name": "Bertrand Maltaverne",
        "role": "Procurement Digital Expert & Thought Leader",
        "url": "https://www.linkedin.com/in/bmaltaverne/",
        "topics": ["digital procurement", "innovation", "P2P"],
        "tone": "expert et francophone"
    },
    {
        "name": "Dipika Sharma",
        "role": "Procurement & Cost Modeling Expert",
        "url": "https://www.linkedin.com/in/dipika-sharma-a1306a222/",
        "topics": ["procurement strategy", "innovation", "tech"],
        "tone": "analytique et orienté valeur"
    },
    {
        "name": "Faiq Ali",
        "role": "Procurement Leader - iDeliver Framework",
        "url": "https://www.linkedin.com/in/faiq-supplychain-procurement/",
        "topics": ["digital procurement", "transformation", "AI"],
        "tone": "analytique et data-driven"
    },
    {
        "name": "Marijn Overvest",
        "role": "Founder Procurement Tactics",
        "url": "https://www.linkedin.com/in/marijn-overvest-60683315/",
        "topics": ["negotiation", "procurement strategy", "procurement branding"],
        "tone": "pragmatique et orienté résultats"
    },
    {
        "name": "Chandhrika",
        "role": "Procurement Tech & Supplier Data Expert",
        "url": "https://www.linkedin.com/in/chandhrika/",
        "topics": ["supplier data", "tech", "digital procurement"],
        "tone": "technique et orienté process"
    },
    {
        "name": "SupplyChainAIPRO",
        "role": "AI & Automation in Supply Chain",
        "url": "https://www.linkedin.com/in/supplychainaipro/",
        "topics": ["AI", "digital procurement", "innovation"],
        "tone": "visionnaire et technologique"
    }
]

# ============================================================
# TEMPLATES DE COMMENTAIRES (5 types)
# ============================================================
COMMENT_TEMPLATES = {
    "agreement_plus_value": [
        "Totalement d accord {name}. J ajouterais que {value_add}. Dans mon experience, {example}.",
        "Point excellent. Ce que je constate aussi chez mes clients : {value_add}. La cle : {insight}.",
        "Spot on {name}. C est encore plus vrai quand {context}. J ai vu {example}.",
    ],
    "constructive_challenge": [
        "Perspective interessante {name}. Je nuancerais : {nuance}. Qu en pensez-vous ?",
        "D accord sur le fond mais je questionne {challenge}. Mon experience montre que {counter}. Votre avis ?",
        "Excellent post. Angle complementaire : {alternative}. Ca change la donne quand {context}.",
    ],
    "question_engagement": [
        "Question {name} : {question} ? Je fais face a ca chez un client et votre approche m interesse.",
        "Ca m interpelle. Comment gerez-vous le cas ou {edge_case} ? Curieux d avoir votre retour.",
        "Merci pour ce partage. Votre recommandation quand {scenario} ?",
    ],
    "storytelling_response": [
        "Ca me rappelle une situation similaire : {story}. La lecon : {lesson}.",
        "Vecu exactement ca. {story}. Depuis j applique {new_rule}. Game changer.",
        "Histoire vraie : {story}. Votre post confirme ce que j ai appris : {lesson}.",
    ],
    "data_enrichment": [
        "Pour appuyer votre point : {data}. Ca renforce l idee que {conclusion}.",
        "Chiffre complementaire : {data}. Ce que je trouve frappant : {insight}.",
        "Les chiffres confirment : {data}. Chez mes clients europeens c est encore plus marque.",
    ],
}

# ============================================================
# CONTENU CONTEXTUEL
# ============================================================
VALUE_ADDS = {
    "procurement strategy": [
        "la maturite achats se mesure en influence au COMEX pas en savings",
        "le vrai differenciateur est la capacite a anticiper pas a reagir",
        "les top performers parlent business pas technique achats",
    ],
    "negotiation": [
        "le should-cost elimine 80% du theatre en negociation",
        "la preparation compte pour 90% du resultat final",
        "le silence est l arme la plus sous-estimee : 47 secondes m ont fait gagner 340K",
    ],
    "digital procurement": [
        "l adoption compte plus que la fonctionnalite : 70% des echecs sont humains",
        "simplifier le process AVANT de digitaliser sinon on automatise le chaos",
        "un quick win en 30 jours vaut plus que 12 mois de deploiement",
    ],
    "AI": [
        "l IA est un co-pilote pas un autopilote : elle a failli me couter 200K EUR",
        "le vrai ROI de l IA est sur l analyse pas la decision",
        "un RFP genere en 12 min au lieu de 2 jours mais la nego reste 100% humaine",
    ],
    "transformation": [
        "un quick win en 30 jours vaut plus que 100 slides de strategie",
        "crediter les autres est la meilleure strategie pour obtenir leur support",
        "parler LEUR langage pas le notre : CA protege pas savings",
    ],
    "leadership": [
        "l influence sans autorite est LA competence #1 en achats",
        "dire non au CEO m a economise 1.7M EUR sur 3 ans",
        "votre personal branding determine si on vous ecoute ou pas",
    ],
    "sustainability": [
        "le Scope 3 est le prochain champ de bataille des achats",
        "le TLC incluant le carbone change toutes les decisions de sourcing",
        "la Pologne a 19.20 EUR bat la Chine a 20.80 EUR en TLC complet",
    ],
    "career": [
        "un acheteur invisible est un acheteur remplacable",
        "de buyer a CPO il y a 5 sauts pas une pente douce",
        "votre reseau rapporte plus que vos savings",
    ],
    "soft skills": [
        "le QE bat le QI en negociation",
        "le silence de 7 secondes minimum change la dynamique",
        "ecouter 3 semaines avant de proposer quoi que ce soit",
    ],
    "SRM": [
        "un fournisseur strategique n est pas un adversaire c est un co-createur",
        "l Innovation Day a 5K EUR a genere 400K de valeur et 1 brevet",
        "passer de 2000 a 400 fournisseurs a libere 25% du temps strategie",
    ],
    "procurement branding": [
        "les achats sont le secret le mieux garde des entreprises performantes",
        "1% des utilisateurs LinkedIn publient chaque semaine c est un avantage enorme",
        "un framework memorable vaut plus que 100 posts generiques",
    ],
    "innovation": [
        "80% du cout est fige au design : intervenir apres c est trop tard",
        "le value engineering a sorti -38% sans toucher au prix",
        "3 innovations de mes fournisseurs valaient 10x les savings demandes",
    ],
    "P2P": [
        "40% des taches P2P n ont aucune valeur ajoutee",
        "le maverick spend n est pas un probleme de compliance mais de service",
        "automatiser le tail spend libere les acheteurs pour la strategie",
    ],
    "RSE": [
        "le CBAM rend le nearshoring economiquement superieur pas juste ethique",
        "RSE sans mesure c est du greenwashing avec un joli PowerPoint",
        "l economie circulaire n est pas un cout c est un avantage competitif",
    ],
    "public sector": [
        "les marches publics ne sont pas condamnes a la lenteur",
        "l innovation est possible meme dans un cadre reglemente",
        "la valeur dans le public se mesure differemment mais se mesure quand meme",
    ],
    "supplier data": [
        "vous ne savez probablement pas qui vous fournit au tier 2 et 3",
        "la data fournisseur est le fondement de toute decision achats fiable",
        "un panel propre vaut plus qu un outil sophistique sur des donnees sales",
    ],
    "circular economy": [
        "l economie fonctionnelle remplace la possession par l usage : moins de capex plus de valeur",
        "le reconditionnement peut reduire les couts de 60% sur certaines categories",
        "acheter moins mais mieux : le paradoxe vertueux de la circularite",
    ],
    "women in procurement": [
        "la diversite en achats n est pas un objectif RSE c est un levier de performance",
        "les equipes mixtes negocient mieux parce qu elles voient plus d angles",
        "plus de role models feminins = plus de talents attires vers la profession",
    ],
    "tech": [
        "150 solutions procurement tech sur le marche mais combien sont vraiment utilisees",
        "la technologie doit s adapter au process pas l inverse",
        "le meilleur outil est celui que les gens utilisent vraiment",
    ],
}

EXAMPLES = [
    "rationalisation de 2000 a 400 fournisseurs = -40% risque et +25% temps strategique",
    "un CPO qui a rebaptise ses savings en protection du CA a vu son budget doubler",
    "47 secondes de silence en nego = de -4% a -12% soit 340K EUR",
    "value engineering composant 45 a 28 EUR sans negocier le prix",
    "fournisseur chinois a 12 EUR qui coute en realite 20.80 EUR en TLC",
    "transformation sauvee par un quick win a 30 jours apres 3 mois de resistance",
    "dire non a un contrat de 2M EUR en 48h a economise 1.7M EUR sur 3 ans",
    "refuser 500K de savings pour proteger 4.2M EUR de CA",
    "un Innovation Day a 5K EUR qui a genere 400K EUR de valeur et 1 brevet",
    "IA qui recommande un fournisseur en faillite 3 mois plus tard",
]

QUESTIONS = [
    "comment mesurez-vous le vrai impact quand le COMEX ne parle pas achats",
    "comment convaincre les prescripteurs sans avoir l autorite hierarchique",
    "quel a ete votre plus gros echec et qu avez-vous appris",
    "comment equilibrer vitesse d execution et rigueur process",
    "comment gerez-vous la resistance au changement dans vos equipes",
    "quel conseil donneriez-vous a un acheteur qui veut devenir CPO",
    "comment traitez-vous le dilemme prix vs qualite vs delai",
]

EDGE_CASES = [
    "le fournisseur est en monopole et le sait",
    "les prescripteurs court-circuitent les achats systematiquement",
    "le CEO impose un fournisseur pour des raisons personnelles",
    "le budget est coupe mais les attentes restent les memes",
    "l equipe achats est trop petite pour couvrir tout le scope",
]

def connect_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID)

def generate_comment(target):
    """Genere un commentaire personnalise pour un compte cible"""
    comment_type = random.choice(list(COMMENT_TEMPLATES.keys()))
    template = random.choice(COMMENT_TEMPLATES[comment_type])

    topic = random.choice(target["topics"])
    value_adds = VALUE_ADDS.get(topic, VALUE_ADDS["procurement strategy"])

    comment = template.format(
        name=target["name"].split()[0],
        value_add=random.choice(value_adds),
        example=random.choice(EXAMPLES),
        insight=random.choice(value_adds),
        context="on parle de categories strategiques ou le risque est eleve",
        nuance="dans le contexte europeen la reglementation change la donne notamment CBAM et CSRD",
        challenge="l applicabilite quand les ressources sont limitees",
        counter="la creativite compense souvent le manque de moyens",
        alternative="integrer le facteur humain et culturel dans l equation",
        question=random.choice(QUESTIONS),
        edge_case=random.choice(EDGE_CASES),
        scenario="les stakeholders internes ne voient pas la valeur des achats",
        story=random.choice(EXAMPLES),
        lesson="la preparation et la posture font 90% du resultat",
        new_rule="toujours calculer le TLC complet avant de conclure",
        data="selon Deloitte CPO Survey 2025 65% des CPOs placent le risque supply chain en priorite 1",
        conclusion="la fonction achats est en pleine mutation strategique vers l orchestration",
    )

    return comment_type, comment

def generate_daily_plan():
    """Genere le plan d engagement du jour : 5 comptes + 2 suggestions chacun"""
    today = datetime.now().strftime("%Y-%m-%d")
    day_number = datetime.now().timetuple().tm_yday

    # Rotation : 5 comptes differents chaque jour
    shuffled = TARGET_ACCOUNTS.copy()
    random.seed(day_number)
    random.shuffle(shuffled)
    selected = shuffled[:5]

    plan = []
    for target in selected:
        type1, comment1 = generate_comment(target)
        type2, comment2 = generate_comment(target)

        # S assurer que les 2 suggestions sont differentes
        attempts = 0
        while type1 == type2 and attempts < 5:
            type2, comment2 = generate_comment(target)
            attempts += 1

        plan.append([
            today,
            target["name"],
            target["role"],
            type1.replace("_", " "),
            comment1,
            type2.replace("_", " "),
            comment2,
            target["tone"],
            ""
        ])

    return plan

def write_plan(plan):
    """Ecrit le plan dans l onglet Engagement"""
    spreadsheet = connect_sheets()

    try:
        ws = spreadsheet.worksheet("Engagement")
    except:
        ws = spreadsheet.add_worksheet(title="Engagement", rows=500, cols=9)
        ws.update("A1:I1", [["Date", "Compte", "Role", "Type_Comment_1", "Suggestion_1", "Type_Comment_2", "Suggestion_2", "Ton", "Fait"]])

    existing = ws.get_all_values()
    next_row = len(existing) + 1

    ws.update(f"A{next_row}:I{next_row + len(plan) - 1}", plan)
    print(f"  [OK] Plan ecrit dans le Sheet (lignes {next_row}-{next_row + len(plan) - 1})")

def main():
    print("=" * 50)
    print("ENGAGEMENT AUTOMATION - PLAN DU JOUR")
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
        print(f"        {entry[4][:120]}")
        print(f"      Option 2 [{entry[5]}]:")
        print(f"        {entry[6][:120]}")
    print("")
    print("  " + "-" * 50)

    write_plan(plan)

    print("")
    print("  INSTRUCTIONS RAPIDES:")
    print("  1. Ouvre LinkedIn")
    print("  2. Va sur le profil de chaque personne")
    print("  3. Trouve leur dernier post")
    print("  4. Adapte UNE des 2 suggestions a leur post")
    print("  5. Publie le commentaire")
    print("  6. Marque OUI dans la colonne Fait du Sheet")
    print("  Temps total : 15 minutes max")
    print("")
    print("[DONE] Bon engagement ! L algo LinkedIn te recompensera.")

if __name__ == "__main__":
    main()
