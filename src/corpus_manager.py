"""
corpus_manager.py — GEM Corpus Expansion Pipeline

Manages the corpus of TV shows: adding new shows, gathering evidence,
storing scripts + fallback metadata in a structured, inspectable format.

Evidence hierarchy (best first):
  1. pilot_script      — full pilot script text (best for scoring)
  2. episode_script    — any episode script
  3. show_summary      — multi-paragraph description of the full show
  4. season_summary    — description of season 1
  5. episode_summary   — description of pilot episode
  6. logline           — 1-2 sentence premise
  7. synopsis          — brief description
  8. metadata          — basic facts (year, network, cast, genre)
  9. outcome_data      — renewal, cancellation, ratings, awards info

Commands:
  python3 src/corpus_manager.py list                      # Show all corpus entries
  python3 src/corpus_manager.py show <show_id>            # Show evidence for one show
  python3 src/corpus_manager.py add <show_id> <show_name> # Register a new show
  python3 src/corpus_manager.py add-script <show_id> <path_to_txt>  # Add script file
  python3 src/corpus_manager.py add-evidence <show_id> <type> <path_or_text>
  python3 src/corpus_manager.py gather <show_id>          # Web-fetch fallback evidence
  python3 src/corpus_manager.py gather-batch <file.txt>   # Gather evidence for list of shows
  python3 src/corpus_manager.py status                    # Coverage summary
  python3 src/corpus_manager.py ready-to-score            # List shows with enough evidence to score
"""

import argparse
import json
import os
import sys
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

BASE_DIR        = Path(".")
REGISTRY_PATH   = BASE_DIR / "data/corpus/registry.jsonl"
EVIDENCE_DIR    = BASE_DIR / "data/corpus/evidence"
EXTRACTED_DIR   = BASE_DIR / "data/extracted_text"  # legacy script location
LABELS_V2       = BASE_DIR / "data/labels/labels_v2.jsonl"

EVIDENCE_TYPES  = [
    "pilot_script",
    "episode_script",
    "show_summary",
    "season_summary",
    "episode_summary",
    "logline",
    "synopsis",
    "metadata",
    "outcome_data",
]

# Minimum evidence needed to run LLM scoring
SCOREABLE_TYPES = {"pilot_script", "episode_script", "show_summary", "season_summary"}


# ─── Registry I/O ──────────────────────────────────────────────

def load_registry() -> list:
    if not REGISTRY_PATH.exists():
        return []
    with open(REGISTRY_PATH) as f:
        return [json.loads(l) for l in f if l.strip()]


