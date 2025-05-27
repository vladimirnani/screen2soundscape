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
    question = detect_and_translate(question)
    doc = nlp(question.lower())
    params = {
        "tag_key": None, "tag_value": None,
        "bbox": None, "radius": None, "center": None,
        "mode": None, "place_name": None,
        "start": None, "end": None, "poi": None,
        "start_coords": None, "end_coords": None, "poi_coords": None,
        "transport": "walk", "wheelchair_only": False
    }

    # 🚦 ROUTING LOGIC
    m = re.search(r"(walk|drive|bike|bus|train)?\s*from\s+(.+?)\s+to\s+(.+?)(?:\s+(?:past|via)\s+(?:an|a)?\s*(.+))?$", question, re.IGNORECASE)
    if m:
        mode, start, end, poi = m.groups()
        params.update({
            "start": start.strip(), "end": end.strip(),
            "poi": poi.strip() if poi else None,
            "mode": "route_via" if poi else "route_check",
            "transport": mode.lower() if mode else "walk"
        })
        try:
            params["start_coords"] = geocode_point(params["start"])
            params["end_coords"] = geocode_point(params["end"])
            if params["poi"]:
                params["poi_coords"] = geocode_point(params["poi"])
        except ValueError as e:
            print(f"❌ Geocoding error: {e}")
        return params

    # 🦽 WHEELCHAIR ACCESSIBILITY CHECK
    m = re.search(r"is\s+(.+?)\s+wheelchair\s+accessible", question, re.IGNORECASE)
    if m:
        location = m.group(1).strip()
        try:
            params.update({
                "center": geocode_point(location),
                "place_name": location,
                "tag_key": "wheelchair",
                "tag_value": "yes",
                "mode": "generic"
            })
        except ValueError:
            pass
        return params

    # 🛒 ACCESSIBLE SUPERMARKET NEARBY
    if "wheelchair accessible supermarket" in question:
        params.update({
            "tag_key": "shop", "tag_value": "supermarket",
            "wheelchair_only": True, "radius": 1000,
            "mode": "generic",
            "center": geocode_point("Amsterdam")  # Default or mock location
        })
        return params

    # 🚻 NEAREST TOILET
    if re.search(r"(?:nearest|closest)\s+toilet", question, re.IGNORECASE):
        params.update({
            "tag_key": "amenity", "tag_value": "toilets",
            "radius": 1000, "mode": "generic",
            "center": geocode_point("Amsterdam")
        })
        return params

    # 📍 WITHIN X KM OF LOCATION
    m = re.search(r"within\s+(\d+)\s*km\s+of\s+(.+)", question, re.IGNORECASE)
    if m:
        radius_km, loc = m.groups()
        try:
            params.update({
                "radius": int(radius_km) * 1000,
                "center": geocode_point(loc.strip()),
                "mode": "generic"
            })
        except ValueError:
            pass
        return params

    # 🗺️ WHERE IS LOCATION (BOUNDARY LOOKUP)
    if re.match(r"where\s+is\s+(.+)", question, re.IGNORECASE):
        for ent in doc.ents:
            if ent.label_ in {"GPE", "LOC"}:
                params.update({
                    "mode": "boundary_lookup",
                    "place_name": ent.text.strip().title()
                })
                return params

        # Fallback
        m = re.match(r"where\s+is\s+(.+)", question, re.IGNORECASE)
        if m:
            params.update({
                "mode": "boundary_lookup",
                "place_name": m.group(1).strip().title()
            })
            return params

    # 🔍 PLACES NEAR X
    m = re.search(r"places\s+near\s+(.+)", question, re.IGNORECASE)
    if m:
        try:
            params.update({
                "center": geocode_point(m.group(1).strip()),
                "radius": 500,
                "mode": "generic"
            })
            return params
        except ValueError:
            pass

    # 🏷️ TAG MATCHING OR SEMANTIC SEARCH
    words = [w for w in re.findall(r"\w+", question.lower()) if w not in STOPWORDS and len(w) > 2]
    found_tag = False

    for word in words:
        for term, (key, val) in TAG_MAP.items():
            if word == term:
                params["tag_key"], params["tag_value"] = key, val
                found_tag = True
                break
        if found_tag:
            break

    # Fuzzy match fallback
    if not found_tag:
        for word in words:
            close = get_close_matches(word, TAG_MAP.keys(), n=1, cutoff=0.8)
            if close:
                key, val = TAG_MAP[close[0]]
                print(f"🤖 Interpreted '{word}' as '{close[0]}'")
                params["tag_key"], params["tag_value"] = key, val
                break

    # If we found a tag, set default location logic
    for ent in doc.ents:
        if ent.label_ in {"GPE", "LOC"}:
            try:
                params["bbox"] = geocode_location(ent.text)
                params["place_name"] = ent.text
                params["mode"] = "bbox"  # Will default to bbox-based in query builder
                return params
            except ValueError:
                continue

    # If we have tag but no bbox, try center
    if params.get("tag_key") and not params.get("mode"):
        params.update({
            "center": geocode_point("Berlin"),
            "radius": 1000,
            "mode": "generic"
        })

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
            # 🔍 Proximity / Discovery
            "What is around me right now?",  # generic, radius from current location
            "Are there any vegan restaurants near me?",  # tag + diet
            "What are the closest ATMs near Brandenburg Gate?",  # amenity=atm, location-based
            "Which beaches near Lisbon are wheelchair accessible?",  # natural=beach + wheelchair
            "Are there baby changing stations in JFK Terminal 4?",  # baby_changing=yes + location
            "Show me cafes within 2 km of Amsterdam Central Station",  # radius + tag
            "Find restaurants in Berlin",  # bbox + tag
            "Look for places near Eiffel Tower",  # generic

            # 📍 Location lookup
            "Where is Lyon?",  # boundary lookup
            "Is MOMA wheelchair accessible?",  # specific tag query on a named place

            # 🎭 Thematic queries
            "What historical sites are near the Colosseum?",  # historic tag + nearby
            "Show me UNESCO World Heritage sites in India.",  # heritage=unesco + bbox
            "Where can I find live jazz bars in New Orleans?",  # amenity=bar + music:genre=jazz
            "What’s a good area for street food in Bangkok?",  # cuisine=street_food
            "Where can I find hostels near downtown Prague?",  # tourism=hostel
            "Are there pet-friendly hotels in Zurich?",  # tourism=hotel + pets=yes
            "Show me all libraries open past 8 PM in central London.",  # amenity=library + opening_hours

            # 🧭 Route-based (handled but not with Overpass directly)
            "Can I drive from Marseille to Nice via Avignon?",
            "Puis-je conduire de Marseille à Nice via Avignon ?",
            "How can I bike from Stanford University to Googleplex?",
            "What's the fastest public transport route from Heathrow to Covent Garden?",
            "Can I walk from the Louvre to Notre-Dame along the river?",
            "How long does it take to drive from Barcelona to Valencia?"
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
