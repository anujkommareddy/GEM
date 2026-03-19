"""
enrich_metadata.py — Wikipedia Show Metadata Enrichment Pipeline

For each show in the GEM corpus, fetches and structures publicly available
show-level metadata from Wikipedia. Saves as typed evidence alongside
existing pilot script evidence.

Usage:
    python3 src/enrich_metadata.py                      # Full run
    python3 src/enrich_metadata.py --dry-run            # No fetches, preview only
    python3 src/enrich_metadata.py --limit 20           # First N shows
    python3 src/enrich_metadata.py --show "Breaking Bad" # Single show
    python3 src/enrich_metadata.py --resume             # Skip already-enriched
    python3 src/enrich_metadata.py --report             # Coverage report only

Output:
    data/metadata/{show_id}.json        — per-show structured metadata
    data/metadata/_manifest.jsonl       — enrichment run manifest
    data/metadata/_coverage_report.json — field-level coverage stats

Storage:
    evidence_type = "show_metadata"
    source_type   = "wikipedia"
"""

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── Paths ────────────────────────────────────────────────────────────────────

BASE_DIR      = Path(".")
REGISTRY_FILE = BASE_DIR / "data/corpus/registry.jsonl"
METADATA_DIR  = BASE_DIR / "data/metadata"
MANIFEST_FILE = METADATA_DIR / "_manifest.jsonl"

WIKIPEDIA_REST = "https://en.wikipedia.org/api/rest_v1"
WIKIPEDIA_API  = "https://en.wikipedia.org/w/api.php"
USER_AGENT     = "GEM-Enrichment/1.0 (TV pilot research; contact: anujkommareddy@gmail.com)"

REQUEST_DELAY  = 1.0   # seconds between requests (Wikipedia rate limit courtesy)
MAX_RETRIES    = 2
REQUEST_TIMEOUT = 15

# ─── Title Extraction ─────────────────────────────────────────────────────────

