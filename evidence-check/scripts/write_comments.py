#!/usr/bin/env python3
"""Write evidence-check verdicts back into a deliverable as comments.

    python3 write_comments.py report.docx verdicts.json --dry-run
    python3 write_comments.py report.docx verdicts.json -o report-checked.docx
    python3 write_comments.py report.docx verdicts.json --in-place

Never run this without the user's explicit approval for that specific file.
Approval never carries from one file to the next. The skill asks every run;
this script does not ask.

verdicts.json is a list of records:

    [
      {
        "claim_id": "C07",
        "anchor": {"type": "docx", "para_index": 12},
        "comment": "overstated. 3 of 11 support, 2 disconfirm, 6 silent.\\n..."
      }
    ]

Anchors come from document_ir.py and mean the same thing here.

Existing comments in the file are preserved. New comment ids continue from the
highest id already present, so a re-run or a colleague's markup is never
overwritten.

Surface support:

    .docx   Word comments, anchored to the paragraph. In-place allowed.
    .pdf    Text (sticky note) annotations, placed at the anchor's y position.
            In-place allowed.
    .pptx   Legacy PowerPoint comments, anchored to the slide. Copy only:
            --in-place is refused, because this writer has been validated by
            reopening and by LibreOffice conversion, not against PowerPoint
            itself.
"""

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WQ = "{%s}" % W
PML = "http://schemas.openxmlformats.org/presentationml/2006/main"
PQ = "{%s}" % PML
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
RQ = "{%s}" % REL_NS
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
CTQ = "{%s}" % CT_NS

COMMENTS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
AUTHORS_REL = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/commentAuthors"
)
DOCX_COMMENTS_CT = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
)
PPTX_COMMENTS_CT = (
    "application/vnd.openxmlformats-officedocument.presentationml.comments+xml"
)
PPTX_AUTHORS_CT = (
    "application/vnd.openxmlformats-officedocument.presentationml.commentAuthors+xml"
)

AUTHOR = "evidence-check"
INITIALS = "EC"

# PowerPoint legacy comment positions are in EMU. 0.25in from the top left of
# the slide keeps the marker clear of most title placeholders.
PPTX_POS = (228600, 228600)


def _lxml():
    """lxml rather than the standard library, deliberately.

    ElementTree re-derives namespace prefixes when it writes, which can rename
    the prefixes a real Word file declares. Word's mc:Ignorable attribute names
    those prefixes as a string, so a rename leaves it pointing at prefixes that
    no longer exist and Word reads the file as corrupt. lxml round-trips them,
    which matters here because this script writes into real deliverables.
    """
    try:
        from lxml import etree

        return etree
    except ImportError:
        sys.exit(
            "error: lxml is required to write comments into Office files.\n"
            "       pip3 install lxml"
        )


