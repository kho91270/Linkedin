# smart_scheduler.py - Optimisation intelligente du calendrier

import os
import json
import random
from datetime import datetime
from collections import defaultdict

METRICS_FILE = "metrics_history.json"
SCHEDULE_FILE = "smart_schedule.json"

DEFAULT_SLOTS = [
    {"day": "Tuesday", "time": "07:00", "pillar": "terrain"},
    {"day": "Thursday", "time": "08:30", "pillar": "analyste"},
    {"day": "Saturday", "time": "09:00", "pillar": "conversation"},
]

TIME_SLOTS_TO_TEST = ["07:00", "08:00", "08:30", "12:00", "17:30", "18:30"]


def load_metrics():
    if os.path.exists(METRICS_FILE):
        with open(METRICS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"posts_metrics": []}


def load_schedule():
    if os.path.exists(SCHEDULE_FILE):
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"slots": DEFAULT_SLOTS, "optimizations": [], "last_updated": None}


def save_schedule(schedule):
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)


def analyze_best_pillar_by_day(metrics):
    posts = metrics.get("posts_metrics", [])
    if len(posts) < 10:
        return None
    day_pillar_scores = defaultdict(lambda: defaultdict(list))
    for p in posts:
        try:
            day = datetime.strptime(p["date"], "%Y-%m-%d").strftime("%A")
            pillar = p.get("pillar", "unknown")
            score = p.get("score", 0)
            day_pillar_scores[day][pillar].append(score)
        except (ValueError, KeyError):
            continue
    best_combos = {}
    for day, pillars in day_pillar_scores.items():
        best_pillar = None
        best_avg = 0
        for pillar, scores in pillars.items():
            if len(scores) >= 2:
                avg = sum(scores) / len(scores)
                if avg > best_avg:
                    best_avg = avg
                    best_pillar = pillar
        if best_pillar:
            best_combos[day] = {"pillar": best_pillar, "avg_score": round(best_avg, 1)}
    return best_combos


def analyze_best_time(metrics):
    posts = metrics.get("posts_metrics", [])
    if len(posts) < 10:
        return None
    time_scores = defaultdict(list)
    for p in posts:
        pub_time = p.get("published_time", "08:30")
        hour = pub_time.split(":")[0] if ":" in pub_time else "08"
        bucket = "morning" if int(hour) < 12 else ("afternoon" if int(hour) < 17 else "evening")
        time_scores[bucket].append(p.get("score", 0))
    best_bucket = None
    best_avg = 0
    for bucket, scores in time_scores.items():
        if scores:
            avg = sum(scores) / len(scores)
            if avg > best_avg:
                best_avg = avg
                best_bucket = bucket
    time_map = {"morning": "08:00", "afternoon": "12:30", "evening": "18:00"}
    return {"best_bucket": best_bucket, "suggested_time": time_map.get(best_bucket, "08:30"), "avg_score": round(best_avg, 1)}


def analyze_best_format(metrics):
    posts = metrics.get("posts_metrics", [])
    if len(posts) < 10:
        return None
    format_scores = defaultdict(list)
    for p in posts:
        fmt = p.get("format", "texte")
        format_scores[fmt].append(p.get("score", 0))
    results = {}
    for fmt, scores in format_scores.items():
        if scores:
            results[fmt] = {"avg_score": round(sum(scores) / len(scores), 1), "count": len(scores)}
    return results


def optimize_schedule():
    print("[START] Smart Scheduler -- " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    metrics = load_metrics()
    schedule = load_schedule()
    optimizations = []
    best_combos = analyze_best_pillar_by_day(metrics)
    if best_combos:
        print("")
        print("[PILIER x JOUR] Meilleures combinaisons:")
        for day, data in best_combos.items():
            print("  " + day + ": " + data["pillar"] + " (score moy: " + str(data["avg_score"]) + ")")
        optimizations.append({"type": "pillar_by_day", "data": best_combos, "date": datetime.now().strftime("%Y-%m-%d")})
        for slot in schedule["slots"]:
            if slot["day"] in best_combos:
                old_pillar = slot["pillar"]
                new_pillar = best_combos[slot["day"]]["pillar"]
                if old_pillar != new_pillar:
                    print("  -> OPTIMISE: " + slot["day"] + " " + old_pillar + " -> " + new_pillar)
                    slot["pillar"] = new_pillar
    best_time = analyze_best_time(metrics)
    if best_time:
        print("")
        print("[TIMING] Meilleur creneau: " + str(best_time["best_bucket"]) + " (score moy: " + str(best_time["avg_score"]) + ")")
        optimizations.append({"type": "best_time", "data": best_time, "date": datetime.now().strftime("%Y-%m-%d")})
    best_format = analyze_best_format(metrics)
    if best_format:
        print("")
        print("[FORMAT] Performance par format:")
        for fmt, data in best_format.items():
            print("  " + fmt + ": score moy " + str(data["avg_score"]) + " (" + str(data["count"]) + " posts)")
        optimizations.append({"type": "best_format", "data": best_format, "date": datetime.now().strftime("%Y-%m-%d")})
    schedule["optimizations"] = optimizations
    schedule["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_schedule(schedule)
    print("")
    print("[DONE] Schedule optimise.")
    return schedule


def get_optimal_pillar_for_date(target_date):
    schedule = load_schedule()
    day_name = target_date.strftime("%A")
    for slot in schedule.get("slots", []):
        if slot["day"] == day_name:
            return slot["pillar"]
    pillar_rotation = ["terrain", "analyste", "conversation", "insight"]
    week_num = target_date.isocalendar()[1]
    day_index = target_date.weekday()
    index = (week_num + day_index) % len(pillar_rotation)
    return pillar_rotation[index]


def get_optimal_time():
    schedule = load_schedule()
    for opt in schedule.get("optimizations", []):
        if opt.get("type") == "best_time":
            return opt["data"].get("suggested_time", "08:30")
    return "08:30"


if __name__ == "__main__":
    optimize_schedule()
