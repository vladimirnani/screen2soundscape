# run_assistant.py
import warnings
import transformers
warnings.filterwarnings("ignore")
transformers.logging.set_verbosity_error()

import torch
import logging
import requests
import argparse
import os
import json
import time
from langdetect import detect
from deep_translator import GoogleTranslator
from utils.transcribe import record_and_transcribe
from utils.speak import speak
from utils.question_to_overpass import (
    parse_question,
    build_overpass_query
)
from utils.overpass_to_osm import (
    analyze_barriers,
    run_overpass_query,
    summarize_results,
    summarize_route
)

os.environ["TRANSFORMERS_VERBOSITY"] = "error"

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LAST_QUERY = None

def detect_language(text):
    try:
        return detect(text)
    except Exception:
        return "unknown"

def get_question_and_language(text=None, text_file=None):
    if text:
        return text.strip(), detect_language(text)
    elif text_file and os.path.isfile(text_file):
        with open(text_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
        return content, detect_language(content)
    else:
        return record_and_transcribe()

def get_directions(start, end, mode="walk"):
    profile = {"walk": "foot", "drive": "car", "bike": "bike"}.get(mode.lower(), "foot")
    url = f"https://router.project-osrm.org/route/v1/{profile}/{start[1]},{start[0]};{end[1]},{end[0]}"
    params = {"overview": "simplified", "geometries": "geojson", "steps": "true"}
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

def main(speaker, language, speed, save_json, text, text_file, batch_examples):
    global LAST_QUERY

    example_questions = [
        "What is near Aula Magna right now?",
        "Are there any vegan restaurants near Aula Magna?",
        "What are the closest ATMs near Musée universitaire de Louvain?",
        "Which beaches near Lisbon are wheelchair accessible?",
        "Are there baby changing stations in Musée universitaire de Louvain?",
        "Show me cafes within 2 km of Amsterdam Central Station",
        "Find restaurants in Berlin",
        "Look for places near Eiffel Tower",
        "Where is Lyon?",
        "Is MOMA wheelchair accessible?",
        "What historical sites are near the Colosseum?",
        "Show me UNESCO World Heritage sites in India.",
        "Where can I find live jazz bars in New Orleans?",
        "What’s a good area for street food in Bangkok?",
        "Where can I find hostels near downtown Prague?",
        "Are there pet-friendly hotels in Zurich?",
        "Show me all libraries open past 8 PM in central London.",
        "Can I drive from Marseille to Nice via Avignon?",
        "Puis-je conduire de Marseille à Nice via Avignon ?",
        "How can I bike from Stanford University to Googleplex?",
        "What's the fastest public transport route from Heathrow to Covent Garden?",
        "Can I walk from the Louvre to Notre-Dame along the river?",
    ]

    if batch_examples:
        for i, q in enumerate(example_questions, 1):
            print(f"\n--- Example {i} ---\n❓ {q}")
            main(
                speaker=speaker,
                language=language,
                speed=speed,
                save_json=save_json,
                text=q,
                text_file=None,
                batch_examples=False
            )
        return

    logger.info("🕒 Step 1: Getting question (recording or from text)...")
    t0 = time.time()
    question, lang = get_question_and_language(text=text, text_file=text_file)
    logger.info(f"✅ Got question: [{lang}] {question}")
    t1 = time.time()

    # Repeat logic
    if question.lower().strip() in {"repeat", "again"} and isinstance(LAST_QUERY, dict):
        logger.info(f"🔁 Repeating last query: {LAST_QUERY['question']}")
        question, lang, params, summary = LAST_QUERY['question'], LAST_QUERY['lang'], LAST_QUERY['params'], LAST_QUERY['summary']
    else:
        try:
            params = parse_question(question)
            logger.info(f"✅ Parsed parameters: {params}")
        except Exception as e:
            logger.error(f"❌ parse_question failed: {e}")
            return
        t2 = time.time()

        if params.get("mode") == "public_transport":
            logger.warning("🚆 Public transport mode not yet implemented.")
            return

        # Handle route queries
        if params.get("mode") in ("route_check", "route_via"):
            try:
                logger.info("🛣️ Requesting OSRM directions...")
                directions = get_directions(params["start_coords"], params["end_coords"])
                summary = summarize_route(directions)

                obstacles = analyze_barriers(directions)
                if obstacles:
                    logger.info("🚧 Obstacles detected:")
                    for obs in obstacles:
                        logger.info(obs)
                    summary += "\n\nObstacle Warnings:\n" + "\n".join(obstacles)
            except Exception as e:
                logger.error(f"❌ Routing failed: {e}")
                return
        else:
            # Handle Overpass queries
            try:
                logger.info("📡 Building Overpass query...")
                query = build_overpass_query(params)

                logger.info("🛰️ Sending Overpass query...")
                overpass_start = time.time()
                results = run_overpass_query(query)
                overpass_end = time.time()

                logger.info(f"✅ Got {len(results.get('elements', []))} result(s).")
                if save_json:
                    os.makedirs("osm_assistant_output", exist_ok=True)
                    with open("osm_assistant_output/raw.json", "w", encoding="utf-8") as f:
                        json.dump(results, f, indent=2, ensure_ascii=False)

                logger.info("🧠 Summarizing...")
                summary = summarize_results(question, results)
                t3 = time.time()
            except Exception as e:
                logger.error(f"❌ Overpass query failed: {e}")
                return

        LAST_QUERY = {
            "question": question,
            "lang": lang,
            "params": params,
            "summary": summary,
            "place": params.get("place_name")
        }

    # Translate if needed
    logger.info("🌍 Translating summary...")
    lang_code = lang.lower()
    translated_summary = summary
    t4 = time.time()
    if lang_code not in ["en", "en_us", "en_newest"]:
        try:
            translated_summary = GoogleTranslator(source="en", target=lang_code).translate(summary)
        except Exception as e:
            logger.warning(f"⚠️ Translation failed: {e}")

    # Speak the response
    logger.info("🔊 Speaking...")
    try:
        speak(translated_summary, language=language or lang.upper(), speaker_key=speaker, speed=speed)
    except Exception as e:
        logger.error(f"❌ TTS failed: {e}")
        return
    t5 = time.time()

    # Timing diagnostics
    logger.info("⏱️ Step timings:")
    logger.info(f"  Step 1: Get question        {t1 - t0:.2f}s")
    logger.info(f"  Step 2: Parse               {t2 - t1:.2f}s")
    if 'overpass_start' in locals():
        logger.info(f"  Step 3: Overpass query      {overpass_end - overpass_start:.2f}s")
    logger.info(f"  Step 4: Summarization       {t3 - (overpass_end if 'overpass_end' in locals() else t2):.2f}s")
    logger.info(f"  Step 5: Translation         {t5 - t4:.2f}s")
    logger.info(f"  Step 6: TTS                 {time.time() - t5:.2f}s")
    logger.info(f"🎉 Total time:                {time.time() - t0:.2f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the OSM voice assistant.")
    parser.add_argument("--speaker", type=str, required=True)
    parser.add_argument("--language", type=str, default="EN_NEWEST")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--save-json", action="store_true")
    parser.add_argument("--text", type=str)
    parser.add_argument("--text-file", type=str)
    parser.add_argument("--batch-examples", action="store_true")  # ← ADD THIS LINE
    args = parser.parse_args()

    main(
        speaker=args.speaker,
        language=args.language,
        speed=args.speed,
        save_json=args.save_json,
        text=args.text,
        text_file=args.text_file,
        batch_examples=args.batch_examples  # ← PASS THIS ARG TOO
    )
