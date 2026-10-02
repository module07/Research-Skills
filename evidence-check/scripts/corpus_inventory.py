#!/usr/bin/env python3
"""Maintain a project's evidence registry and print its coverage manifest.

The registry is what makes a verdict readable. "No supporting evidence" only
means something next to a statement of what was searched, so every run prints
the manifest and the exclusion list alongside the findings.

    python3 corpus_inventory.py init  <project-dir> --name <project> \\
        --unit participants
    python3 corpus_inventory.py scan  <project-dir> --deliverable report.docx
    python3 corpus_inventory.py add   <project-dir> --type bear \\
        --locator ABC-123 --label "Field notes, day 2" --link "bear://..."
    python3 corpus_inventory.py exclude <project-dir> \\
        --pattern "drafts/**" --reason "working drafts, not evidence"
    python3 corpus_inventory.py manifest <project-dir> --json

The registry lives at <project>/.evidence-check/registry.json and records where
sources are, not what they contain. Every scan re-walks the tree, so an
additive corpus is picked up without anything being re-registered by hand.

It also records the unit of analysis: the thing being counted when a verdict
says "3 of 11". Participants for an interview corpus, documents for a policy
review, tickets for a support audit, sites for a field study. It is stored
rather than inferred per run, because a denominator that changes between runs
makes a changed verdict unattributable.

File sources are found by this script. Connector sources (Bear notes, Miro
boards, Drive files, Figma frames) are fetched by the agent through MCP and
recorded here with `add`, because a script in a sandbox cannot reach them.
"""

import argparse
import fnmatch
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
REG_DIR = ".evidence-check"
REG_FILE = "registry.json"

# What a denominator counts. Not a closed list; --unit takes any noun. These
# are the ones common enough to suggest when nothing was given.
UNIT_EXAMPLES = ("participants", "sources", "documents", "sessions", "tickets", "sites")
DEFAULT_UNIT = "sources"

DEFAULT_EXCLUSIONS = [
    (f"{REG_DIR}/**", "the registry itself"),
    ("**/.git/**", "version control internals"),
    ("**/.DS_Store", "filesystem noise"),
    ("**/~$*", "office lock files"),
    ("**/node_modules/**", "dependencies"),
]

KIND_BY_EXT = {
    ".vtt": "transcript",
    ".srt": "transcript",
    ".md": "note",
    ".txt": "note",
    ".rtf": "doc",
    ".docx": "doc",
    ".doc": "doc",
    ".odt": "doc",
    ".pdf": "doc",
    ".pptx": "deck",
    ".key": "deck",
    ".xlsx": "sheet",
    ".xls": "sheet",
    ".csv": "sheet",
    ".tsv": "sheet",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".heic": "image",
    ".webp": "image",
    ".json": "data",
}

TRANSCRIPT_HINTS = ("transcript", "interview", "session", "otter", "reduct", "rev-")
BOARD_HINTS = ("miro", "mural", "figjam", "figma", "board", "whiteboard", "sticky")

CONNECTOR_TYPES = ("bear", "miro", "mural", "drive", "figma", "notion", "url", "other")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reg_path(project):
    return Path(project) / REG_DIR / REG_FILE


def load(project, required=True):
    p = reg_path(project)
    if not p.exists():
        if required:
            sys.exit(
                f"error: no registry at {p}\n"
                f"       run: corpus_inventory.py init {project}"
            )
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save(project, reg):
    p = reg_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    reg["updated"] = now_iso()
    p.write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")


def source_id(type_, locator):
    return hashlib.sha1(f"{type_}:{locator}".encode("utf-8")).hexdigest()[:12]


def classify(rel_path):
    name = rel_path.name.lower()
    parts = [p.lower() for p in rel_path.parts]
    ext = rel_path.suffix.lower()
    haystack = " ".join(parts)

    if any(h in haystack for h in BOARD_HINTS):
        if ext in (".png", ".jpg", ".jpeg", ".pdf", ".webp"):
            return "board_export"
    if ext in (".vtt", ".srt"):
        return "transcript"
    if any(h in name for h in TRANSCRIPT_HINTS) or "transcript" in haystack:
        if ext in (".md", ".txt", ".docx", ".json"):
            return "transcript"
    return KIND_BY_EXT.get(ext, "other")


def excluded(rel, exclusions):
    posix = rel.as_posix()
    for ex in exclusions:
        pat = ex["pattern"]
        if fnmatch.fnmatch(posix, pat) or fnmatch.fnmatch(posix, pat.rstrip("/*") + "/*"):
            return ex
        if fnmatch.fnmatch(rel.name, pat):
            return ex
    return None


