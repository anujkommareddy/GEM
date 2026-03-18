"""
label_manager.py — GEM Label System (v2: winner / middle / loser)

Label Definitions:
  winner  = clear breakout / transcendent cultural success
  middle  = ambiguous — cult, respectable, niche, mixed, or unclear outcome
  loser   = clear failure to break out

Commands:
  python3 src/label_manager.py review          # Interactive review of needs_review items
  python3 src/label_manager.py stats           # Label distribution stats
  python3 src/label_manager.py show <show_id>  # Show label for one entry
  python3 src/label_manager.py set <show_id> <label>  # Set label manually
  python3 src/label_manager.py export          # Export labels as JSONL for scoring pipeline
  python3 src/label_manager.py review-list     # Print all items flagged for review (no prompt)
"""

import json
import argparse
import sys
from pathlib import Path
from datetime import datetime
from collections import Counter

BASE_DIR    = Path(".")
LABELS_V1   = BASE_DIR / "data/labels/labels_v1.jsonl"
LABELS_V2   = BASE_DIR / "data/labels/labels_v2.jsonl"
VALID_LABELS = {"winner", "middle", "loser"}


# ─── I/O ───────────────────────────────────────────────────────

def load_labels(path: Path) -> list:
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def save_labels(path: Path, labels: list):
    with open(path, "w") as f:
        for entry in labels:
            f.write(json.dumps(entry) + "\n")


def find_entry(labels: list, show_id: str) -> tuple:
    """Return (index, entry) or (-1, None)."""
    for i, e in enumerate(labels):
        if e["show_id"] == show_id:
            return i, e
    return -1, None


# ─── Commands ──────────────────────────────────────────────────

def cmd_stats(labels: list):
    """Print label distribution stats."""
    v2_dist = Counter(e["label_v2"] for e in labels)
    v1_dist = Counter(e["label_v1"] for e in labels)
    needs_review = [e for e in labels if e.get("needs_review")]

    print("\n" + "="*60)
    print("GEM LABEL STATS — v2 (winner / middle / loser)")
    print("="*60)
    total = len(labels)
    for label in ["winner", "middle", "loser", None]:
        count = v2_dist.get(label, 0)
        pct = 100 * count / total if total else 0
        name = label or "unlabeled"
        print(f"  {name:<12} {count:>5}  ({pct:.1f}%)")
    print(f"  {'TOTAL':<12} {total:>5}")
    print()
    print(f"  Flagged for review: {len(needs_review)}")
    print()
    print("v1 → v2 migration:")
    for lbl in ["winner", "loser", None]:
        v1_count = v1_dist.get(lbl, 0)
        name = lbl or "unlabeled"
        print(f"  v1 {name:<12} → {v1_count} entries")
    print("="*60 + "\n")


def cmd_show(labels: list, show_id: str):
    """Show label info for one show."""
    _, entry = find_entry(labels, show_id)
    if not entry:
        # Fuzzy match
        matches = [e for e in labels if show_id.lower() in e["show_id"].lower()
                   or show_id.lower() in e.get("show_name","").lower()]
        if matches:
            print(f"\nNo exact match for '{show_id}'. Closest matches:")
            for m in matches[:10]:
                print(f"  {m['show_id']:<60}  [{m['label_v2']}]")
        else:
            print(f"Show not found: {show_id}")
        return
    print(f"\n{'='*60}")
    print(f"Show:       {entry['show_name']}")
    print(f"ID:         {entry['show_id']}")
    print(f"Label v1:   {entry['label_v1']}")
    print(f"Label v2:   {entry['label_v2']}  (confidence: {entry.get('label_v2_confidence','?')})")
    if entry.get("needs_review"):
        print(f"Review:     YES — {entry.get('suggested_reclassification','')}")
    if entry.get("v2_weighted_score"):
        print(f"v2 Score:   {entry['v2_weighted_score']:.3f}")
    print(f"Labeled by: {entry.get('labeled_by','?')}  at {entry.get('labeled_at','?')}")
    print("="*60 + "\n")


def cmd_set(labels: list, show_id: str, new_label: str, note: str = ""):
    """Set a label manually."""
    if new_label not in VALID_LABELS:
        print(f"Invalid label '{new_label}'. Must be one of: {sorted(VALID_LABELS)}")
        sys.exit(1)

    i, entry = find_entry(labels, show_id)
    if i == -1:
        print(f"Show not found: {show_id}")
        sys.exit(1)

    old_label = entry["label_v2"]
    labels[i]["label_v2"] = new_label
    labels[i]["label_v2_confidence"] = "high"
    labels[i]["needs_review"] = False
    labels[i]["suggested_reclassification"] = None
    labels[i]["labeled_by"] = "human"
    labels[i]["labeled_at"] = datetime.utcnow().strftime("%Y-%m-%d")
    if note:
        labels[i]["notes"] = note

    save_labels(LABELS_V2, labels)
    print(f"  {show_id}: {old_label} → {new_label}")


