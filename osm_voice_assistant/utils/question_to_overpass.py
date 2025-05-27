# question_to_overpass.py
import re
import spacy
import json
from difflib import get_close_matches
from geopy.geocoders import Nominatim
import sys
import os
from langdetect import detect
from deep_translator import GoogleTranslator

nlp = spacy.load("en_core_web_sm")

STOPWORDS = {"is", "a", "an", "the", "in", "on", "at", "of", "to", "from", "with", "for", "near", "by"}

def detect_and_translate(question: str) -> str:
    lang = detect(question)
    if lang == "fr":
        try:
            translated = GoogleTranslator(source="fr", target="en").translate(question)
            print(f"🌍 Translated from French: '{question}' → '{translated}'")
            return translated
        except Exception as e:
            print(f"⚠️ Translation failed: {e}")
    return question


def load_text(source: str) -> list[str]:
    if os.path.isfile(source):
        with open(source, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    else:
        return [source]

# Load OSM tag map from JSON
TAG_MAP = {}
def load_tag_map(path):
    global TAG_MAP
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    for entry in raw.get("data", []):
        key = entry["key"]
        TAG_MAP[key] = (key, key)

# Geocoding utilities
def geocode_point(location: str):
    geolocator = Nominatim(user_agent="nl_overpass_converter")
    place = geolocator.geocode(location, exactly_one=True)
    if not place:
        raise ValueError(f"Could not geocode location: {location}")
    return place.latitude, place.longitude

def geocode_location(location: str):
    geolocator = Nominatim(user_agent="nl_overpass_converter")
    place = geolocator.geocode(location, exactly_one=True)
    if not place:
        raise ValueError(f"Could not geocode location: {location}")
    south, north, west, east = map(float, place.raw["boundingbox"])
    return south, west, north, east

def parse_question(question: str) -> dict:
    question = detect_and_translate(question)  # translate if needed
    doc = nlp(question.lower())
    params = {
        "tag_key": None, "tag_value": None,
        "bbox": None, "radius": None, "center": None,
        "mode": "tagged", "place_name": None,
        "start": None, "end": None, "poi": None,
        "start_coords": None, "end_coords": None, "poi_coords": None,
        "transport": "walk", "wheelchair_only": False
    }

    # Routing pattern
    m = re.search(r"(walk|drive|bus|train)?\s*from\s+(.+?)\s+to\s+(.+?)(?:\s+(?:past|via)\s+(an|a)?\s*(.+))?$", question, re.IGNORECASE)
    if m:
        mode, start, end, _, poi = m.groups()
        params["start"] = start.strip()
        params["end"] = end.strip()
        params["poi"] = poi.strip() if poi else None
        params["mode"] = "route_via" if poi else "route_check"
        if mode: params["transport"] = mode.lower()
        try:
            params["start_coords"] = geocode_point(params["start"])
            params["end_coords"] = geocode_point(params["end"])
            if params["poi"]:
                params["poi_coords"] = geocode_point(params["poi"])
        except ValueError as e:
            print(f"❌ Geocoding error: {e}")
        return params

    # Wheelchair accessible check
    m = re.search(r"is\s+(.+?)\s+wheelchair\s+accessible", question, re.IGNORECASE)
    if m:
        location = m.group(1).strip()
        try:
            params["center"] = geocode_point(location)
            params["place_name"] = location
            params["tag_key"] = "wheelchair"
            params["tag_value"] = "yes"
            params["mode"] = "tagged"
        except ValueError:
            pass
        return params

    # Nearest accessible supermarket
    m = re.search(r"(?:nearest|closest)\s+wheelchair\s+accessible\s+supermarket", question, re.IGNORECASE)
    if m:
        params.update({
            "tag_key": "shop", "tag_value": "supermarket",
            "wheelchair_only": True, "radius": 1000,
            "mode": "generic", "center": geocode_point("Amsterdam")
        })
        return params

    # Closest toilet
    m = re.search(r"(?:nearest|closest)\s+toilet", question, re.IGNORECASE)
    if m:
        params.update({
            "tag_key": "amenity", "tag_value": "toilets",
            "radius": 1000, "mode": "generic",
            "center": geocode_point("Amsterdam")
        })
        return params

    # Radius query
    m = re.search(r"within\s+(\d+)\s*km\s+of\s+(.+)", question, re.IGNORECASE)
    if m:
        params["radius"] = int(m.group(1)) * 1000
        try:
            params["center"] = geocode_point(m.group(2).strip())
        except ValueError:
            pass
        return params

    # Where is X → use boundary lookup via Overpass
    if re.match(r"where\s+is\s+(.+)", question, re.IGNORECASE):
        # Try spaCy NER
        for ent in doc.ents:
            if ent.label_ in {"GPE", "LOC"}:
                place_name = ent.text.strip().title()
                params["mode"] = "boundary_lookup"
                params["place_name"] = place_name
                return params
        
        # 🛑 Fallback: extract after "where is"
        m = re.match(r"where\s+is\s+(.+)", question, re.IGNORECASE)
        if m:
            place_name = m.group(1).strip().title()
            params["mode"] = "boundary_lookup"
            params["place_name"] = place_name
            return params


    # Places near X
    m = re.search(r"places\s+near\s+(.+)", question, re.IGNORECASE)
    if m:
        try:
            params["center"] = geocode_point(m.group(1).strip())
            params["radius"] = 500
            params["mode"] = "generic"
            return params
        except ValueError:
            pass

    # Try matching OSM tags
    location_found = any(ent.label_ in {"GPE", "LOC"} for ent in doc.ents)

    words = re.findall(r"\w+", question.lower())
    for word in words:
        if word in STOPWORDS or len(word) < 3:
            continue
        for term, (key, val) in TAG_MAP.items():
            if word == term:
                params["tag_key"], params["tag_value"] = key, val
                break

    if not params["tag_key"] and not location_found:
        for word in words:
            if word in STOPWORDS or len(word) < 3:
                continue
            close = get_close_matches(word, TAG_MAP.keys(), n=1, cutoff=0.8)
            if close:
                key, val = TAG_MAP[close[0]]
                print(f"🤖 Interpreted '{word}' as '{close[0]}'")
                params["tag_key"], params["tag_value"] = key, val
                break

    for ent in doc.ents:
        if ent.label_ in {"GPE", "LOC"}:
            try:
                params["bbox"] = geocode_location(ent.text)
                params["place_name"] = ent.text
                break
            except ValueError:
                continue

    return params

def build_overpass_query(params: dict) -> str:
    mode = params.get("mode")

    if mode == "geocode":
        lat, lon = params["center"]
        return f"📍 {params.get('place_name', 'Location')} is at latitude {lat:.5f}, longitude {lon:.5f}."

    elif mode == "boundary_lookup":
        name = params.get("place_name", "Unknown")
        return f"""[out:json][timeout:25];
relation
  ["boundary"="administrative"]
  ["name"="{name}"]
  ["admin_level"~"^(8|6|4)$"];
out body;
>;
out skel qt;"""

    elif mode == "generic":
        lat, lon = params["center"]
        r = params["radius"]
        tag_filter = f'["{params["tag_key"]}"="{params["tag_value"]}"]' if params.get("tag_key") else ""
        wheelchair_filter = '["wheelchair"="yes"]' if params.get("wheelchair_only") else ""

        return f"""[out:json][timeout:25];
(
  node{tag_filter}{wheelchair_filter}(around:{r},{lat},{lon});
  way{tag_filter}{wheelchair_filter}(around:{r},{lat},{lon});
  rel{tag_filter}{wheelchair_filter}(around:{r},{lat},{lon});
);
out center;"""

    elif mode == "route_check":
        lat1, lon1 = params["start_coords"]
        lat2, lon2 = params["end_coords"]
        south = min(lat1, lat2) - 0.01
        north = max(lat1, lat2) + 0.01
        west = min(lon1, lon2) - 0.01
        east = max(lon1, lon2) + 0.01

        return f"""[out:json][timeout:25];
(
  way["leisure"="park"]({south},{west},{north},{east});
  relation["leisure"="park"]({south},{west},{north},{east});
);
out center;"""

    elif mode == "route_via":
        lat1, lon1 = params["start_coords"]
        lat2, lon2 = params["end_coords"]
        lat3, lon3 = params["poi_coords"]
        south = min(lat1, lat2, lat3) - 0.01
        north = max(lat1, lat2, lat3) + 0.01
        west = min(lon1, lon2, lon3) - 0.01
        east = max(lon1, lon2, lon3) + 0.01
        poi_name = params["poi"].lower()

        return f"""[out:json][timeout:25];
(
  node["name"~"{poi_name}", i]({south},{west},{north},{east});
  way["name"~"{poi_name}", i]({south},{west},{north},{east});
  relation["name"~"{poi_name}", i]({south},{west},{north},{east});
);
out center;"""

    else:
        key, value = params.get("tag_key"), params.get("tag_value")
        tag_filter = f'[{key}="{value}"]' if key and value else ""

        if params.get("bbox"):
            south, west, north, east = params["bbox"]
            return f"""[out:json][timeout:25];
(
  node{tag_filter}({south},{west},{north},{east});
  way{tag_filter}({south},{west},{north},{east});
  rel{tag_filter}({south},{west},{north},{east});
);
out center;"""
        elif params.get("center"):
            lat, lon = params["center"]
            r = params.get("radius", 500)
            return f"""[out:json][timeout:25];
(
  node{tag_filter}(around:{r},{lat},{lon});
  way{tag_filter}(around:{r},{lat},{lon});
  rel{tag_filter}(around:{r},{lat},{lon});
);
out center;"""
        else:
            raise ValueError("No area specified.")


if __name__ == "__main__":
    input_arg = sys.argv[1] if len(sys.argv) > 1 else "examples"

    output_lines = []
    save_to_file = False
    output_filename = None

    if input_arg.lower() == "examples":
        examples = [
            "Find restaurants in Berlin",
            "Show me cafes within 2 km of Amsterdam Central Station",
            "Where is Lyon?",
            "Look for places near Eiffel Tower",
            "Can I drive from Marseille to Nice via Avignon?",
            "Is MOMA wheelchair accessible?",
            "Puis-je conduire de Marseille à Nice via Avignon ?"
        ]
    elif os.path.isfile(input_arg):
        examples = load_text(input_arg)
        save_to_file = True
        base_name = os.path.splitext(os.path.basename(input_arg))[0]
        os.makedirs("overpass_query", exist_ok=True)
        output_filename = os.path.join("overpass_query", f"{base_name}_overpass.txt")
    else:
        print(f"❌ Input '{input_arg}' is not a valid file or 'examples'.")
        sys.exit(1)

    for ex in examples:
        print("Question:", ex)
        params = parse_question(ex)
        try:
            result = build_overpass_query(params)
            print("Overpass query or result:")
            print(result)
            if save_to_file:
                output_lines.append(f"# {ex}\n{result}\n")
        except ValueError as e:
            print("❌", e)
            if save_to_file:
                output_lines.append(f"# {ex}\n# ❌ {e}\n")

        print()

    if save_to_file and output_filename:
        with open(output_filename, "w", encoding="utf-8") as out_file:
            out_file.writelines(line if line.endswith("\n") else line + "\n" for line in output_lines)
        print(f"✅ Overpass queries saved to: {output_filename}")