def extract_clean_title(show_id: str) -> str:
    """Extract the best searchable show title from a messy show_id."""
    s = show_id

    # Pattern: "ShowNameEpisodeTitle_hash_slug-year" — extract before the hash
    # e.g. FargoThe_Crocodiles_Dilemma_29e0fe2e_... → "Fargo"
    hash_match = re.match(r'^([A-Za-z0-9_\-\s\.&\']+?)_[a-f0-9]{8}_', s)
    if hash_match:
        s = hash_match.group(1)
        # Strip underscores to get something like "FargoThe_Crocodiles_Dilemma"
        s_flat = s.replace('_', '')
        # Split at CamelCase boundary where second word starts with common episode words
        # e.g. FargoThe → Fargo | ManiacThe → Maniac | BallersPilot → Ballers
        EPISODE_STARTERS = r'(?:The|A|An|Pilot|Episode|Chapter|Part|Act|Into|In|Out|Up|Down|New|Old|Last|First|Dead|Dark|Light|Red|Black|White|Blue)'
        # Allow optional trailing chars (handles end-of-string like "BallersPilot")
        camel = re.match(rf'^([A-Z][a-zA-Z0-9]+?)({EPISODE_STARTERS})(?:[A-Z]|$)', s_flat)
        if camel:
            s = camel.group(1)
        else:
            # For numeric starts like "1899The" → "1899"
            num_camel = re.match(r'^(\d+)([A-Z])', s_flat)
            if num_camel:
                s = num_camel.group(1)

    # Replace underscores/hyphens with spaces
    s = re.sub(r'[_-]', ' ', s)

    # Remove episode/season markers
    s = re.sub(r'\b[Ss]\d+\s*[Ee][Pp]?\d+\b', '', s)
    s = re.sub(r'\b\d+x\d+\b', '', s)
    s = re.sub(r'\b1\d{2}\b', '', s)    # 3-digit episode codes like 101, 102

    # Remove common pilot script file noise
    s = re.sub(r'\bPilot\b', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\bEpisode\s+(One|Two|Three|Four|Five|\d+)\b', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\bSeason\s+\d+\b', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\bby\s+[A-Z][a-z]+(\s+[A-Z][a-z]+)+$', '', s)   # "by Joe Smith"
    s = re.sub(r'\s+\d{4}\s*$', '', s)   # trailing year

    # Remove time stamps (e.g. "12.00 PM 1.00 PM")
    s = re.sub(r'\b\d+\.\d+\s*(AM|PM)\b', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\b\d+:\d+\s*(AM|PM)\b', '', s, flags=re.IGNORECASE)

    # Remove large orphan numbers (file IDs) — but only if there are other words
    stripped = re.sub(r'\b\d{4,}\b', '', s).strip()
    if stripped:  # only remove if something remains; "1899" as full title stays
        s = stripped

    # Remove known file-slug noise phrases
    for noise in ['the ship', 'the chosen one', 'the crocodiles dilemma',
                  'godflame', 'karen laws', 'oriane messina fay rusling',
                  'the episode', 'episode one']:
        s = re.sub(rf'\b{re.escape(noise)}\b', '', s, flags=re.IGNORECASE)

    # Remove channel prefix artifacts (e.g. "AMC - ")
    s = re.sub(r'^(AMC|HBO|NBC|CBS|ABC|FOX|CW|FX|Netflix|Showtime|Prime)\s*[-–]\s*', '', s, flags=re.IGNORECASE)
    s = re.sub(r'^(AMC|HBO|NBC|CBS|ABC|FOX|CW|FX|Netflix|Showtime|Prime)\s+', '', s, flags=re.IGNORECASE)

    s = re.sub(r'\s+', ' ', s).strip()
    return s


def build_search_query(title: str) -> str:
    """Build a good Wikipedia search query for a TV show title."""
    return f"{title} TV series"


# ─── Wikipedia API Calls ──────────────────────────────────────────────────────

def _get(url: str, params: dict = None) -> Optional[dict]:
    """Make a GET request with retries. Returns parsed JSON or None on failure."""
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, headers=headers,
                                timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 404:
                return None
            else:
                logger.debug(f"HTTP {resp.status_code} for {url}")
                time.sleep(1)
        except requests.RequestException as e:
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
            else:
                logger.debug(f"Request failed: {e}")
    return None


def search_wikipedia(query: str) -> list[dict]:
    """Search Wikipedia and return top results."""
    data = _get(WIKIPEDIA_API, params={
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 5,
        "srnamespace": 0,
        "format": "json",
    })
    if not data:
        return []
    return data.get("query", {}).get("search", [])


def get_page_summary(title: str) -> Optional[dict]:
    """Fetch the Wikipedia REST summary for a page title."""
    encoded = requests.utils.quote(title.replace(" ", "_"), safe="()")
    return _get(f"{WIKIPEDIA_REST}/page/summary/{encoded}")


def get_page_wikitext(title: str) -> Optional[str]:
    """Fetch the raw wikitext for a page (for infobox parsing)."""
    data = _get(WIKIPEDIA_API, params={
        "action": "query",
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "titles": title,
        "format": "json",
        "formatversion": 2,
    })
    if not data:
        return None
    pages = data.get("query", {}).get("pages", [])
    if not pages:
        return None
    rev = pages[0].get("revisions", [])
    if not rev:
        return None
    return rev[0].get("slots", {}).get("main", {}).get("content", "")


# ─── Wikitext Infobox Parser ──────────────────────────────────────────────────

def _extract_infobox_block(wikitext: str) -> Optional[str]:
    """
    Find and return the full {{Infobox television ...}} block,
    correctly handling nested {{ }} braces.
    """
    start = re.search(r'\{\{[Ii]nfobox\s+television', wikitext)
    if not start:
        return None
    depth = 0
    i = start.start()
    while i < len(wikitext):
        if wikitext[i:i+2] == '{{':
            depth += 1
            i += 2
        elif wikitext[i:i+2] == '}}':
            depth -= 1
            i += 2
            if depth == 0:
                return wikitext[start.start():i]
        else:
            i += 1
    return None


def _extract_field_value(infobox: str, key: str) -> str:
    """
    Extract the value of a named field from an infobox, correctly handling
    nested {{ }} and [[ ]] so we get the full raw value.
    """
    pattern = re.compile(r'\|\s*' + re.escape(key) + r'\s*=\s*', re.IGNORECASE)
    m = pattern.search(infobox)
    if not m:
        return ""

    start = m.end()
    depth_curly = 0
    depth_square = 0
    i = start
    while i < len(infobox):
        c2 = infobox[i:i+2]
        if c2 == '{{':
            depth_curly += 1; i += 2
        elif c2 == '}}':
            if depth_curly > 0:
                depth_curly -= 1; i += 2
            else:
                break
        elif c2 == '[[':
            depth_square += 1; i += 2
        elif c2 == ']]':
            depth_square -= 1; i += 2
        elif infobox[i] == '|' and depth_curly == 0 and depth_square == 0:
            break
        else:
            i += 1

    return infobox[start:i].strip()


def _clean_wikitext(raw: str) -> str:
    """Strip wikitext markup from a raw field value."""
    # Unwrap {{Plainlist|* item\n* item}} → just the items
    raw = re.sub(r'\{\{[Pp]lainlist\s*\|(.*?)\}\}', r'\1', raw, flags=re.DOTALL)
    raw = re.sub(r'\{\{[Uu]bulleted\s+list\s*\|(.*?)\}\}',
                 lambda m: '\n'.join(m.group(1).split('|')), raw, flags=re.DOTALL)
    raw = re.sub(r'\{\{[Ff]latlist\s*\|(.*?)\}\}', r'\1', raw, flags=re.DOTALL)
    # [[link|display]] → display, [[link]] → link
    raw = re.sub(r'\[\[(?:[^\|\]]*\|)?([^\]]+)\]\]', r'\1', raw)
    # Remaining {{ }} templates — try to grab first positional arg or strip
    raw = re.sub(r'\{\{[^}|]*\|([^}|]*)[^}]*\}\}', r'\1', raw)
    raw = re.sub(r'\{\{[^}]*\}\}', '', raw)
    # Bold/italic
    raw = re.sub(r"'{2,3}([^']+)'{2,3}", r'\1', raw)
    # HTML tags
    raw = re.sub(r'<ref[^>]*>.*?</ref>', '', raw, flags=re.DOTALL)
    raw = re.sub(r'<[^>]+>', '', raw)
    # Wikitext bullet markers — strip leading * but keep newlines as separators
    raw = re.sub(r'^\s*\*+\s*', '\n', raw, flags=re.MULTILINE)
    # Collapse runs of spaces (not newlines) to single space
    raw = re.sub(r'[ \t]+', ' ', raw)
    # Collapse 3+ newlines to 2
    raw = re.sub(r'\n{3,}', '\n\n', raw)
    return raw.strip()


def parse_infobox(wikitext: str) -> dict:
    """Extract key-value pairs from a Wikipedia {{Infobox television}} block."""
    fields = {}
    if not wikitext:
        return fields

    block = _extract_infobox_block(wikitext)
    if not block:
        return fields

    # Known fields to extract
    FIELD_NAMES = [
        'name', 'genre', 'genres', 'first_aired', 'last_aired', 'airdate',
        'last_airdate', 'network', 'channel', 'runtime', 'num_seasons',
        'num_episodes', 'seasons', 'episodes', 'creator', 'creators',
        'showrunner', 'showrunners', 'starring', 'executive_producer',
        'executive_producers', 'production_company', 'company', 'distributor',
        'country', 'country_of_origin', 'language', 'language_of_origin',
        'type', 'status',
    ]

    for key in FIELD_NAMES:
        raw = _extract_field_value(block, key)
        if raw:
            cleaned = _clean_wikitext(raw)
            if cleaned:
                fields[key] = cleaned

    return fields


def clean_list_field(raw: str) -> list[str]:
    """Parse a cleaned wikitext field value into a Python list of strings."""
    if not raw:
        return []
    # Split on newlines, bullets, or comma-before-Capital
    items = re.split(r'[\n\r]+|\*\s*|;\s*|,\s*(?=[A-Z])', raw)
    cleaned = []
    for item in items:
        item = re.sub(r'\s+', ' ', item).strip().strip('*').strip()
        if item and len(item) > 1 and not item.startswith('{{'):
            cleaned.append(item)
    return cleaned


# ─── Metadata Structuring ─────────────────────────────────────────────────────

def pick_best_result(search_results: list, title: str) -> Optional[str]:
    """
    Pick the best Wikipedia page title from search results.
    Prefers results that contain the show title and 'TV' or 'series' in snippet.
    """
    title_lower = title.lower()
    tv_keywords = {'television', 'tv', 'series', 'sitcom', 'drama', 'miniseries',
                   'comedy', 'show', 'streaming', 'netflix', 'hbo', 'season'}

    for result in search_results:
        page_title = result.get("title", "")
        snippet = result.get("snippet", "").lower()

        # Skip disambiguation pages
        if "disambiguation" in page_title.lower():
            continue

        # Check if title words appear in page title
        title_words = set(title_lower.split())
        page_words = set(page_title.lower().split())
        overlap = title_words & page_words

        if len(overlap) >= max(1, len(title_words) // 2):
            # Boost if snippet mentions TV keywords
            if any(k in snippet for k in tv_keywords):
                return page_title

    # Fallback: return first non-disambiguation result
    for result in search_results:
        page_title = result.get("title", "")
        if "disambiguation" not in page_title.lower():
            return page_title

    return None


def structure_metadata(show_id: str, clean_title: str,
                        summary: dict, infobox: dict,
                        wiki_page_title: str) -> dict:
    """
    Build the structured metadata record from Wikipedia summary + infobox.
    """
    now = datetime.now(timezone.utc).isoformat()

    # ── Basic identity ──────────────────────────────────────────────────────
    title = summary.get("title") or infobox.get("name") or clean_title
    description = summary.get("description", "")
    extract = summary.get("extract", "")

    start_year = None
    end_year    = None

    # Try to parse years from infobox
    first_aired = infobox.get("first_aired", "") or infobox.get("airdate", "")
    last_aired  = infobox.get("last_aired",  "") or infobox.get("last_airdate", "")

    year_match = re.search(r'\b(19|20)\d{2}\b', first_aired)
    if year_match:
        start_year = int(year_match.group())

    year_match = re.search(r'\b(19|20)\d{2}\b', last_aired)
    if year_match:
        end_year = int(year_match.group())

    # Also try from description text
    if not start_year:
        year_match = re.search(r'\b(19[5-9]\d|20[012]\d)\b', extract)
        if year_match:
            start_year = int(year_match.group())

    # ── Format / Structure ──────────────────────────────────────────────────
    genre_raw = infobox.get("genre", "") or infobox.get("genres", "")
    genres = clean_list_field(genre_raw)

    # Runtime class inference
    runtime_raw = infobox.get("runtime", "")
    runtime_class = None
    if runtime_raw:
        mins = re.search(r'(\d+)', runtime_raw)
        if mins:
            m = int(mins.group(1))
            if m <= 15:
                runtime_class = "short-form"
            elif m <= 32:
                runtime_class = "half-hour"
            elif m <= 75:
                runtime_class = "hour"
            else:
                runtime_class = "feature-length"

    seasons_raw  = infobox.get("num_seasons",  "") or infobox.get("seasons", "")
    episodes_raw = infobox.get("num_episodes", "") or infobox.get("episodes", "")

    seasons_num  = None
    episodes_num = None
    n = re.search(r'\d+', seasons_raw)
    if n:
        seasons_num = int(n.group())
    n = re.search(r'\d+', episodes_raw)
    if n:
        episodes_num = int(n.group())

    # Format type from description or genre
    format_type = infer_format_type(genres, description, infobox)

    # ── Distribution ────────────────────────────────────────────────────────
    network_raw   = infobox.get("network", "") or infobox.get("channel", "")
    company_raw   = infobox.get("production_company", "") or infobox.get("company", "")
    distributor   = infobox.get("distributor", "")

    # ── Creative talent ─────────────────────────────────────────────────────
    creator_raw     = infobox.get("creator", "")   or infobox.get("creators", "")
    showrunner_raw  = infobox.get("showrunner", "") or infobox.get("showrunners", "")
    starring_raw    = infobox.get("starring", "")
    exec_prod_raw   = infobox.get("executive_producer", "") or infobox.get("executive_producers", "")

    # ── Country / Language ──────────────────────────────────────────────────
    country  = infobox.get("country", "") or infobox.get("country_of_origin", "")
    language = infobox.get("language", "") or infobox.get("language_of_origin", "")

    # ── Premise / content ───────────────────────────────────────────────────
    # Best premise text: first paragraph of extract (before == headings ==)
    premise_text = ""
    if extract:
        first_para = extract.split("\n\n")[0].strip()
        premise_text = first_para[:1500]  # cap at 1500 chars

    # ── Wikipedia page link ─────────────────────────────────────────────────
    source_url = ""
    if wiki_page_title:
        slug = wiki_page_title.replace(" ", "_")
        source_url = f"https://en.wikipedia.org/wiki/{slug}"

    return {
        # ── Evidence envelope ──────────────────────────────────────────────
        "show_id":            show_id,
        "evidence_type":      "show_metadata",
        "source_type":        "wikipedia",
        "source_url":         source_url,
        "wiki_page_title":    wiki_page_title or "",
        "retrieval_timestamp": now,
        "retrieval_confidence": assess_confidence(title, clean_title, wiki_page_title),

        # ── Basic identity ─────────────────────────────────────────────────
        "title":              title,
        "search_title_used":  clean_title,
        "alternate_titles":   [],
        "start_year":         start_year,
        "end_year":           end_year,
        "country":            clean_list_field(country) or None,
        "original_language":  clean_list_field(language) or None,

        # ── Format / structure ─────────────────────────────────────────────
        "genres":             genres,
        "format_type":        format_type,
        "runtime_class":      runtime_class,
        "seasons":            seasons_num,
        "episodes":           episodes_num,

        # ── Distribution ──────────────────────────────────────────────────
        "original_network":   clean_list_field(network_raw) or None,
        "production_companies": clean_list_field(company_raw) or None,
        "distributor":        clean_list_field(distributor) or None,

        # ── Creative talent ────────────────────────────────────────────────
        "creators":           clean_list_field(creator_raw) or None,
        "showrunners":        clean_list_field(showrunner_raw) or None,
        "lead_cast":          clean_list_field(starring_raw) or None,
        "executive_producers": clean_list_field(exec_prod_raw) or None,

        # ── Premise / content ──────────────────────────────────────────────
        "premise_summary":    premise_text or None,
        "wikipedia_extract":  extract[:3000] if extract else None,

        # ── Reception / outcome ────────────────────────────────────────────
        "reception_notes":    None,   # parsed separately if needed
        "awards_summary":     None,
        "cancellation_status": infer_cancellation(infobox, extract),
        "franchise_status":   None,
    }


def infer_format_type(genres: list, description: str, infobox: dict) -> Optional[str]:
    """Infer format type from genre, description, and infobox fields."""
    combined = " ".join(genres + [description]).lower()
    infobox_type = infobox.get("type", "").lower()

    if "anthology" in combined:
        return "anthology"
    if "animated" in combined or "animation" in combined:
        return "animated"
    if "limited series" in combined or "miniseries" in combined:
        return "limited_series"
    if "sitcom" in combined or "situation comedy" in combined:
        return "sitcom"
    if "procedural" in combined:
        return "procedural"
    if "docuseries" in combined or "documentary series" in combined:
        return "docuseries"
    if "reality" in combined:
        return "reality"
    if "comedy" in combined and "drama" in combined:
        return "dramedy"
    if "comedy" in combined:
        return "comedy"
    if "drama" in combined:
        return "drama"
    if "thriller" in combined or "horror" in combined:
        return "thriller_horror"
    if "sci-fi" in combined or "science fiction" in combined:
        return "sci_fi"
    if "fantasy" in combined:
        return "fantasy"
    return None


def infer_cancellation(infobox: dict, extract: str) -> Optional[str]:
    """Infer cancellation/renewal status from available text."""
    last_aired = infobox.get("last_aired", "")
    extract_lower = (extract or "").lower()

    if "cancelled" in extract_lower or "canceled" in extract_lower:
        return "cancelled"
    if "renewed" in extract_lower:
        return "renewed"
    if last_aired:
        year_match = re.search(r'\b(19|20)\d{2}\b', last_aired)
        if year_match:
            return f"ended_{year_match.group()}"
    return None


def assess_confidence(title: str, clean_title: str, wiki_page_title: str) -> str:
    """
    Rough confidence: high / medium / low / none.
    Based on how well the Wikipedia page title matches the expected show title.
    """
    if not wiki_page_title:
        return "none"

    title_words = set(clean_title.lower().split())
    page_words  = set(wiki_page_title.lower().split())
    overlap     = title_words & page_words

    if len(title_words) == 0:
        return "low"

    ratio = len(overlap) / len(title_words)

    if ratio >= 0.8:
        return "high"
    elif ratio >= 0.5:
        return "medium"
    elif ratio >= 0.25:
        return "low"
    else:
        return "very_low"


# ─── Main Enrichment Logic ────────────────────────────────────────────────────

def enrich_show(show_id: str, clean_title: str, dry_run: bool = False) -> dict:
    """
    Full enrichment pipeline for one show.
    Returns a result dict with status and metadata.
    """
    result = {
        "show_id":      show_id,
        "clean_title":  clean_title,
        "status":       "pending",
        "wiki_page":    None,
        "confidence":   "none",
        "error":        None,
    }

    if dry_run:
        result["status"] = "dry_run"
        return result

    try:
        # Step 1: Search Wikipedia
        query = build_search_query(clean_title)
        search_results = search_wikipedia(query)
        time.sleep(REQUEST_DELAY)

        if not search_results:
            result["status"] = "not_found"
            return result

        # Step 2: Pick best result
        wiki_page_title = pick_best_result(search_results, clean_title)
        if not wiki_page_title:
            result["status"] = "no_match"
            return result

        result["wiki_page"] = wiki_page_title

        # Step 3: Get page summary
        summary = get_page_summary(wiki_page_title) or {}
        time.sleep(REQUEST_DELAY)

        # Step 4: Get wikitext for infobox
        wikitext = get_page_wikitext(wiki_page_title) or ""
        time.sleep(REQUEST_DELAY)

        infobox = parse_infobox(wikitext)

        # Step 5: Structure metadata
        metadata = structure_metadata(
            show_id=show_id,
            clean_title=clean_title,
            summary=summary,
            infobox=infobox,
            wiki_page_title=wiki_page_title,
        )

        result["status"]     = "success"
        result["confidence"] = metadata["retrieval_confidence"]
        result["metadata"]   = metadata

    except Exception as e:
        result["status"] = "error"
        result["error"]  = str(e)
        logger.warning(f"Error enriching {show_id}: {e}")

    return result


def save_metadata(show_id: str, metadata: dict):
    """Save per-show metadata JSON."""
    out_path = METADATA_DIR / f"{show_id}.json"
    out_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")


def append_manifest(entry: dict):
    """Append a run record to the manifest."""
    with open(MANIFEST_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def already_enriched(show_id: str) -> bool:
    """Return True if a non-empty metadata file already exists."""
    p = METADATA_DIR / f"{show_id}.json"
    return p.exists() and p.stat().st_size > 100


# ─── Coverage Report ─────────────────────────────────────────────────────────

def generate_coverage_report():
    """Scan all per-show JSON files and compute field coverage stats."""
    files = list(METADATA_DIR.glob("*.json"))
    if not files:
        print("No metadata files found.")
        return

    total = 0
    by_status = {}
    by_confidence = {}
    field_counts = {}
    failed = []
    low_confidence = []

    TRACKED_FIELDS = [
        "title", "start_year", "end_year", "country", "original_language",
        "genres", "format_type", "runtime_class", "seasons", "episodes",
        "original_network", "production_companies", "creators", "showrunners",
        "lead_cast", "premise_summary", "cancellation_status",
    ]

    for fpath in files:
        if fpath.name.startswith("_"):
            continue
        try:
            d = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception:
            continue

        total += 1
        status = d.get("status", "unknown") if "status" in d else "data"
        conf   = d.get("retrieval_confidence", "unknown")

        by_confidence[conf] = by_confidence.get(conf, 0) + 1

        for field in TRACKED_FIELDS:
            val = d.get(field)
            if val is not None and val != "" and val != [] and val != {}:
                field_counts[field] = field_counts.get(field, 0) + 1

        if conf in ("low", "very_low", "none"):
            low_confidence.append({"show_id": d.get("show_id", fpath.stem),
                                   "confidence": conf,
                                   "wiki_page": d.get("wiki_page_title", "")})

    coverage = {
        field: {"count": field_counts.get(field, 0),
                "pct": round(field_counts.get(field, 0) / total * 100, 1) if total else 0}
        for field in TRACKED_FIELDS
    }

    report = {
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "total_shows":     total,
        "by_confidence":   by_confidence,
        "field_coverage":  coverage,
        "low_confidence_shows": low_confidence[:50],  # first 50 for review
    }

    report_path = METADATA_DIR / "_coverage_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Print summary
    print(f"\n{'='*65}")
    print(f"METADATA COVERAGE REPORT")
    print(f"{'='*65}")
    print(f"Total shows with metadata:  {total}")
    print(f"\nConfidence distribution:")
    for conf, count in sorted(by_confidence.items(), key=lambda x: -x[1]):
        print(f"  {conf:<12}  {count:>4}  ({count/total*100:.0f}%)")
    print(f"\nField coverage (top fields):")
    for field, stats in sorted(coverage.items(), key=lambda x: -x[1]["count"]):
        bar = "█" * int(stats["pct"] / 5)
        print(f"  {field:<40}  {stats['pct']:>5.1f}%  {bar}")
    print(f"\nShows with low/no confidence: {len(low_confidence)}")
    print(f"\nReport saved: {report_path}")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="GEM Wikipedia metadata enrichment")
    parser.add_argument("--dry-run",  action="store_true", help="No fetches, preview only")
    parser.add_argument("--limit",    type=int,   default=None, help="Only process first N shows")
    parser.add_argument("--show",     type=str,   default=None, help="Enrich a single show title")
    parser.add_argument("--resume",   action="store_true", help="Skip already-enriched shows")
    parser.add_argument("--report",   action="store_true", help="Coverage report only")
    parser.add_argument("--delay",    type=float, default=1.0, help="Seconds between requests")
    args = parser.parse_args()

    REQUEST_DELAY = args.delay

    METADATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.report:
        generate_coverage_report()
        return

    # Load corpus
    rows = [json.loads(l) for l in REGISTRY_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    logger.info(f"Corpus: {len(rows)} shows loaded")

    # Build work list
    work = []
    for row in rows:
        sid   = row["show_id"]
        title = extract_clean_title(sid)
        if not title or len(title) < 2:
            continue
        work.append((sid, title))

    # Filter to single show if requested
    if args.show:
        work = [(sid, t) for sid, t in work if args.show.lower() in t.lower()]
        if not work:
            print(f"No show found matching: {args.show}")
            sys.exit(1)

    # Skip already done if resuming
    if args.resume:
        before = len(work)
        work = [(sid, t) for sid, t in work if not already_enriched(sid)]
        logger.info(f"Resume: skipping {before - len(work)} already-enriched shows")

    # Apply limit
    if args.limit:
        work = work[:args.limit]

    logger.info(f"Shows to enrich: {len(work)}")

    if args.dry_run:
        print(f"\nDRY RUN — {len(work)} shows would be enriched:")
        for sid, title in work[:20]:
            print(f"  {title:<45}  [{sid[:50]}]")
        if len(work) > 20:
            print(f"  ... and {len(work) - 20} more")
        return

    # ── Run enrichment ────────────────────────────────────────────────────────
    run_id  = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    success = failed = skipped = 0

    for i, (sid, title) in enumerate(work, 1):
        logger.info(f"[{i}/{len(work)}] {title}")

        result = enrich_show(sid, title, dry_run=False)

        if result["status"] == "success":
            save_metadata(sid, result["metadata"])
            success += 1
            conf = result.get("confidence", "?")
            logger.info(f"  ✓  {result['wiki_page']}  [{conf}]")
        else:
            # Save a stub so we know we tried
            stub = {
                "show_id":             sid,
                "evidence_type":       "show_metadata",
                "source_type":         "wikipedia",
                "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
                "retrieval_confidence": "none",
                "status":              result["status"],
                "search_title_used":   title,
                "error":               result.get("error"),
            }
            save_metadata(sid, stub)
            failed += 1
            logger.info(f"  ✗  {result['status']}")

        append_manifest({
            "show_id":    sid,
            "title":      title,
            "status":     result["status"],
            "wiki_page":  result.get("wiki_page"),
            "confidence": result.get("confidence", "none"),
            "run_id":     run_id,
            "enriched_at": datetime.now(timezone.utc).isoformat(),
        })

    # ── Final summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"ENRICHMENT COMPLETE")
    print(f"{'='*55}")
    print(f"  Processed:  {len(work)}")
    print(f"  Success:    {success}  ({success/len(work)*100:.0f}%)" if work else "")
    print(f"  Failed:     {failed}")
    print(f"  Output:     {METADATA_DIR}/")
    print(f"{'='*55}\n")

    # Auto-generate coverage report
    generate_coverage_report()


if __name__ == "__main__":
    main()
