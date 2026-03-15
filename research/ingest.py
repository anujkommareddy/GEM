"""Phase 1: Data ingestion and normalization.

Loads the winner/loser sheet and script files, links them into a unified dataset.
"""

from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from typing import Optional

from models import LinkedRecord, Script, ShowEntry


# ---------------------------------------------------------------------------
# Sheet loading
# ---------------------------------------------------------------------------

def load_sheet_csv(path: str, label_column: str = "label", title_column: str = "title") -> list[ShowEntry]:
    """Load the winner/loser labels from a CSV export of the Google Sheet.

    Auto-detects columns by scanning headers for likely matches.
    """
    entries: list[ShowEntry] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        # Auto-detect column names (case-insensitive fuzzy match)
        col_map = _detect_columns(headers, title_column, label_column)

        for row in reader:
            title = row.get(col_map["title"], "").strip()
            raw_label = row.get(col_map["label"], "").strip()
            if not title:
                continue

            extra = {k: v for k, v in row.items()
                     if k not in (col_map["title"], col_map["label"]) and v and v.strip()}

            entries.append(ShowEntry(
                title=title,
                raw_label=raw_label,
                episode_title=row.get(col_map.get("episode", ""), "").strip() or None,
                network=row.get(col_map.get("network", ""), "").strip() or None,
                genre=row.get(col_map.get("genre", ""), "").strip() or None,
                year=_parse_year(row.get(col_map.get("year", ""), "")),
                extra=extra,
            ))
    return entries


def load_sheet_tsv(path: str, **kwargs) -> list[ShowEntry]:
    """Load from a TSV file (Google Sheets copy-paste format)."""
    # Convert TSV to CSV-compatible by re-reading
    with open(path, encoding="utf-8-sig") as f:
        content = f.read()
    # Write as temp CSV
    csv_path = path + ".tmp.csv"
    with open(csv_path, "w", encoding="utf-8") as f:
        for line in content.splitlines():
            f.write(",".join(f'"{cell}"' for cell in line.split("\t")) + "\n")
    try:
        return load_sheet_csv(csv_path, **kwargs)
    finally:
        os.remove(csv_path)


def load_sheet(path: str, **kwargs) -> list[ShowEntry]:
    """Auto-detect format and load sheet."""
    p = Path(path)
    if p.suffix == ".tsv":
        return load_sheet_tsv(path, **kwargs)
    elif p.suffix == ".csv":
        return load_sheet_csv(path, **kwargs)
    elif p.suffix == ".json":
        with open(path) as f:
            data = json.load(f)
        return [ShowEntry(**row) for row in data]
    else:
        # Try CSV first
        try:
            return load_sheet_csv(path, **kwargs)
        except Exception:
            return load_sheet_tsv(path, **kwargs)


# ---------------------------------------------------------------------------
# Script loading
# ---------------------------------------------------------------------------

def load_scripts(directory: str) -> list[Script]:
    """Load all script files from a directory.

    Supports: .txt, .pdf (text extraction), .fdx (Final Draft XML), .fountain
    Extracts show/episode title from filename conventions.
    """
    scripts: list[Script] = []
    script_dir = Path(directory)

    if not script_dir.exists():
        print(f"Warning: Script directory {directory} does not exist.")
        print(f"Place your script files in: {script_dir.absolute()}")
        return scripts

    for path in sorted(script_dir.rglob("*")):
        if path.is_dir():
            continue
        if path.suffix.lower() in (".txt", ".fountain", ".fdx", ".pdf", ".md"):
            script = _parse_script_file(path)
            if script:
                scripts.append(script)

    return scripts


def _parse_script_file(path: Path) -> Optional[Script]:
    """Parse a single script file."""
    try:
        if path.suffix.lower() == ".pdf":
            text = _extract_pdf_text(path)
        elif path.suffix.lower() == ".fdx":
            text = _extract_fdx_text(path)
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"Warning: Could not read {path}: {e}")
        return None

    if not text.strip():
        return None

    show_title, episode_title = _parse_filename(path)

    return Script(
        filename=path.name,
        show_title=show_title,
        episode_title=episode_title,
        text=text,
        word_count=len(text.split()),
        source_path=str(path),
    )