def cmd_init(args):
    project = Path(args.project).expanduser().resolve()
    if not project.is_dir():
        sys.exit(f"error: not a directory: {project}")
    if reg_path(project).exists() and not args.force:
        sys.exit(f"error: registry already exists at {reg_path(project)} (use --force)")
    reg = {
        "schema": SCHEMA,
        "project": args.name or project.name,
        "root": str(project),
        "unit_of_analysis": args.unit or DEFAULT_UNIT,
        "created": now_iso(),
        "updated": now_iso(),
        "sources": [],
        "exclusions": [
            {"pattern": p, "reason": r, "added": now_iso()} for p, r in DEFAULT_EXCLUSIONS
        ],
        "deliverables": [],
        "runs": [],
    }
    save(project, reg)
    print(f"registry created: {reg_path(project)}")
    print(f"  project: {reg['project']}")
    print(f"  unit of analysis: {reg['unit_of_analysis']}")
    if not args.unit:
        print(
            f"    defaulted; set it with --unit "
            f"({', '.join(UNIT_EXAMPLES)}, or whatever this corpus counts)"
        )
    print(f"  default exclusions: {len(reg['exclusions'])}")


def cmd_scan(args):
    project = Path(args.project).expanduser().resolve()
    reg = load(project)

    if args.deliverable:
        d = Path(args.deliverable)
        rel = (
            d.resolve().relative_to(project).as_posix()
            if d.is_absolute() and str(d.resolve()).startswith(str(project))
            else d.as_posix()
        )
        if rel not in reg["deliverables"]:
            reg["deliverables"].append(rel)

    known = {s["id"]: s for s in reg["sources"]}
    seen = set()
    added, skipped = [], []

    for path in sorted(project.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(project)
        ex = excluded(rel, reg["exclusions"])
        if ex:
            skipped.append((rel.as_posix(), ex["reason"]))
            continue
        if rel.as_posix() in reg["deliverables"]:
            skipped.append((rel.as_posix(), "deliverable under audit"))
            continue

        sid = source_id("file", rel.as_posix())
        seen.add(sid)
        stat = path.stat()
        record = {
            "id": sid,
            "type": "file",
            "kind": classify(rel),
            "locator": rel.as_posix(),
            "link": path.as_uri(),
            "label": rel.name,
            "bytes": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "status": "present",
        }
        if sid in known:
            record["first_seen"] = known[sid].get("first_seen", now_iso())
            if known[sid].get("status") == "missing":
                added.append((record["locator"], "returned"))
        else:
            record["first_seen"] = now_iso()
            added.append((record["locator"], "new"))
        record["last_seen"] = now_iso()
        known[sid] = record

    missing = []
    for sid, s in known.items():
        if s["type"] == "file" and sid not in seen and s.get("status") == "present":
            s["status"] = "missing"
            missing.append(s["locator"])

    reg["sources"] = sorted(known.values(), key=lambda s: (s["type"], s["locator"]))
    reg["runs"].append(
        {
            "at": now_iso(),
            "deliverable": args.deliverable,
            "sources_present": sum(1 for s in reg["sources"] if s["status"] == "present"),
        }
    )
    reg["runs"] = reg["runs"][-20:]
    save(project, reg)

    print_manifest(reg, json_out=args.json, added=added, missing=missing, skipped=skipped)


def cmd_add(args):
    project = Path(args.project).expanduser().resolve()
    reg = load(project)
    sid = source_id(args.type, args.locator)
    for s in reg["sources"]:
        if s["id"] == sid:
            s.update(
                {
                    "label": args.label or s.get("label"),
                    "link": args.link or s.get("link"),
                    "kind": args.kind or s.get("kind"),
                    "status": "present",
                    "last_seen": now_iso(),
                }
            )
            save(project, reg)
            print(f"updated {args.type} source {sid}: {s.get('label')}")
            return
    reg["sources"].append(
        {
            "id": sid,
            "type": args.type,
            "kind": args.kind or "other",
            "locator": args.locator,
            "link": args.link,
            "label": args.label or args.locator,
            "bytes": None,
            "mtime": None,
            "first_seen": now_iso(),
            "last_seen": now_iso(),
            "status": "present",
        }
    )
    save(project, reg)
    print(f"added {args.type} source {sid}: {args.label or args.locator}")


def cmd_exclude(args):
    project = Path(args.project).expanduser().resolve()
    reg = load(project)
    for ex in reg["exclusions"]:
        if ex["pattern"] == args.pattern:
            sys.exit(f"error: already excluded: {args.pattern} ({ex['reason']})")
    reg["exclusions"].append(
        {"pattern": args.pattern, "reason": args.reason, "added": now_iso()}
    )
    for s in reg["sources"]:
        if s["type"] == "file" and excluded(Path(s["locator"]), [reg["exclusions"][-1]]):
            s["status"] = "excluded"
    save(project, reg)
    print(f"excluded: {args.pattern}  ({args.reason})")


def cmd_set_unit(args):
    project = Path(args.project).expanduser().resolve()
    reg = load(project)
    was = reg.get("unit_of_analysis", DEFAULT_UNIT)
    reg["unit_of_analysis"] = args.unit
    save(project, reg)
    print(f"unit of analysis: {was} -> {args.unit}")
    if was != args.unit:
        print("  verdict denominators from earlier runs counted a different thing")


def cmd_manifest(args):
    project = Path(args.project).expanduser().resolve()
    reg = load(project)
    print_manifest(reg, json_out=args.json)


def print_manifest(reg, json_out=False, added=None, missing=None, skipped=None):
    present = [s for s in reg["sources"] if s["status"] == "present"]
    if json_out:
        print(
            json.dumps(
                {
                    "project": reg["project"],
                    "root": reg["root"],
                    "unit_of_analysis": reg.get("unit_of_analysis", DEFAULT_UNIT),
                    "updated": reg["updated"],
                    "present": present,
                    "missing": [s for s in reg["sources"] if s["status"] == "missing"],
                    "exclusions": reg["exclusions"],
                    "deliverables": reg["deliverables"],
                    "new_this_run": added or [],
                },
                indent=2,
            )
        )
        return

    by_kind = {}
    for s in present:
        by_kind.setdefault(s["kind"], []).append(s)

    print(f"CORPUS MANIFEST  {reg['project']}")
    print(f"  root:    {reg['root']}")
    print(f"  unit:    {reg.get('unit_of_analysis', DEFAULT_UNIT)} (the denominator in every verdict)")
    print(f"  sources: {len(present)} present")
    for kind, items in sorted(by_kind.items(), key=lambda kv: -len(kv[1])):
        print(f"    {kind:<14} {len(items)}")

    if added:
        print(f"\n  new since last run: {len(added)}")
        for locator, why in added[:20]:
            print(f"    {why:<9} {locator}")
        if len(added) > 20:
            print(f"    ... {len(added) - 20} more")

    if missing:
        print(f"\n  missing since last run: {len(missing)}")
        for locator in missing[:20]:
            print(f"    gone      {locator}")

    connectors = [s for s in present if s["type"] != "file"]
    if connectors:
        print(f"\n  connector sources: {len(connectors)}")
        for s in connectors:
            print(f"    {s['type']:<8} {s['label']}")

    print(f"\n  EXCLUDED FROM THE SWEEP ({len(reg['exclusions'])} rules)")
    for ex in reg["exclusions"]:
        print(f"    {ex['pattern']:<28} {ex['reason']}")
    if reg["deliverables"]:
        print("    deliverables under audit, never cited as evidence:")
        for d in reg["deliverables"]:
            print(f"      {d}")

    if skipped:
        print(f"\n  files skipped this scan: {len(skipped)}")

    print(
        "\n  Read every verdict against this list. A claim graded unsupported is "
        "\n  unsupported by what is above, which is not the same as unsupported."
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="create a registry for a project")
    p.add_argument("project")
    p.add_argument("--name", help="project name (default: folder name)")
    p.add_argument(
        "--unit",
        help=(
            "what this corpus counts, used as the denominator in every verdict: "
            + ", ".join(UNIT_EXAMPLES)
            + f", or any other noun (default: {DEFAULT_UNIT})"
        ),
    )
    p.add_argument("--force", action="store_true", help="overwrite an existing registry")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("set-unit", help="change the unit of analysis on an existing registry")
    p.add_argument("project")
    p.add_argument("--unit", required=True)
    p.set_defaults(func=cmd_set_unit)

    p = sub.add_parser("scan", help="re-walk the project and refresh the registry")
    p.add_argument("project")
    p.add_argument("--deliverable", help="the document under audit; excluded from evidence")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("add", help="register a connector source the agent fetched")
    p.add_argument("project")
    p.add_argument("--type", required=True, choices=CONNECTOR_TYPES)
    p.add_argument("--locator", required=True, help="note id, board id, file id, or URL")
    p.add_argument("--link", help="a link that resolves back to the source")
    p.add_argument("--label", help="human-readable name")
    p.add_argument("--kind", help="transcript, note, board, doc, deck, sheet, image, data")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("exclude", help="rule a path pattern out of the sweep")
    p.add_argument("project")
    p.add_argument("--pattern", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_exclude)

    p = sub.add_parser("manifest", help="print the manifest without scanning")
    p.add_argument("project")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_manifest)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
