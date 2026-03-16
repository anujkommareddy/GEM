"""Phase 1: Data ingestion and normalization.

Loads the winner/loser sheet and script files, links them into a unified dataset.
Optimized for the actual GEM dataset: a CSV with show_name/pdf_file/label columns
and a pdf_backup/ folder of pilot scripts.
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

def load_sheet_csv(path: str) -> list[ShowEntry]:
    """Load the winner/loser labels from a CSV.

    Auto-detects columns by scanning headers for likely matches.
    """
    entries: list[ShowEntry] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        col_map = _detect_columns(headers)

        for row in reader:
            title = row.get(col_map["title"], "").strip()
            raw_label = row.get(col_map["label"], "").strip()
            if not title:
                continue

            # Capture pdf_file reference if present
            pdf_file = row.get(col_map.get("pdf_file", ""), "").strip() or None

            extra = {}
            for k, v in row.items():
                if k not in (col_map["title"], col_map["label"]) and v and v.strip():
                    extra[k] = v.strip()

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


def load_sheet(path: str) -> list[ShowEntry]:
    """Auto-detect format and load sheet."""
    p = Path(path)
    if p.suffix == ".json":
        with open(path) as f:
            data = json.load(f)
        return [ShowEntry(**row) for row in data]
    return load_sheet_csv(path)


# ---------------------------------------------------------------------------
# Script loading
# ---------------------------------------------------------------------------

def load_scripts(directory: str) -> list[Script]:
    """Load all script files from a directory (recursively).

    Supports: .txt, .pdf, .fdx, .fountain, .md
    """
    scripts: list[Script] = []
    script_dir = Path(directory)

    if not script_dir.exists():
        print(f"Warning: Script directory {directory} does not exist.")
        return scripts

    for path in sorted(script_dir.rglob("*")):
        if path.is_dir():
            continue
        # Skip the master list itself
        if "master pilots" in path.name.lower():
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
    """Extract show title and optional episode title from filename."""
    stem = path.stem
    parent_name = path.parent.name

    if parent_name.lower() not in ("scripts", "data", "pdf_backup", "txt_raw", ".", ""):
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

    return _clean_title(stem), None


def _clean_title(raw: str) -> str:
    """Normalize a title string."""
    cleaned = re.sub(r"[_-]", " ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned == cleaned.lower() or cleaned == cleaned.upper():
        cleaned = cleaned.title()
    return cleaned


# ---------------------------------------------------------------------------
# Linking: match sheet rows to script files
# ---------------------------------------------------------------------------

def link_data(
    shows: list[ShowEntry],
    scripts: list[Script],
    scripts_dir: str = "data/scripts/txt_raw",
) -> list[LinkedRecord]:
    """Link show entries to scripts.

    Primary strategy: use the pdf_file field from the sheet for direct filename match.
    Fallback: fuzzy title matching.
    """
    # Build filename -> Script lookup
    script_by_filename: dict[str, Script] = {}
    for s in scripts:
        script_by_filename[s.filename] = s
        script_by_filename[s.filename.lower()] = s

    records: list[LinkedRecord] = []
    matched = 0
    unmatched_shows: list[str] = []

    for show in shows:
        # Try direct filename match from the pdf_file extra field
        pdf_ref = show.extra.get("pdf_file", "")
        found_script = None
        match_method = "unmatched"

        if pdf_ref:
            # Direct match
            if pdf_ref in script_by_filename:
                found_script = script_by_filename[pdf_ref]
                match_method = "filename_exact"
            elif pdf_ref.lower() in script_by_filename:
                found_script = script_by_filename[pdf_ref.lower()]
                match_method = "filename_case_insensitive"

        # Fallback: fuzzy title matching against parsed show_title from scripts
        if not found_script:
            show_norm = normalize_for_matching(show.title)
            best_match = None
            best_score = 0.0

            for script in scripts:
                script_norm = normalize_for_matching(script.show_title)

                if show_norm == script_norm:
                    best_match = script
                    best_score = 1.0
                    break

                if show_norm in script_norm or script_norm in show_norm:
                    shorter = min(len(show_norm), len(script_norm))
                    longer = max(len(show_norm), len(script_norm))
                    score = shorter / longer if longer > 0 else 0
                    if score > best_score and score > 0.5:
                        best_match = script
                        best_score = score

                show_tokens = set(show_norm.split())
                script_tokens = set(script_norm.split())
                if show_tokens and script_tokens:
                    jaccard = len(show_tokens & script_tokens) / len(show_tokens | script_tokens)
                    if jaccard > best_score and jaccard > 0.5:
                        best_match = script
                        best_score = jaccard

            if best_match:
                found_script = best_match
                match_method = "title_fuzzy"

        if found_script:
            matched += 1
            records.append(LinkedRecord(
                show=show,
                scripts=[found_script],
                match_confidence=1.0 if "filename" in match_method else 0.8,
                match_method=match_method,
            ))
        else:
            unmatched_shows.append(show.title)
            records.append(LinkedRecord(
                show=show,
                scripts=[],
                match_confidence=0.0,
                match_method="unmatched",
            ))

    if unmatched_shows:
        print(f"\n  {len(unmatched_shows)} shows could not be matched to scripts")

    print(f"\n  Linked {matched}/{len(shows)} shows to scripts")
    return records


def normalize_for_matching(title: str) -> str:
    """Normalize a title for fuzzy matching."""
    t = title.lower()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    for word in ("the", "a", "an"):
        if t.startswith(word + " "):
            t = t[len(word) + 1:]
    return t


# ---------------------------------------------------------------------------
# Save / load linked dataset
# ---------------------------------------------------------------------------

def save_linked_dataset(records: list[LinkedRecord], output_path: str):
    """Save the linked dataset to JSON (without full script text)."""
    data = [r.model_dump() for r in records]
    for entry in data:
        for script in entry.get("scripts", []):
            script["text"] = f"[{script.get('word_count', 0)} words — see source file]"

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Saved linked dataset to {output_path}")


def load_linked_dataset(path: str) -> list[LinkedRecord]:
    """Load a previously saved linked dataset."""
    with open(path) as f:
        data = json.load(f)
    return [LinkedRecord(**entry) for entry in data]


# ---------------------------------------------------------------------------
# Column detection
# ---------------------------------------------------------------------------

def _detect_columns(headers: list[str]) -> dict[str, str]:
    """Auto-detect which columns map to title, label, pdf_file, etc."""
    col_map: dict[str, str] = {}
    lower_headers = {h.lower().strip(): h for h in headers}

    # Title column
    for candidate in ["show_name", "show name", "title", "show", "series", "name"]:
        if candidate in lower_headers:
            col_map["title"] = lower_headers[candidate]
            break
    if "title" not in col_map and headers:
        col_map["title"] = headers[0]

    # Label column
    for candidate in ["label", "winner/loser", "winner_loser", "w/l", "result",
                       "outcome", "status", "category", "winner", "loser"]:
        if candidate in lower_headers:
            col_map["label"] = lower_headers[candidate]
            break
    if "label" not in col_map and len(headers) > 1:
        col_map["label"] = headers[-1]  # Usually last column

    # PDF file column
    for candidate in ["pdf_file", "pdf file", "file_name", "file name", "filename", "pdf"]:
        if candidate in lower_headers:
            col_map["pdf_file"] = lower_headers[candidate]
            break

    # Optional columns
    for field, candidates in {
        "episode": ["episode", "episode_title", "episode title", "ep"],
        "network": ["network", "channel", "platform", "streamer"],
        "genre": ["genre", "type"],
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