def cmd_review_list(labels: list):
    """Print all items flagged for review without prompting."""
    pending = [e for e in labels if e.get("needs_review")]
    if not pending:
        print("No items flagged for review.")
        return
    print(f"\n{'='*90}")
    print(f"ITEMS FLAGGED FOR REVIEW  ({len(pending)} total)")
    print(f"{'='*90}")
    print(f"{'Show Name':<50} {'v1':>8} {'v2':>8} {'Score':>7}  Suggestion")
    print("-"*90)
    for e in pending:
        name = (e.get('show_name') or e['show_id'])[:48]
        score = f"{e['v2_weighted_score']:.2f}" if e.get('v2_weighted_score') else "  n/a"
        suggestion = (e.get('suggested_reclassification') or '')[:35]
        print(f"{name:<50} {e['label_v1'] or 'None':>8} {e['label_v2']:>8} {score:>7}  {suggestion}")
    print("="*90)
    print(f"\nTo reclassify: python3 src/label_manager.py set <show_id> <label>")
    print(f"Valid labels: winner, middle, loser\n")


def cmd_review(labels: list):
    """Interactive review of needs_review items."""
    pending = [e for e in labels if e.get("needs_review")]
    if not pending:
        print("No items flagged for review. All labels are confirmed.")
        return

    print(f"\nInteractive review: {len(pending)} items flagged.")
    print("Options: w=winner  m=middle  l=loser  s=skip  q=quit\n")

    changed = 0
    for idx, entry in enumerate(pending):
        name = entry.get("show_name") or entry["show_id"]
        score = f"{entry['v2_weighted_score']:.2f}" if entry.get("v2_weighted_score") else "n/a"
        suggestion = entry.get("suggested_reclassification", "")

        print(f"[{idx+1}/{len(pending)}] {name}")
        print(f"  Current:    {entry['label_v2']}  (v1: {entry['label_v1']})")
        print(f"  Score:      {score}")
        print(f"  Suggestion: {suggestion}")
        choice = input("  → ").strip().lower()

        label_map = {"w": "winner", "m": "middle", "l": "loser"}
        if choice == "q":
            break
        elif choice == "s":
            continue
        elif choice in label_map:
            i, _ = find_entry(labels, entry["show_id"])
            labels[i]["label_v2"] = label_map[choice]
            labels[i]["label_v2_confidence"] = "high"
            labels[i]["needs_review"] = False
            labels[i]["labeled_by"] = "human"
            labels[i]["labeled_at"] = datetime.utcnow().strftime("%Y-%m-%d")
            changed += 1
            print(f"  ✓ → {label_map[choice]}\n")
        else:
            print("  Skipped (unrecognized input)\n")

    save_labels(LABELS_V2, labels)
    print(f"\nReview done. {changed} labels updated.")


def cmd_export(labels: list):
    """Export v2 labels in the format scoring pipeline expects."""
    out = BASE_DIR / "data/labels/labels_v2_export.jsonl"
    with open(out, "w") as f:
        for e in labels:
            f.write(json.dumps({
                "show_id":  e["show_id"],
                "show_name": e.get("show_name"),
                "label":    e["label_v2"],
                "label_v1": e["label_v1"],
            }) + "\n")
    print(f"Exported {len(labels)} labels → {out}")


def cmd_add(labels: list, show_id: str, show_name: str, label: str, notes: str = ""):
    """Add a new show to the label set."""
    if label not in VALID_LABELS:
        print(f"Invalid label. Must be: {sorted(VALID_LABELS)}")
        sys.exit(1)
    _, existing = find_entry(labels, show_id)
    if existing:
        print(f"Show already exists: {show_id}. Use 'set' to change label.")
        return
    entry = {
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
        "notes": notes,
    }
    labels.append(entry)
    save_labels(LABELS_V2, labels)
    print(f"Added: {show_id} [{label}]")


# ─── Main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="GEM Label Manager")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("stats")
    sub.add_parser("review")
    sub.add_parser("review-list")
    sub.add_parser("export")

    p_show = sub.add_parser("show")
    p_show.add_argument("show_id")

    p_set = sub.add_parser("set")
    p_set.add_argument("show_id")
    p_set.add_argument("label", choices=list(VALID_LABELS))
    p_set.add_argument("--note", default="")

    p_add = sub.add_parser("add")
    p_add.add_argument("show_id")
    p_add.add_argument("show_name")
    p_add.add_argument("label", choices=list(VALID_LABELS))
    p_add.add_argument("--notes", default="")

    args = parser.parse_args()

    if not LABELS_V2.exists():
        print(f"Label file not found: {LABELS_V2}")
        sys.exit(1)

    labels = load_labels(LABELS_V2)

    if args.command == "stats":
        cmd_stats(labels)
    elif args.command == "show":
        cmd_show(labels, args.show_id)
    elif args.command == "set":
        cmd_set(labels, args.show_id, args.label, args.note)
    elif args.command == "add":
        cmd_add(labels, args.show_id, args.show_name, args.label, args.notes)
    elif args.command == "review":
        cmd_review(labels)
    elif args.command == "review-list":
        cmd_review_list(labels)
    elif args.command == "export":
        cmd_export(labels)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