def _parser(etree):
    """Untrusted Office XML: no entity expansion, no network, no DTD loading."""
    return etree.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False
    )


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_verdicts(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "verdicts" in data:
        data = data["verdicts"]
    if not isinstance(data, list):
        sys.exit("error: verdicts file must be a JSON list, or an object with 'verdicts'")
    for i, v in enumerate(data):
        for key in ("claim_id", "anchor", "comment"):
            if key not in v:
                sys.exit(f"error: verdict {i} is missing '{key}'")
        if "type" not in v["anchor"]:
            sys.exit(f"error: verdict {i} has an anchor with no 'type'")
    return data


def unzip(src, dest):
    with zipfile.ZipFile(src) as z:
        for info in z.infolist():
            target = Path(dest) / info.filename
            if not str(target.resolve()).startswith(str(Path(dest).resolve())):
                sys.exit(f"error: refusing unsafe zip path {info.filename}")
        z.extractall(dest)


def rezip(srcdir, out):
    srcdir = Path(srcdir)
    files = sorted(p for p in srcdir.rglob("*") if p.is_file())
    ct = srcdir / "[Content_Types].xml"
    ordered = ([ct] if ct.exists() else []) + [p for p in files if p != ct]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in ordered:
            z.write(p, p.relative_to(srcdir).as_posix())


def ensure_override(ct_path, part_name, content_type):
    etree = _lxml()

    tree = etree.parse(str(ct_path), _parser(etree))
    root = tree.getroot()
    for ov in root.findall(f"{CTQ}Override"):
        if ov.get("PartName") == part_name:
            return
    ov = etree.SubElement(root, f"{CTQ}Override")
    ov.set("PartName", part_name)
    ov.set("ContentType", content_type)
    tree.write(str(ct_path), xml_declaration=True, encoding="UTF-8", standalone=True)


def ensure_rel(rels_path, rel_type, target):
    """Add a relationship if absent. Returns the relationship id."""
    etree = _lxml()

    rels_path = Path(rels_path)
    rels_path.parent.mkdir(parents=True, exist_ok=True)
    if rels_path.exists():
        tree = etree.parse(str(rels_path), _parser(etree))
        root = tree.getroot()
    else:
        root = etree.Element(f"{RQ}Relationships")
        tree = etree.ElementTree(root)

    for rel in root.findall(f"{RQ}Relationship"):
        if rel.get("Type") == rel_type and rel.get("Target") == target:
            return rel.get("Id")

    used = {rel.get("Id") for rel in root.findall(f"{RQ}Relationship")}
    n = 1
    while f"rId{n}" in used:
        n += 1
    rid = f"rId{n}"
    rel = etree.SubElement(root, f"{RQ}Relationship")
    rel.set("Id", rid)
    rel.set("Type", rel_type)
    rel.set("Target", target)
    tree.write(str(rels_path), xml_declaration=True, encoding="UTF-8", standalone=True)
    return rid


# --------------------------------------------------------------------------
# docx
# --------------------------------------------------------------------------


def comment_body_xml(cid, text):
    paras = []
    for i, line in enumerate(text.split("\n")):
        ref = (
            '<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr>'
            "<w:annotationRef/></w:r>"
            if i == 0
            else ""
        )
        paras.append(
            f"<w:p>{ref}<w:r><w:t xml:space=\"preserve\">{xml_escape(line)}</w:t></w:r></w:p>"
        )
    return (
        f'<w:comment xmlns:w="{W}" w:id="{cid}" w:author="{xml_escape(AUTHOR)}" '
        f'w:date="{now_iso()}" w:initials="{INITIALS}">'
        + "".join(paras)
        + "</w:comment>"
    )


def write_docx(src, dst, verdicts):
    etree = _lxml()

    tmp = tempfile.mkdtemp(prefix="evcheck-docx-")
    try:
        unzip(src, tmp)
        root_dir = Path(tmp)
        doc_path = root_dir / "word" / "document.xml"
        if not doc_path.exists():
            sys.exit("error: no word/document.xml; is this a real .docx?")

        comments_path = root_dir / "word" / "comments.xml"
        if comments_path.exists():
            ctree = etree.parse(str(comments_path), _parser(etree))
            croot = ctree.getroot()
            existing = [
                int(c.get(f"{WQ}id"))
                for c in croot.findall(f"{WQ}comment")
                if (c.get(f"{WQ}id") or "").isdigit()
            ]
            next_id = max(existing) + 1 if existing else 0
        else:
            croot = etree.fromstring(
                f'<w:comments xmlns:w="{W}"></w:comments>'.encode("utf-8")
            )
            ctree = etree.ElementTree(croot)
            next_id = 0

        dtree = etree.parse(str(doc_path), _parser(etree))
        paras = list(dtree.getroot().iter(f"{WQ}p"))

        written = []
        skipped = []
        for v in verdicts:
            a = v["anchor"]
            if a.get("type") != "docx":
                skipped.append((v["claim_id"], f"anchor type '{a.get('type')}' is not docx"))
                continue
            idx = a.get("para_index")
            if not isinstance(idx, int) or idx < 0 or idx >= len(paras):
                skipped.append(
                    (v["claim_id"], f"para_index {idx} outside 0..{len(paras) - 1}")
                )
                continue

            p = paras[idx]
            cid = next_id
            next_id += 1

            start = etree.Element(f"{WQ}commentRangeStart")
            start.set(f"{WQ}id", str(cid))
            ppr = p.find(f"{WQ}pPr")
            p.insert(1 if ppr is not None else 0, start)

            end = etree.SubElement(p, f"{WQ}commentRangeEnd")
            end.set(f"{WQ}id", str(cid))
            run = etree.SubElement(p, f"{WQ}r")
            rpr = etree.SubElement(run, f"{WQ}rPr")
            style = etree.SubElement(rpr, f"{WQ}rStyle")
            style.set(f"{WQ}val", "CommentReference")
            ref = etree.SubElement(run, f"{WQ}commentReference")
            ref.set(f"{WQ}id", str(cid))

            croot.append(etree.fromstring(comment_body_xml(cid, v["comment"]).encode("utf-8")))
            written.append((v["claim_id"], cid, idx))

        dtree.write(str(doc_path), xml_declaration=True, encoding="UTF-8", standalone=True)
        ctree.write(
            str(comments_path), xml_declaration=True, encoding="UTF-8", standalone=True
        )
        ensure_rel(
            root_dir / "word" / "_rels" / "document.xml.rels", COMMENTS_REL, "comments.xml"
        )
        ensure_override(
            root_dir / "[Content_Types].xml", "/word/comments.xml", DOCX_COMMENTS_CT
        )
        rezip(root_dir, dst)
        return written, skipped
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# pptx
# --------------------------------------------------------------------------


def write_pptx(src, dst, verdicts):
    etree = _lxml()

    tmp = tempfile.mkdtemp(prefix="evcheck-pptx-")
    try:
        unzip(src, tmp)
        root_dir = Path(tmp)

        slides = sorted(
            (root_dir / "ppt" / "slides").glob("slide*.xml"),
            key=lambda p: int("".join(ch for ch in p.stem if ch.isdigit()) or 0),
        )
        if not slides:
            sys.exit("error: no ppt/slides/slideN.xml; is this a real .pptx?")

        # commentAuthors.xml, shared across the package.
        authors_path = root_dir / "ppt" / "commentAuthors.xml"
        if authors_path.exists():
            atree = etree.parse(str(authors_path), _parser(etree))
            aroot = atree.getroot()
        else:
            aroot = etree.fromstring(
                f'<p:cmAuthorLst xmlns:p="{PML}"></p:cmAuthorLst>'.encode("utf-8")
            )
            atree = etree.ElementTree(aroot)

        author_id = None
        for a in aroot.findall(f"{PQ}cmAuthor"):
            if a.get("name") == AUTHOR:
                author_id = a.get("id")
        if author_id is None:
            used = {
                int(a.get("id"))
                for a in aroot.findall(f"{PQ}cmAuthor")
                if (a.get("id") or "").isdigit()
            }
            author_id = str(max(used) + 1 if used else 0)
            a = etree.SubElement(aroot, f"{PQ}cmAuthor")
            a.set("id", author_id)
            a.set("name", AUTHOR)
            a.set("initials", INITIALS)
            a.set("lastIdx", "1")
            a.set("clrIdx", str(len(used)))
        atree.write(
            str(authors_path), xml_declaration=True, encoding="UTF-8", standalone=True
        )
        ensure_rel(
            root_dir / "ppt" / "_rels" / "presentation.xml.rels",
            AUTHORS_REL,
            "commentAuthors.xml",
        )
        ensure_override(
            root_dir / "[Content_Types].xml", "/ppt/commentAuthors.xml", PPTX_AUTHORS_CT
        )

        by_slide = {}
        skipped = []
        for v in verdicts:
            a = v["anchor"]
            if a.get("type") != "pptx":
                skipped.append((v["claim_id"], f"anchor type '{a.get('type')}' is not pptx"))
                continue
            s = a.get("slide_index")
            if not isinstance(s, int) or s < 0 or s >= len(slides):
                skipped.append(
                    (v["claim_id"], f"slide_index {s} outside 0..{len(slides) - 1}")
                )
                continue
            by_slide.setdefault(s, []).append(v)

        (root_dir / "ppt" / "comments").mkdir(parents=True, exist_ok=True)
        written = []
        for s_idx, items in sorted(by_slide.items()):
            slide_no = int("".join(ch for ch in slides[s_idx].stem if ch.isdigit()))
            cpath = root_dir / "ppt" / "comments" / f"comment{slide_no}.xml"
            if cpath.exists():
                ctree = etree.parse(str(cpath), _parser(etree))
                croot = ctree.getroot()
                used = {
                    int(c.get("idx"))
                    for c in croot.findall(f"{PQ}cm")
                    if (c.get("idx") or "").isdigit()
                }
                next_idx = max(used) + 1 if used else 1
            else:
                croot = etree.fromstring(
                    f'<p:cmLst xmlns:p="{PML}" '
                    f'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                    f"</p:cmLst>".encode("utf-8")
                )
                ctree = etree.ElementTree(croot)
                next_idx = 1

            for v in items:
                cm = etree.SubElement(croot, f"{PQ}cm")
                cm.set("authorId", author_id)
                cm.set("dt", now_iso())
                cm.set("idx", str(next_idx))
                pos = etree.SubElement(cm, f"{PQ}pos")
                pos.set("x", str(PPTX_POS[0]))
                pos.set("y", str(PPTX_POS[1]))
                txt = etree.SubElement(cm, f"{PQ}text")
                txt.text = v["comment"]
                written.append((v["claim_id"], next_idx, s_idx))
                next_idx += 1

            ctree.write(str(cpath), xml_declaration=True, encoding="UTF-8", standalone=True)
            ensure_rel(
                root_dir / "ppt" / "slides" / "_rels" / f"slide{slide_no}.xml.rels",
                COMMENTS_REL,
                f"../comments/comment{slide_no}.xml",
            )
            ensure_override(
                root_dir / "[Content_Types].xml",
                f"/ppt/comments/comment{slide_no}.xml",
                PPTX_COMMENTS_CT,
            )

        rezip(root_dir, dst)
        return written, skipped
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# pdf
# --------------------------------------------------------------------------


def write_pdf(src, dst, verdicts):
    try:
        from pypdf import PdfReader, PdfWriter
        from pypdf.annotations import Text
    except ImportError:
        sys.exit("error: writing pdf annotations needs pypdf")

    reader = PdfReader(str(src))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    written = []
    skipped = []
    for v in verdicts:
        a = v["anchor"]
        if a.get("type") != "pdf":
            skipped.append((v["claim_id"], f"anchor type '{a.get('type')}' is not pdf"))
            continue
        page_no = a.get("page")
        if not isinstance(page_no, int) or page_no < 1 or page_no > len(writer.pages):
            skipped.append((v["claim_id"], f"page {page_no} outside 1..{len(writer.pages)}"))
            continue
        page = writer.pages[page_no - 1]
        box = page.mediabox
        y = a.get("y")
        if y is None:
            y = float(box.top) - 72.0
        x = float(box.right) - 36.0
        annot = Text(rect=(x - 18, float(y) - 9, x, float(y) + 9), text=v["comment"])
        writer.add_annotation(page_number=page_no - 1, annotation=annot)
        written.append((v["claim_id"], len(written), page_no))

    with open(dst, "wb") as fh:
        writer.write(fh)
    return written, skipped


# --------------------------------------------------------------------------


WRITERS = {".docx": write_docx, ".pptx": write_pptx, ".pdf": write_pdf}
NO_IN_PLACE = {".pptx"}


def validate(path):
    """Reopen the written file so a structural break surfaces here, not in Word."""
    ext = Path(path).suffix.lower()
    try:
        if ext == ".docx":
            with zipfile.ZipFile(path) as z:
                z.read("word/document.xml")
                z.read("word/comments.xml")
        elif ext == ".pptx":
            from pptx import Presentation

            Presentation(str(path))
        elif ext == ".pdf":
            from pypdf import PdfReader

            PdfReader(str(path)).pages[0]
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("document", help="the deliverable to annotate")
    ap.add_argument("verdicts", help="JSON file of verdict records")
    ap.add_argument("-o", "--output", help="write to this path (default: <stem>-checked<ext>)")
    ap.add_argument(
        "--in-place",
        action="store_true",
        help="modify the document itself; requires the user's approval for this file",
    )
    ap.add_argument("--dry-run", action="store_true", help="report what would be written")
    args = ap.parse_args()

    src = Path(args.document)
    if not src.exists():
        sys.exit(f"error: no such file: {src}")
    ext = src.suffix.lower()
    if ext not in WRITERS:
        sys.exit(
            f"error: {ext} has no comment layer. Supported: "
            f"{', '.join(sorted(WRITERS))}. Deliver the markdown report instead."
        )
    if args.in_place and ext in NO_IN_PLACE:
        sys.exit(
            f"error: --in-place is refused for {ext}. This writer is validated by "
            "reopening and by LibreOffice, not against PowerPoint itself, so it "
            "writes a copy. Drop --in-place and use -o."
        )

    verdicts = load_verdicts(args.verdicts)

    if args.dry_run:
        print(f"{src.name}: {len(verdicts)} verdict(s) would be written as comments")
        for v in verdicts:
            first = v["comment"].split("\n")[0][:72]
            print(f"  {v['claim_id']:<6} {v['anchor']}  {first}")
        dest = src if args.in_place else Path(args.output or f"{src.stem}-checked{src.suffix}")
        print(f"  destination: {dest}")
        return

    if args.in_place:
        dst = src.with_suffix(src.suffix + ".tmp")
    else:
        dst = Path(args.output) if args.output else src.with_name(f"{src.stem}-checked{src.suffix}")

    written, skipped = WRITERS[ext](src, dst, verdicts)

    problem = validate(dst)
    if problem:
        Path(dst).unlink(missing_ok=True)
        sys.exit(f"error: the annotated file failed to reopen, nothing written ({problem})")

    if args.in_place:
        shutil.move(str(dst), str(src))
        dst = src

    print(f"wrote {len(written)} comment(s) to {dst}")
    for claim_id, cid, loc in written:
        print(f"  {claim_id} -> comment {cid} at {loc}")
    if skipped:
        print(f"skipped {len(skipped)}:")
        for claim_id, why in skipped:
            print(f"  {claim_id}: {why}")
        sys.exit(1)


if __name__ == "__main__":
    main()