def _extract_pdf_text(path: Path) -> str:
    """Best-effort PDF text extraction."""
    try:
        import subprocess
        result = subprocess.run(
            ["pdftotext", str(path), "-"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return result.stdout
    except FileNotFoundError:
        pass

    # Fallback: try PyPDF2 if available
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except ImportError:
        pass

    print(f"Warning: Cannot extract text from PDF {path}. Install pdftotext or PyPDF2.")
    return ""


def _extract_fdx_text(path: Path) -> str:
    """Extract text from Final Draft .fdx files (XML format)."""
    import xml.etree.ElementTree as ET
    tree = ET.parse(str(path))
    root = tree.getroot()
    paragraphs = []
    for para in root.iter("Paragraph"):
        texts = [t.text or "" for t in para.iter("Text")]
        line = " ".join(texts).strip()
        if line:
            ptype = para.get("Type", "")
            if ptype:
                paragraphs.append(f"[{ptype}] {line}")
            else:
                paragraphs.append(line)
    return "\n".join(paragraphs)


def _parse_filename(path: Path) -> tuple[str, Optional[str]]:
    """Extract show title and optional episode title from filename.

    Handles patterns like:
    - "Show Name - S01E01 - Episode Title.txt"
    - "Show Name - Pilot.txt"
    - "Show_Name_101.txt"
    - "show-name.txt"
    - Subdirectory structure: scripts/ShowName/episode.txt
    """
    stem = path.stem
    parent_name = path.parent.name

    # Check if parent directory is the show name (scripts/ShowName/episode.txt)
    if parent_name.lower() not in ("scripts", "data", ".", ""):
        show_title = _clean_title(parent_name)
        episode_title = _clean_title(stem)
        return show_title, episode_title

    # Try "Show - S01E01 - Episode" pattern
    match = re.match(r"^(.+?)\s*[-–]\s*S\d+E\d+\s*[-–]\s*(.+)$", stem, re.IGNORECASE)
    if match:
        return _clean_title(match.group(1)), _clean_title(match.group(2))

    # Try "Show - Episode" pattern
    match = re.match(r"^(.+?)\s*[-–]\s*(.+)$", stem)
    if match:
        return _clean_title(match.group(1)), _clean_title(match.group(2))

    # Just the show name
    return _clean_title(stem), None


def _clean_title(raw: str) -> str:
    """Normalize a title string."""
    # Replace underscores and hyphens with spaces
    cleaned = re.sub(r"[_-]", " ", raw)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Title case if all lower or all upper
    if cleaned == cleaned.lower() or cleaned == cleaned.upper():
        cleaned = cleaned.title()
    return cleaned


# ---------------------------------------------------------------------------
# Title matching / linking
# ---------------------------------------------------------------------------

def normalize_for_matching(title: str) -> str:
    """Normalize a title for fuzzy matching."""
    t = title.lower()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    # Remove common prefixes/suffixes
    for word in ("the", "a", "an"):
        if t.startswith(word + " "):
            t = t[len(word) + 1:]
    return t


def link_data(shows: list[ShowEntry], scripts: list[Script]) -> list[LinkedRecord]:
    """Link show entries to scripts using title matching.

    Uses a multi-pass approach:
    1. Exact normalized match
    2. Substring/contains match
    3. Token overlap match
    """
    records: list[LinkedRecord] = []
    unmatched_scripts = list(scripts)

    for show in shows:
        show_norm = normalize_for_matching(show.title)
        matched: list[tuple[Script, float, str]] = []

        for script in unmatched_scripts:
            script_norm = normalize_for_matching(script.show_title)

            # Exact match
            if show_norm == script_norm:
                matched.append((script, 1.0, "exact"))
                continue

            # Contains match
            if show_norm in script_norm or script_norm in show_norm:
                shorter = min(len(show_norm), len(script_norm))
                longer = max(len(show_norm), len(script_norm))
                conf = shorter / longer if longer > 0 else 0
                if conf > 0.5:
                    matched.append((script, conf, "contains"))
                    continue

            # Token overlap
            show_tokens = set(show_norm.split())
            script_tokens = set(script_norm.split())
            if show_tokens and script_tokens:
                overlap = len(show_tokens & script_tokens)
                total = len(show_tokens | script_tokens)
                jaccard = overlap / total
                if jaccard > 0.5:
                    matched.append((script, jaccard, "token_overlap"))

        # Build record
        record_scripts = []
        for s, conf, method in matched:
            record_scripts.append(s)
            if s in unmatched_scripts:
                unmatched_scripts.remove(s)

        best_conf = max((c for _, c, _ in matched), default=1.0)
        best_method = next((m for _, _, m in matched if m == "exact"), "fuzzy")

        records.append(LinkedRecord(
            show=show,
            scripts=record_scripts,
            match_confidence=best_conf,
            match_method=best_method if matched else "unmatched",
        ))

    # Report unmatched scripts
    if unmatched_scripts:
        print(f"\n⚠ {len(unmatched_scripts)} scripts could not be matched to any show:")
        for s in unmatched_scripts:
            print(f"  - {s.filename} (parsed title: '{s.show_title}')")

    matched_count = sum(1 for r in records if r.scripts)
    print(f"\n✓ Linked {matched_count}/{len(shows)} shows to scripts")

    return records


def save_linked_dataset(records: list[LinkedRecord], output_path: str):
    """Save the linked dataset to JSON."""
    data = [r.model_dump() for r in records]
    # Don't save full script text in the linked dataset — too large
    for entry in data:
        for script in entry.get("scripts", []):
            script["text"] = f"[{script.get('word_count', 0)} words — see source file]"

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"✓ Saved linked dataset to {output_path}")


def load_linked_dataset(path: str) -> list[LinkedRecord]:
    """Load a previously saved linked dataset."""
    with open(path) as f:
        data = json.load(f)
    return [LinkedRecord(**entry) for entry in data]


# ---------------------------------------------------------------------------
# Column detection helpers
# ---------------------------------------------------------------------------

def _detect_columns(headers: list[str], title_hint: str, label_hint: str) -> dict[str, str]:
    """Auto-detect which columns map to title, label, etc."""
    col_map: dict[str, str] = {}
    lower_headers = {h.lower().strip(): h for h in headers}

    # Title column
    for candidate in [title_hint, "title", "show", "show_name", "show name", "series", "name"]:
        if candidate.lower() in lower_headers:
            col_map["title"] = lower_headers[candidate.lower()]
            break
    if "title" not in col_map and headers:
        col_map["title"] = headers[0]

    # Label column
    for candidate in [label_hint, "label", "winner", "result", "outcome", "status",
                      "winner/loser", "winner_loser", "w/l", "category"]:
        if candidate.lower() in lower_headers:
            col_map["label"] = lower_headers[candidate.lower()]
            break
    if "label" not in col_map and len(headers) > 1:
        col_map["label"] = headers[1]

    # Optional columns
    for field, candidates in {
        "episode": ["episode", "episode_title", "episode title", "ep"],
        "network": ["network", "channel", "platform", "streamer"],
        "genre": ["genre", "type", "category"],
        "year": ["year", "premiere", "air_date", "date", "premiere_year"],
    }.items():
        for c in candidates:
            if c in lower_headers:
                col_map[field] = lower_headers[c]
                break

    return col_map


def _parse_year(val: str) -> Optional[int]:
    if not val:
        return None
    match = re.search(r"(19|20)\d{2}", val.strip())
    return int(match.group()) if match else None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python ingest.py <sheet_path> [scripts_dir]")
        print()
        print("Loads your Google Sheet data and script files, links them, and")
        print("saves a normalized dataset.")
        print()
        print("  sheet_path   Path to CSV/TSV export of your labeled sheet")
        print("  scripts_dir  Directory containing script files (default: data/scripts/)")
        sys.exit(1)

    sheet_path = sys.argv[1]
    scripts_dir = sys.argv[2] if len(sys.argv) > 2 else "data/scripts"

    print(f"Loading sheet from {sheet_path}...")
    shows = load_sheet(sheet_path)
    print(f"  Found {len(shows)} show entries")

    # Show label distribution
    labels = {}
    for s in shows:
        l = s.raw_label.lower().strip()
        labels[l] = labels.get(l, 0) + 1
    print(f"  Label distribution: {labels}")

    print(f"\nLoading scripts from {scripts_dir}...")
    scripts = load_scripts(scripts_dir)
    print(f"  Found {len(scripts)} scripts")

    print("\nLinking shows to scripts...")
    records = link_data(shows, scripts)

    output_path = "data/linked_dataset.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    save_linked_dataset(records, output_path)
