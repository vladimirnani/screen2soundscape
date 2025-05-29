# overpass_to_osm.py

import os
import json
import requests
from requests.exceptions import HTTPError
from utils.llama_singleton import get_llm

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_llm = get_llm()

DEN_HAAG_CONTEXT = (
    "All queries should be scoped to Den Haag (’s-Gravenhage), "
    "admin_level=8, Netherlands."
)

def generate_overpass_query(question: str) -> str:
    prompt = (
        f"You are an expert at writing Overpass QL for OpenStreetMap. "
        f"{DEN_HAAG_CONTEXT}\n\n"
        f"Question: \"{question}\"\n\n"
        f"Return ONLY the Overpass QL query (no explanation)."
    )
    resp = _llm(prompt=prompt, max_tokens=256, temperature=0.0, stop=[";export", "; //"])
    q = resp["choices"][0]["text"].strip()
    if not q.endswith(";"):
        q += "\n;"
    return q

def run_overpass_query(query: str) -> dict:
    try:
        r = requests.post(OVERPASS_URL, data={"data": query})
        r.raise_for_status()
        return r.json()
    except HTTPError as e:
        raise RuntimeError(f"Overpass API error: {e}") from e

def summarize_results(question: str, data: dict) -> str:
    count = len(data.get("elements", []))
    prompt = (
        f"You have {count} results for the question: \"{question}\". "
        "Summarize in one clear paragraph the key findings "
        "(counts, types, accessibility, etc.)."
    )
    resp = _llm(prompt=prompt, max_tokens=150, temperature=0.3)
    text = resp["choices"][0]["text"].strip().replace("\n", " ")

    # De-duplicate sentences
    seen, out = set(), []
    for s in text.split(". "):
        s = s.strip().rstrip(".")
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return ". ".join(out) + "."

def process_question(question: str, save_json: bool = False, output_dir: str = "osm_assistant_output") -> str:
    ql = generate_overpass_query(question)
    try:
        data = run_overpass_query(ql)
    except RuntimeError as e:
        return f"❌ Error running Overpass query: {e}"

    if save_json:
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "raw.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return summarize_results(question, data)
