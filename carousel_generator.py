# carousel_generator.py - Transforme un post en carrousel HTML LinkedIn

import os
import json
from datetime import datetime
from groq import Groq

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)
GROQ_MODEL = "llama-3.3-70b-versatile"

CAROUSEL_DIR = "carousels"


def post_to_carousel_slides(content, pillar, lang="fr"):
    if lang == "fr":
        prompt = (
            "Transforme ce post LinkedIn en CARROUSEL de 6-8 slides.\n\n"
            "POST:\n" + content + "\n\n"
            "Format JSON:\n"
            "{\n"
            "    \"title\": \"Titre du carrousel\",\n"
            "    \"slides\": [\n"
            "        {\"slide\": 1, \"type\": \"cover\", \"main_text\": \"...\", \"subtitle\": \"...\"},\n"
            "        {\"slide\": 2, \"type\": \"problem\", \"main_text\": \"...\", \"subtitle\": \"...\"},\n"
            "        {\"slide\": 3, \"type\": \"content\", \"main_text\": \"...\", \"subtitle\": \"...\"},\n"
            "        {\"slide\": 4, \"type\": \"content\", \"main_text\": \"...\", \"subtitle\": \"...\"},\n"
            "        {\"slide\": 5, \"type\": \"content\", \"main_text\": \"...\", \"subtitle\": \"...\"},\n"
            "        {\"slide\": 6, \"type\": \"takeaway\", \"main_text\": \"...\", \"subtitle\": \"...\"},\n"
            "        {\"slide\": 7, \"type\": \"cta\", \"main_text\": \"...\", \"subtitle\": \"...\"}\n"
            "    ]\n"
            "}\n\n"
            "Regles:\n"
            "- Texte TRES court par slide (max 20 mots)\n"
            "- Slide 1: hook (cover)\n"
            "- Slide 2: probleme\n"
            "- Slides 3-5: points cles\n"
            "- Slide 6: takeaway\n"
            "- Slide 7: CTA + question\n\n"
            "Reponds UNIQUEMENT en JSON."
        )
    else:
        prompt = (
            "Transform this LinkedIn post into a 6-8 slide CAROUSEL.\n\n"
            "POST:\n" + content + "\n\n"
            "JSON format:\n"
            "{\n"
            "    \"title\": \"Carousel title\",\n"
            "    \"slides\": [\n"
            "        {\"slide\": 1, \"type\": \"cover\", \"main_text\": \"...\", \"subtitle\": \"...\"},\n"
            "        {\"slide\": 2, \"type\": \"problem\", \"main_text\": \"...\", \"subtitle\": \"...\"},\n"
            "        {\"slide\": 3, \"type\": \"content\", \"main_text\": \"...\", \"subtitle\": \"...\"},\n"
            "        {\"slide\": 4, \"type\": \"content\", \"main_text\": \"...\", \"subtitle\": \"...\"},\n"
            "        {\"slide\": 5, \"type\": \"content\", \"main_text\": \"...\", \"subtitle\": \"...\"},\n"
            "        {\"slide\": 6, \"type\": \"takeaway\", \"main_text\": \"...\", \"subtitle\": \"...\"},\n"
            "        {\"slide\": 7, \"type\": \"cta\", \"main_text\": \"...\", \"subtitle\": \"...\"}\n"
            "    ]\n"
            "}\n\n"
            "Rules: VERY short text per slide (max 20 words). Respond ONLY in JSON."
        )
    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=1200,
        )
        text = response.choices[0].message.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        return json.loads(text)
    except Exception as e:
        print("[ERROR] Carousel: " + str(e))
        return None


def generate_carousel_html(carousel_data, pillar):
    colors = {
        "terrain": {"bg": "#1B2A4A", "accent": "#2E86AB"},
        "analyste": {"bg": "#0D1B2A", "accent": "#E8871E"},
        "conversation": {"bg": "#1A1A2E", "accent": "#16213E"},
        "insight": {"bg": "#0F3460", "accent": "#533483"},
    }
    c = colors.get(pillar, colors["terrain"])
    slides_html = ""
    for slide in carousel_data.get("slides", []):
        main_text = slide.get("main_text", "")
        subtitle = slide.get("subtitle", "")
        font_size = "42px" if slide.get("type") == "cover" else "36px"
        sub_html = ""
        if subtitle:
            sub_html = "<div style=\"margin-top:30px;font-size:22px;opacity:0.8;\">" + subtitle + "</div>"
        slides_html += (
            "<div style=\"width:1080px;height:1080px;margin:20px auto;"
            "background:linear-gradient(135deg," + c["bg"] + " 0%," + c["accent"] + " 100%);"
            "color:white;display:flex;flex-direction:column;justify-content:center;"
            "align-items:center;text-align:center;padding:80px;box-sizing:border-box;"
            "border-radius:8px;page-break-after:always;position:relative;\">"
            "<div style=\"position:absolute;top:30px;right:40px;font-size:18px;opacity:0.5;\">" + str(slide["slide"]) + "</div>"
            "<div style=\"font-weight:700;line-height:1.3;font-size:" + font_size + ";max-width:900px;\">" + main_text + "</div>"
            + sub_html +
            "</div>\n"
        )
    html = (
        "<!DOCTYPE html>\n"
        "<html><head><meta charset=\"utf-8\"><style>body{margin:0;padding:20px;background:#f0f0f0;"
        "font-family:Segoe UI,Arial,sans-serif;}</style></head>\n"
        "<body>" + slides_html + "</body></html>"
    )
    return html


def generate_carousel(post, lang="fr"):
    content = post.get("content_" + lang) or post.get("content_fr") or post.get("content", "")
    pillar = post.get("pillar", "terrain")
    if not content:
        return None
    print("[1/2] Conversion en slides (" + lang.upper() + ")...")
    carousel_data = post_to_carousel_slides(content, pillar, lang)
    if not carousel_data:
        return None
    print("       -> " + str(len(carousel_data.get("slides", []))) + " slides")
    print("[2/2] Generation HTML...")
    html = generate_carousel_html(carousel_data, pillar)
    os.makedirs(CAROUSEL_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    filename = "carousel_" + date_str + "_" + pillar + "_" + lang + ".html"
    filepath = os.path.join(CAROUSEL_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    json_path = filepath.replace(".html", ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(carousel_data, f, ensure_ascii=False, indent=2)
    print("[OK] Carrousel: " + filepath)
    return {"html_path": filepath, "json_path": json_path, "slides": carousel_data}


if __name__ == "__main__":
    print("Carousel Generator ready.")
