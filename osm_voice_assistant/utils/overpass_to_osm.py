# overpass_to_osm.py
import os
import json
import hashlib
import requests
from langdetect import detect
from utils.llama_singleton import get_llm

_llm = get_llm()

def run_overpass_query(query, endpoint="https://overpass-api.de/api/interpreter"):
    """
    Execute an Overpass QL query and return JSON results.
    """
    headers = {"Accept": "application/json"}
    response = requests.post(endpoint, data={"data": query}, headers=headers, timeout=60)
    response.raise_for_status()
    return response.json()

def run_overpass_query_cached(query, cache_dir="overpass_cache"):
    os.makedirs(cache_dir, exist_ok=True)
    key = hashlib.md5(query.encode()).hexdigest()
    cache_path = os.path.join(cache_dir, f"{key}.json")

    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    result = run_overpass_query(query)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result

def generate_overpass_query_llama(question: str, user_latlon=None) -> dict:
    """
    Generates Overpass QL using LLaMA-3.2-Instruct with:
    ✅ Structured JSON output
    ✅ Clarification fallback if ambiguous
    ✅ “Near me” handling if user_latlon provided
    ✅ Language detection for clarification messages
    """
    lang = detect(question)
    is_french = lang == "fr"

    system_prompt = (
        "You are an expert assistant that writes valid Overpass QL queries for OpenStreetMap.\n"
        "Return ONLY JSON with either:\n"
        "{ \"query\": \"<Overpass QL here>\" }\n"
        "or if unclear:\n"
        "{ \"clarification_needed\": true, \"clarification_question\": \"<clarifying question>\" }\n"
    )

    if user_latlon:
        lat, lon = user_latlon
        system_prompt += f"\nThe user's approximate location is at latitude {lat}, longitude {lon}.\n"

    if is_french:
        system_prompt += "\nIf clarification is needed, write the clarifying question in French.\n"

    prompt = (
        f"{system_prompt}\n"
        f"User question: \"{question}\"\n"
    )

    resp = _llm(prompt=prompt, max_tokens=512, temperature=0.0)
    raw = resp["choices"][0]["text"].strip()

    try:
        parsed = json.loads(raw)
        parsed["language"] = lang
        return parsed
    except json.JSONDecodeError:
        if raw.startswith("[out:json]") or "node" in raw:
            return {
                "query": raw,
                "clarification_needed": False,
                "clarification_question": None,
                "language": lang
            }
        else:
            return {
                "clarification_needed": True,
                "clarification_question": (
                    "Pouvez-vous préciser votre demande ?" if is_french else "Could you please clarify your request?"
                ),
                "language": lang
            }

def summarize_results(question: str, data: dict, language: str = "en") -> str:
    """
    Summarizes Overpass JSON results into a voice-friendly paragraph using LLaMA,
    with language-aware output.
    """
    elements = data.get("elements", [])
    count = len(elements)

    compressed = []
    for el in elements[:5]:
        tags = el.get("tags", {})
        name = tags.get("name")
        type_ = tags.get("amenity") or tags.get("shop") or tags.get("tourism") or tags.get("leisure")
        address = tags.get("addr:street") or tags.get("addr:full") or "(no address)"
        if name and type_:
            compressed.append(f"- {name} ({type_}), located at {address}")
        elif name:
            compressed.append(f"- {name}, located at {address}")
        elif type_:
            compressed.append(f"- A {type_} located at {address}")

    details = "\n".join(compressed) if compressed else "No detailed information available."

    prompt = (
        "You are a voice assistant summarizing OpenStreetMap Overpass results.\n"
        f"The user asked: \"{question}\"\n"
        f"There are {count} matching places. Some examples:\n"
        f"{details}\n"
        "Summarize this clearly, naturally, and concisely for voice output."
    )

    if language == "fr":
        prompt += "\nPlease respond in French.\n"

    resp = _llm(prompt=prompt, max_tokens=200, temperature=0.3)
    text = resp["choices"][0]["text"].strip().replace("\n", " ")

    # Deduplicate
    seen, out = set(), []
    for s in text.split(". "):
        s = s.strip().rstrip(".")
        if s and s not in seen:
            seen.add(s)
            out.append(s)

    return ". ".join(out) + "."

def summarize_route(directions_json):
    try:
        route = directions_json["routes"][0]
        leg = route["legs"][0]
        steps = leg["steps"]

        lines = [
            f"The route is about {round(route['distance'] / 1000, 1)} kilometers "
            f"and will take approximately {round(route['duration'] / 60)} minutes.",
            "Here are the step-by-step directions:"
        ]

        for i, step in enumerate(steps, 1):
            maneuver = step.get("maneuver", {})
            instruction = maneuver.get("instruction") or maneuver.get("type", "Move")
            name = step.get("name")
            line = f"{i}. {instruction}"
            if name:
                line += f" onto {name}"
            if step.get("duration"):
                line += f" for about {round(step['duration'] / 60, 1)} minutes"
            lines.append(line)

        return "\n".join(lines)
    except Exception as e:
        return f"⚠️ Could not summarize route: {e}"

def analyze_barriers(route_json, radius=15):
    coords = []
    for leg in route_json.get("routes", [])[0].get("legs", []):
        for step in leg.get("steps", []):
            for loc in step.get("geometry", {}).get("coordinates", []):
                lon, lat = loc
                coords.append((lat, lon))

    obstacles = []
    for lat, lon in coords[::10]:  # sample every ~10 points
        overpass_query = f"""
        [out:json];
        (
          node(around:{radius},{lat},{lon})["barrier"];
          node(around:{radius},{lat},{lon})["highway"="crossing"];
          node(around:{radius},{lat},{lon})["kerb"];
          node(around:{radius},{lat},{lon})["incline"];
        );
        out body;
        """
        result = run_overpass_query_cached(overpass_query)
        for el in result.get("elements", []):
            tags = el.get("tags", {})
            tag_desc = ", ".join(f"{k}={v}" for k, v in tags.items())
            obstacles.append(f"⚠️ Obstacle at ({el['lat']:.5f}, {el['lon']:.5f}): {tag_desc}")
    return obstacles

def process_question_with_llama(
    question: str,
    user_latlon=None,
    save_json: bool = False,
    output_dir: str = "osm_assistant_output"
) -> str:
    """
    Processes a question through:
    ✅ LLaMA-based Overpass QL generation
    ✅ Lat/lon fallback
    ✅ Clarification fallback
    ✅ Language-aware summarization
    """

    parsed = generate_overpass_query_llama(question, user_latlon=user_latlon)

    if parsed.get("clarification_needed"):
        return f"❓ {parsed.get('clarification_question')}"

    query = parsed.get("query")
    if not query:
        return "❌ Failed to generate Overpass QL."

    try:
        data = run_overpass_query_cached(query)
    except Exception as e:
        return f"❌ Error fetching Overpass data: {e}"

    if save_json:
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "raw.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return summarize_results(question, data, language=parsed.get("language", "en"))
