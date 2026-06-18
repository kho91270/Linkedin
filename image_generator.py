# image_generator.py - Generation images LinkedIn via Leonardo AI

import os
import json
import time
import requests
from datetime import datetime
from groq import Groq

LEONARDO_API_KEY = os.environ.get("LEONARDO_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

client = Groq(api_key=GROQ_API_KEY)
GROQ_MODEL = "llama-3.3-70b-versatile"

IMAGES_DIR = "generated_images"


def generate_image_prompt(post_content, pillar):
    prompt = (
        "Based on this LinkedIn post about procurement, generate a SHORT image prompt for AI image generator.\n\n"
        "Post excerpt: " + post_content[:300] + "\n"
        "Pillar: " + pillar + "\n\n"
        "Rules:\n"
        "- Professional, corporate style\n"
        "- Clean, minimal design\n"
        "- Color palette: navy blue, white, light blue accents\n"
        "- NO text, NO words, NO letters in the image\n"
        "- Abstract or metaphorical representation\n"
        "- Max 100 words\n\n"
        "Return ONLY the image prompt."
    )
    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        defaults = {
            "terrain": "Professional business meeting, handshake, modern office, navy blue tones, minimal",
            "analyste": "Futuristic technology dashboard, data visualization, blue holographic, corporate",
            "conversation": "Two professionals discussing, thought bubbles, clean minimal illustration",
            "insight": "Single lightbulb illuminated, dark navy background, clean minimal premium",
        }
        return defaults.get(pillar, defaults["terrain"])


def create_leonardo_generation(image_prompt):
    if not LEONARDO_API_KEY:
        print("[SIMULATE] Leonardo generation simulee")
        return {"generation_id": "sim_" + datetime.now().strftime("%Y%m%d%H%M%S"), "status": "simulated"}
    url = "https://cloud.leonardo.ai/api/rest/v1/generations"
    headers = {"Authorization": "Bearer " + LEONARDO_API_KEY, "Content-Type": "application/json"}
    payload = {
        "prompt": image_prompt,
        "negative_prompt": "text, words, letters, numbers, watermark, blurry, low quality, cartoon",
        "modelId": "6bef9f1b-29cb-40c7-b9df-32b51c1f67d3",
        "width": 1080,
        "height": 1080,
        "num_images": 1,
        "guidance_scale": 7,
        "num_inference_steps": 30,
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            data = response.json()
            gen_id = data.get("sdGenerationJob", {}).get("generationId")
            return {"generation_id": gen_id, "status": "pending"}
        else:
            return {"status": "error", "code": response.status_code}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_generation_result(generation_id):
    if not LEONARDO_API_KEY or generation_id.startswith("sim_"):
        return {"status": "simulated", "url": None}
    url = "https://cloud.leonardo.ai/api/rest/v1/generations/" + generation_id
    headers = {"Authorization": "Bearer " + LEONARDO_API_KEY}
    for attempt in range(30):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                gen = data.get("generations_by_pk", {})
                status = gen.get("status")
                if status == "COMPLETE":
                    images = gen.get("generated_images", [])
                    if images:
                        return {"status": "complete", "url": images[0].get("url")}
                elif status == "FAILED":
                    return {"status": "failed"}
            time.sleep(10)
        except Exception:
            time.sleep(10)
    return {"status": "timeout"}


def download_image(image_url, filename):
    os.makedirs(IMAGES_DIR, exist_ok=True)
    filepath = os.path.join(IMAGES_DIR, filename)
    try:
        response = requests.get(image_url, timeout=30)
        if response.status_code == 200:
            with open(filepath, "wb") as f:
                f.write(response.content)
            return filepath
    except Exception:
        pass
    return None


def generate_post_image(post):
    content = post.get("content_fr") or post.get("content", "")
    pillar = post.get("pillar", "terrain")
    print("[1/3] Generation du prompt image...")
    image_prompt = generate_image_prompt(content, pillar)
    print("       Prompt: " + image_prompt[:80] + "...")
    print("[2/3] Lancement generation Leonardo...")
    result = create_leonardo_generation(image_prompt)
    if result.get("status") in ["simulated", "error"]:
        return {"status": result["status"], "prompt": image_prompt}
    gen_id = result.get("generation_id")
    print("[3/3] Attente du resultat...")
    final = get_generation_result(gen_id)
    if final.get("status") == "complete" and final.get("url"):
        date_str = datetime.now().strftime("%Y%m%d_%H%M")
        filename = "img_" + date_str + "_" + pillar + ".png"
        local_path = download_image(final["url"], filename)
        return {"status": "complete", "url": final["url"], "local_path": local_path, "prompt": image_prompt}
    return final


if __name__ == "__main__":
    print("Image Generator ready.")