def save_registry(entries: list):
    with open(REGISTRY_PATH, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def find_show(registry: list, show_id: str) -> tuple:
    for i, e in enumerate(registry):
        if e["show_id"] == show_id:
            return i, e
    return -1, None


def get_show_evidence_dir(show_id: str) -> Path:
    return EVIDENCE_DIR / show_id


# ─── Evidence Manifest ─────────────────────────────────────────

def load_manifest(show_id: str) -> dict:
    path = get_show_evidence_dir(show_id) / "manifest.json"
    if path.exists():
        return json.loads(path.read_text())
    return {
        "show_id": show_id,
        "evidence": {},
        "last_updated": None,
    }


def save_manifest(show_id: str, manifest: dict):
    d = get_show_evidence_dir(show_id)
    d.mkdir(parents=True, exist_ok=True)
    manifest["last_updated"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    (d / "manifest.json").write_text(json.dumps(manifest, indent=2))


def record_evidence(show_id: str, evidence_type: str, filename: str,
                    source: str = "manual", notes: str = ""):
    """Update the manifest to record a piece of evidence."""
    manifest = load_manifest(show_id)
    manifest["evidence"][evidence_type] = {
        "file": filename,
        "source": source,
        "notes": notes,
        "added_at": datetime.utcnow().strftime("%Y-%m-%d"),
    }
    save_manifest(show_id, manifest)


def list_evidence_types(show_id: str) -> list:
    """Return list of evidence types available for a show."""
    manifest = load_manifest(show_id)
    types = list(manifest.get("evidence", {}).keys())
    # Also check legacy extracted_text
    if (EXTRACTED_DIR / f"{show_id}.txt").exists():
        if "pilot_script" not in types:
            types.insert(0, "pilot_script (legacy)")
    return types


def get_best_evidence_text(show_id: str) -> tuple:
    """
    Return (evidence_type, text) for the best available evidence.
    Priority: pilot_script > episode_script > show_summary > ...
    """
    # Check legacy location first
    legacy = EXTRACTED_DIR / f"{show_id}.txt"
    if legacy.exists():
        return "pilot_script", legacy.read_text(encoding="utf-8", errors="ignore")

    manifest = load_manifest(show_id)
    evidence = manifest.get("evidence", {})

    for etype in EVIDENCE_TYPES:
        if etype in evidence:
            fpath = get_show_evidence_dir(show_id) / evidence[etype]["file"]
            if fpath.exists():
                return etype, fpath.read_text(encoding="utf-8", errors="ignore")

    return None, None


def is_scoreable(show_id: str) -> bool:
    """Check if show has enough evidence to score."""
    legacy = EXTRACTED_DIR / f"{show_id}.txt"
    if legacy.exists():
        return True
    manifest = load_manifest(show_id)
    return bool(set(manifest.get("evidence", {}).keys()) & SCOREABLE_TYPES)


# ─── Commands ──────────────────────────────────────────────────

def cmd_status(registry: list):
    has_script = [r for r in registry if r.get("pilot_script_available")]
    needs_script = [r for r in registry if not r.get("pilot_script_available")]

    # Check corpus/evidence for those without legacy scripts
    has_evidence = 0
    for r in needs_script:
        if is_scoreable(r["show_id"]):
            has_evidence += 1

    scoreable = len(has_script) + has_evidence

    print(f"\n{'='*60}")
    print(f"CORPUS STATUS")
    print(f"{'='*60}")
    print(f"Total shows in corpus:   {len(registry)}")
    print(f"  Has pilot script:      {len(has_script)}")
    print(f"  Has other evidence:    {has_evidence}")
    print(f"  Needs evidence:        {len(needs_script) - has_evidence}")
    print(f"  Scoreable total:       {scoreable}")
    print(f"{'='*60}\n")
    print(f"To add evidence for a show:")
    print(f"  python3 src/corpus_manager.py add-script <show_id> <path.txt>")
    print(f"  python3 src/corpus_manager.py gather <show_id>  # web-fetch fallback\n")


def cmd_list(registry: list, filter_status: str = None):
    print(f"\n{'='*80}")
    print(f"CORPUS REGISTRY  ({len(registry)} shows)")
    print(f"{'='*80}")
    print(f"{'Show Name':<50} {'Status':<20} {'Evidence'}")
    print("-"*80)
    for r in registry:
        if filter_status and r.get("retrieval_status") != filter_status:
            continue
        name = (r.get("show_name") or r["show_id"])[:48]
        ev = list_evidence_types(r["show_id"])
        ev_str = ", ".join(ev[:3]) if ev else "none"
        print(f"{name:<50} {r.get('retrieval_status','?'):<20} {ev_str}")
    print("="*80 + "\n")


def cmd_show(registry: list, show_id: str):
    _, entry = find_show(registry, show_id)
    if not entry:
        matches = [r for r in registry if show_id.lower() in r["show_id"].lower()
                   or show_id.lower() in (r.get("show_name") or "").lower()]
        if matches:
            print(f"No exact match. Closest:")
            for m in matches[:10]:
                print(f"  {m['show_id']}")
        else:
            print(f"Not found: {show_id}")
        return

    manifest = load_manifest(show_id)
    ev = manifest.get("evidence", {})

    print(f"\n{'='*60}")
    print(f"Show:     {entry.get('show_name') or show_id}")
    print(f"ID:       {show_id}")
    print(f"Status:   {entry.get('retrieval_status')}")
    print(f"Scoreable: {'Yes' if is_scoreable(show_id) else 'No'}")
    print(f"\nEvidence ({len(ev)} items):")
    for etype, info in ev.items():
        print(f"  [{etype}]  {info['file']}  (source: {info['source']})")
    legacy = EXTRACTED_DIR / f"{show_id}.txt"
    if legacy.exists():
        size = legacy.stat().st_size
        print(f"  [pilot_script]  {legacy}  (legacy, {size:,} bytes)")
    print("="*60 + "\n")


def cmd_add(registry: list, show_id: str, show_name: str, label: str = None):
    _, existing = find_show(registry, show_id)
    if existing:
        print(f"Show already in corpus: {show_id}")
        return
    entry = {
        "show_id": show_id,
        "show_name": show_name,
        "in_benchmark": False,
        "evidence_types": [],
        "pilot_script_available": False,
        "retrieval_status": "needs_script",
        "added_at": datetime.utcnow().strftime("%Y-%m-%d"),
        "source": "manual",
    }
    registry.append(entry)
    save_registry(registry)

    # Also add to labels if label provided
    if label:
        labels = []
        if LABELS_V2.exists():
            with open(LABELS_V2) as f:
                labels = [json.loads(l) for l in f if l.strip()]
        labels.append({
            "show_id": show_id,
            "show_name": show_name,
            "label_v1": None,
            "label_v2": label,
            "label_v2_confidence": "high",
            "needs_review": False,
            "suggested_reclassification": None,
            "v2_weighted_score": None,
            "labeled_by": "human",
            "labeled_at": datetime.utcnow().strftime("%Y-%m-%d"),
        })
        with open(LABELS_V2, "w") as f:
            for l in labels:
                f.write(json.dumps(l) + "\n")
        print(f"Added to labels as [{label}]")

    print(f"Added to corpus: {show_id}")


def cmd_add_script(registry: list, show_id: str, script_path: str):
    """Copy a script text file into the corpus evidence directory."""
    src = Path(script_path)
    if not src.exists():
        print(f"File not found: {src}")
        sys.exit(1)

    _, entry = find_show(registry, show_id)
    if not entry:
        print(f"Show not in corpus: {show_id}. Add it first with 'add'.")
        sys.exit(1)

    dest_dir = get_show_evidence_dir(show_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "pilot_script.txt"
    shutil.copy2(src, dest)

    # Update registry
    i, _ = find_show(registry, show_id)
    registry[i]["pilot_script_available"] = True
    registry[i]["retrieval_status"] = "has_script"
    if "pilot_script" not in registry[i].get("evidence_types", []):
        registry[i].setdefault("evidence_types", []).append("pilot_script")
    save_registry(registry)

    record_evidence(show_id, "pilot_script", "pilot_script.txt",
                    source="manual", notes=f"copied from {src.name}")
    print(f"Script added for {show_id} → {dest}")


def cmd_add_evidence(registry: list, show_id: str, evidence_type: str, content: str):
    """Add text evidence (path to file, or inline text)."""
    if evidence_type not in EVIDENCE_TYPES:
        print(f"Unknown evidence type '{evidence_type}'. Valid: {EVIDENCE_TYPES}")
        sys.exit(1)

    _, entry = find_show(registry, show_id)
    if not entry:
        print(f"Show not in corpus: {show_id}")
        sys.exit(1)

    dest_dir = get_show_evidence_dir(show_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # If content is a file path, copy it; otherwise treat as inline text
    src = Path(content)
    filename = f"{evidence_type}.txt"
    dest = dest_dir / filename
    if src.exists():
        shutil.copy2(src, dest)
        source = f"file:{src.name}"
    else:
        dest.write_text(content)
        source = "inline"

    record_evidence(show_id, evidence_type, filename, source=source)

    i, _ = find_show(registry, show_id)
    if evidence_type not in registry[i].get("evidence_types", []):
        registry[i].setdefault("evidence_types", []).append(evidence_type)
    registry[i]["retrieval_status"] = "has_evidence"
    save_registry(registry)
    print(f"Evidence added: {show_id} / {evidence_type} → {dest}")


def cmd_gather(show_id: str):
    """Web-fetch fallback evidence for a show (logline, summary, metadata)."""
    try:
        import openai
        client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    except Exception as e:
        print(f"OpenAI client init failed: {e}")
        sys.exit(1)

    registry = load_registry()
    _, entry = find_show(registry, show_id)
    if not entry:
        print(f"Show not in corpus: {show_id}")
        sys.exit(1)

    show_name = entry.get("show_name") or show_id
    print(f"Gathering evidence for: {show_name}")

    prompt = f"""You are a TV research assistant. Provide detailed information about the TV show "{show_name}".

Return a JSON object with these fields:
{{
  "logline": "1-2 sentence premise of the show",
  "show_summary": "3-5 paragraph description of the show: premise, main characters, tone, themes, what makes it distinctive",
  "pilot_summary": "2-3 paragraph description of what happens in the pilot episode",
  "metadata": {{
    "network": "network name",
    "year": "premiere year",
    "genre": "genre(s)",
    "creator": "creator/showrunner name",
    "main_cast": ["actor: role", ...],
    "seasons": "number of seasons",
    "status": "ended/ongoing"
  }},
  "outcome_data": "What happened to the show: ratings, renewal, cancellation, awards, cultural impact, critical reception"
}}

Be specific and accurate. If you don't know something, use null."""

    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=2000,
        )
        raw = response.choices[0].message.content.strip()

        # Clean JSON
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        data = json.loads(raw)

        dest_dir = get_show_evidence_dir(show_id)
        dest_dir.mkdir(parents=True, exist_ok=True)

        added = []
        for field in ["logline", "show_summary", "pilot_summary", "outcome_data"]:
            if data.get(field):
                fname = f"{field}.txt" if field != "pilot_summary" else "episode_summary.txt"
                etype = field if field != "pilot_summary" else "episode_summary"
                (dest_dir / fname).write_text(str(data[field]))
                record_evidence(show_id, etype, fname, source="llm_gathered")
                added.append(etype)

        if data.get("metadata"):
            (dest_dir / "metadata.json").write_text(json.dumps(data["metadata"], indent=2))
            record_evidence(show_id, "metadata", "metadata.json", source="llm_gathered")
            added.append("metadata")

        # Update registry
        i, _ = find_show(registry, show_id)
        for a in added:
            if a not in registry[i].get("evidence_types", []):
                registry[i].setdefault("evidence_types", []).append(a)
        registry[i]["retrieval_status"] = "has_evidence"
        save_registry(registry)

        print(f"Evidence gathered for {show_name}: {added}")

    except Exception as e:
        print(f"Failed to gather evidence for {show_id}: {e}")


def cmd_gather_batch(show_list_file: str):
    """Gather evidence for all shows in a text file (one show_id per line)."""
    shows = Path(show_list_file).read_text().strip().split("\n")
    shows = [s.strip() for s in shows if s.strip() and not s.startswith("#")]
    print(f"Gathering evidence for {len(shows)} shows...")
    for i, show_id in enumerate(shows, 1):
        print(f"\n[{i}/{len(shows)}] {show_id}")
        cmd_gather(show_id)


def cmd_ready_to_score(registry: list):
    """List shows that have enough evidence to run LLM scoring."""
    ready = [r for r in registry if is_scoreable(r["show_id"])]
    not_ready = [r for r in registry if not is_scoreable(r["show_id"])]
    print(f"\n{'='*60}")
    print(f"READY TO SCORE: {len(ready)} shows")
    print(f"NEEDS EVIDENCE: {len(not_ready)} shows")
    print(f"{'='*60}")
    if not_ready:
        print("\nShows needing evidence (first 20):")
        for r in not_ready[:20]:
            print(f"  {r['show_id']}")
        if len(not_ready) > 20:
            print(f"  ... and {len(not_ready)-20} more")
    print(f"\nTo gather fallback evidence:")
    print(f"  python3 src/corpus_manager.py gather <show_id>")


# ─── Main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="GEM Corpus Manager")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status")
    sub.add_parser("ready-to-score")

    p_list = sub.add_parser("list")
    p_list.add_argument("--status", help="Filter by retrieval_status")

    p_show = sub.add_parser("show")
    p_show.add_argument("show_id")

    p_add = sub.add_parser("add")
    p_add.add_argument("show_id")
    p_add.add_argument("show_name")
    p_add.add_argument("--label", choices=["winner", "middle", "loser"])

    p_script = sub.add_parser("add-script")
    p_script.add_argument("show_id")
    p_script.add_argument("script_path")

    p_ev = sub.add_parser("add-evidence")
    p_ev.add_argument("show_id")
    p_ev.add_argument("evidence_type", choices=EVIDENCE_TYPES)
    p_ev.add_argument("content", help="Path to file or inline text")

    p_gather = sub.add_parser("gather")
    p_gather.add_argument("show_id")

    p_batch = sub.add_parser("gather-batch")
    p_batch.add_argument("show_list_file", help="Text file with one show_id per line")

    args = parser.parse_args()
    registry = load_registry()

    if args.command == "status":
        cmd_status(registry)
    elif args.command == "list":
        cmd_list(registry, getattr(args, "status", None))
    elif args.command == "show":
        cmd_show(registry, args.show_id)
    elif args.command == "add":
        cmd_add(registry, args.show_id, args.show_name, getattr(args, "label", None))
    elif args.command == "add-script":
        cmd_add_script(registry, args.show_id, args.script_path)
    elif args.command == "add-evidence":
        cmd_add_evidence(registry, args.show_id, args.evidence_type, args.content)
    elif args.command == "gather":
        cmd_gather(args.show_id)
    elif args.command == "gather-batch":
        cmd_gather_batch(args.show_list_file)
    elif args.command == "ready-to-score":
        cmd_ready_to_score(registry)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
