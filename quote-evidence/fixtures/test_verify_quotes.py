#!/usr/bin/env python3
"""
test_verify_quotes.py

Build-gating assertions for quote-evidence. package.sh runs every *.py directly
under fixtures/ and treats a nonzero exit as a build failure, so this must never
silently no-op.

Two things are being proven, and the second matters more than the first:

  1. The parser reads every transcript shape into the same IR, and the locator
     degrades from timestamp to line number rather than to nothing.

  2. The matcher accepts every legitimate construction the quoting rules permit
     (bracketed insertions, ellipsis joins, typographic drift) AND rejects the
     constructions that destroy the audit trail (summarised quotes, joins that
     cross speakers, joins that reverse the source order, brackets that hide a
     passage).

The second half includes a mutation self-test: a quote that verifies is altered
by one word and must then fail. Without it a matcher that returns "pass" for
everything would sail through the rest of the suite, and a verifier that rubber
stamps is worse than no verifier, because its presence implies a check that is
not happening.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import transcript_ir as ir          # noqa: E402
import verify_quotes as vq          # noqa: E402

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"PASS  {label}")
    else:
        print(f"FAIL  {label}" + (f"\n        {detail}" if detail else ""))
        FAILURES.append(label)


# ---------------------------------------------------------------------------
# Sample sources, one per format the parsers claim to handle
# ---------------------------------------------------------------------------
LABELLED_MD = """\
[0:00] Dana: OK, so let's get started. Tell me about the intake process.
[0:12] Priya: We don't have a written policy for how that gets done. It changes by region and nobody owns it.
[0:31] Dana: Who requests the records today?
[0:44] Priya: The office assistant does it, but it is her other duties as assigned, and she also handles the data entry and the education records for us. She works for seven specialists across the state.
[1:02] Priya: And then we run into the problem of consent, because after nineteen they have to legally give their consent to stay in custody.
"""

UNLABELLED_MD = """\
# Sample Interview-20260717_100203-Meeting Recording

**Date:** 2026-07-17

**Source:** transcripts/Sample Interview.docx

**Note:** Teams auto-transcript. No speaker attribution in source.

**[0:04]** We don't have a written policy for how that gets done. It changes by region.

**[1:12]** The office assistant handles it, but it is her other duties as assigned.
"""

VTT = """\
WEBVTT

00:00:01.000 --> 00:00:06.000
<v Dana>OK, so let's get started.

00:00:06.500 --> 00:00:12.000
<v Priya>We don't have a written policy for how that gets done.
"""

SRT = """\
1
00:00:01,000 --> 00:00:06,000
Dana: OK, so let's get started.

2
00:00:06,500 --> 00:00:12,000
Priya: We don't have a written policy for how that gets done.
"""

OTTER = """\
Dana  0:01
OK, so let's get started.

Priya  0:06
We don't have a written policy for how that gets done.
"""

PLAIN = """\
We don't have a written policy for how that gets done.

The office assistant handles it, but it is her other duties as assigned.
"""

JSON_EXPORT = json.dumps({"segments": [
    {"speaker": "Dana", "start": 1.0, "end": 6.0, "text": "OK, so let's get started."},
    {"speaker": "Priya", "start": 6.5, "end": 12.0,
     "text": "We don't have a written policy for how that gets done."},
]})


def write_sources(root: Path) -> dict:
    files = {
        "labelled.md": LABELLED_MD,
        "unlabelled.md": UNLABELLED_MD,
        "sample.vtt": VTT,
        "sample.srt": SRT,
        "otter.txt": OTTER,
        "plain.txt": PLAIN,
        "export.json": JSON_EXPORT,
    }
    out = {"dir": root}
    for name, body in files.items():
        p = root / name
        p.write_text(body, encoding="utf-8")
        out[name] = p
    return out


# ---------------------------------------------------------------------------
# 1. Parsing
# ---------------------------------------------------------------------------
def test_parsers(files):
    t = ir.load(files["labelled.md"])
    check("labelled md: 5 segments", len(t.segments) == 5, f"got {len(t.segments)}")
    check("labelled md: speakers labelled", t.speaker_mode == "labelled", t.speaker_mode)
    check("labelled md: timestamp locator", t.locator_kind == "timestamp", t.locator_kind)
    check("labelled md: mm:ss read as minutes", t.segments[1].start == "0:00:12",
          str(t.segments[1].start))
    check("labelled md: speaker captured", t.segments[1].speaker == "Priya",
          str(t.segments[1].speaker))

    a = ir.load(files["unlabelled.md"])
    check("unlabelled md: 2 segments", len(a.segments) == 2, f"got {len(a.segments)}")
    check("unlabelled md: no speaker mode", a.speaker_mode == "none", a.speaker_mode)
    check("unlabelled md: header note detected", a.explicit_no_speakers is True)
    check("unlabelled md: metadata lines not read as speech",
          all("Teams auto-transcript" not in s.text for s in a.segments))
    check("unlabelled md: stamp says unattributed",
          ir.stamp(a, a.segments[0]).startswith("unattributed, unlabelled.md @ 0:00:04"),
          ir.stamp(a, a.segments[0]))

    v = ir.load(files["sample.vtt"])
    check("vtt: format detected", v.fmt == "vtt", v.fmt)
    check("vtt: 2 cues", len(v.segments) == 2, f"got {len(v.segments)}")
    check("vtt: voice span speaker", v.segments[0].speaker == "Dana", str(v.segments[0].speaker))
    check("vtt: start normalized", v.segments[0].start == "0:00:01", str(v.segments[0].start))
    check("vtt: end captured", v.segments[0].end == "0:00:06", str(v.segments[0].end))
    check("vtt: markup stripped from text", "<v" not in v.segments[0].text)

    s = ir.load(files["sample.srt"])
    check("srt: format detected", s.fmt == "srt", s.fmt)
    check("srt: comma decimals parsed", s.segments[1].start == "0:00:06", str(s.segments[1].start))
    check("srt: inline speaker captured", s.segments[1].speaker == "Priya", str(s.segments[1].speaker))

    o = ir.load(files["otter.txt"])
    check("otter: speaker plus timestamp shape", o.fmt == "text-speaker-timestamped", o.fmt)
    check("otter: 2 turns", len(o.segments) == 2, f"got {len(o.segments)}")
    check("otter: text follows the label line",
          o.segments[0].text.startswith("OK, so let's get started"), o.segments[0].text)

    j = ir.load(files["export.json"])
    check("json: format detected", j.fmt == "json", j.fmt)
    check("json: numeric seconds normalized", j.segments[1].start == "0:00:06",
          str(j.segments[1].start))

    p = ir.load(files["plain.txt"])
    check("plain: falls back to paragraphs", len(p.segments) == 2, f"got {len(p.segments)}")
    check("plain: locator degrades to line, never to nothing", p.locator_kind == "line",
          p.locator_kind)
    check("plain: stamp carries a line locator", ":L" in ir.stamp(p, p.segments[1]),
          ir.stamp(p, p.segments[1]))


# ---------------------------------------------------------------------------
# 2. Matching: what must pass
# ---------------------------------------------------------------------------
def test_docx_dtd_refused(files):
    import zipfile
    evil = files["dir"] / "evil.docx"
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xml = (f'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "x">]>'
           f'<w:document xmlns:w="{w}"><w:body><w:p><w:r><w:t>&a;</w:t></w:r></w:p></w:body></w:document>')
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("word/document.xml", xml)
    try:
        ir.docx_text(evil)
        refused = False
    except ValueError:
        refused = True
    check("docx declaring a DTD or entity is refused", refused)


def test_accepts(prepared):
    m = vq.verify("We don't have a written policy for how that gets done.", 1, prepared)
    check("exact quote verifies", m.status == "pass", str(m.notes))
    check("exact quote stamped to speaker and moment",
          m.stamp.startswith("Priya, labelled.md @ 0:00:12"), m.stamp)

    drift = "We don’t have a written policy for how that gets done."
    m = vq.verify(drift, 2, prepared)
    check("typographic drift verifies (curly apostrophe, nbsp)", m.status == "pass", str(m.notes))

    m = vq.verify("The office assistant does it, but it is her [other] duties as assigned", 3, prepared)
    check("bracketed insertion verifies", m.status == "pass", str(m.notes))
    check("bracket reports the source text it stands in for",
          m.bracket_fill and "other" in m.bracket_fill[0], str(m.bracket_fill))

    joined = ("We don't have a written policy for how that gets done ... "
              "She works for seven specialists across the state")
    m = vq.verify(joined, 4, prepared)
    check("ellipsis join, same speaker, in order verifies", m.status == "pass", str(m.notes))
    check("ellipsis join is reported as a join",
          any("joined fragments" in n for n in m.notes), str(m.notes))

    m = vq.verify("ok, so let's get started", 5, prepared)
    check("case difference verifies with a note", m.status == "pass", str(m.notes))
    check("case note quotes the source casing",
          any("case differs" in n for n in m.notes), str(m.notes))

    m = vq.verify("We  don't   have a written policy for how that gets done", 6, prepared)
    check("whitespace runs collapse rather than failing", m.status == "pass", str(m.notes))


# ---------------------------------------------------------------------------
# 3. Matching: what must fail
# ---------------------------------------------------------------------------
def test_rejects(prepared):
    m = vq.verify("nobody has a policy for how records get requested", 10, prepared)
    check("summarised quote fails", m.status == "fail", str(m.notes))
    check("failure reports the closest source text",
          m.near_miss is not None and "written policy" in m.near_miss["text"],
          str(m.near_miss))

    crossed = ("We don't have a written policy for how that gets done ... "
               "Who requests the records today")
    m = vq.verify(crossed, 11, prepared)
    check("ellipsis join across speakers fails", m.status == "fail", str(m.notes))
    check("cross-speaker failure names the mechanism",
          any("cross speakers" in n for n in m.notes), str(m.notes))

    reversed_join = ("She works for seven specialists across the state ... "
                     "We don't have a written policy for how that gets done")
    m = vq.verify(reversed_join, 12, prepared)
    check("ellipsis join that reverses source order fails", m.status == "fail", str(m.notes))

    hidden = ("The office assistant does it, [and works with several other units] "
              "She works for seven specialists across the state")
    m = vq.verify(hidden, 13, prepared)
    check("bracket hiding more than MAX_BRACKET_GAP of source fails",
          m.status == "fail", str(m.notes))

    m = vq.verify("We don't have a written protocol for how that gets done", 14, prepared)
    check("single wrong word fails", m.status == "fail", str(m.notes))


# ---------------------------------------------------------------------------
# 4. Mutation self-test: prove the matcher is not rubber-stamping
# ---------------------------------------------------------------------------
def test_mutation(prepared):
    original = "We don't have a written policy for how that gets done."
    baseline = vq.verify(original, 20, prepared)
    if baseline.status != "pass":
        check("mutation self-test baseline verifies", False,
              "baseline quote did not verify, so the mutation test proves nothing")
        return
    mutated = original.replace("written", "formal")
    m = vq.verify(mutated, 21, prepared)
    check("mutation self-test: altered quote is caught", m.status == "fail",
          "the matcher passed a quote whose wording is not in the source, which means "
          "the matcher itself is broken and every other PASS above is meaningless")


# ---------------------------------------------------------------------------
# 5. Attribution rules
# ---------------------------------------------------------------------------
def test_attribution(files):
    corpus = [ir.load(files["unlabelled.md"])]

    prepared = vq.prepare(corpus)
    m = vq.verify("We don't have a written policy for how that gets done.", 1, prepared)
    check("unlabelled source verifies but refuses a speaker",
          m.status == "pass" and m.stamp.startswith("unattributed,"), m.stamp)

    prepared = vq.prepare(corpus, {"unlabelled": "P03"})
    m = vq.verify("We don't have a written policy for how that gets done.", 1, prepared)
    check("speaker map attributes an unlabelled source",
          m.status == "pass" and m.stamp.startswith("P03, unlabelled.md @ 0:00:04"), m.stamp)
    check("speaker map provenance is disclosed on the quote",
          any("speaker map" in n for n in m.notes), str(m.notes))


def test_inference(files):
    """Graded attribution: infer a likely speaker, and mark it as inferred."""
    named = files["dir"] / "Priya_Raman_Interview-20260101.md"
    named.write_text(files["unlabelled.md"].read_text(), encoding="utf-8")
    corpus = [ir.load(named)]
    prepared = vq.prepare(corpus)

    m = vq.verify("We don't have a written policy for how that gets done.", 1, prepared)
    check("first-person quote in a single-participant file infers a likely speaker",
          m.status == "pass" and m.stamp.startswith("likely Priya Raman [inferred],"),
          m.stamp)
    check("the inference names its signal in a note",
          any("inferred from" in n for n in m.notes), str(m.notes))

    # Third person, so the first-person fence does not open.
    m = vq.verify("The office assistant handles it, but it is her other duties as assigned.",
                  1, prepared)
    check("a quote with no first-person marker stays unattributed",
          m.stamp.startswith("unattributed,"), m.stamp)

    # A map is the user's own claim, so it outranks inference and drops the hedge.
    prepared = vq.prepare(corpus, {"priya_raman": "Priya Raman"})
    m = vq.verify("We don't have a written policy for how that gets done.", 1, prepared)
    check("a speaker map outranks inference and carries no [inferred] marker",
          m.stamp.startswith("Priya Raman,") and "[inferred]" not in m.stamp, m.stamp)

    # --no-infer restores the old refusal for anyone who wants it.
    prepared = vq.prepare(corpus, infer=False)
    m = vq.verify("We don't have a written policy for how that gets done.", 1, prepared)
    check("--no-infer restores strict refusal",
          m.stamp.startswith("unattributed,"), m.stamp)


# ---------------------------------------------------------------------------
# 5b. Domain neutrality: no project's vocabulary is compiled into the signals
# ---------------------------------------------------------------------------
def test_domain_neutrality(files):
    """The skill must work on a corpus about anything.

    Two ways it could fail silently: a filename filter tuned to one project's
    subject matter starts reading document titles as people, and a role-bound
    list of one field's job titles attributes nothing on any other field.
    """
    body = files["unlabelled.md"].read_text(encoding="utf-8")

    topic = files["dir"] / "Records Review Session-20260101.md"
    topic.write_text(body, encoding="utf-8")
    check("a file named for a document offers no candidate speaker",
          ir.candidate_names(ir.load(topic))["filename"] == set(),
          str(ir.candidate_names(ir.load(topic))))

    dated = files["dir"] / "July Planning Call.md"
    dated.write_text(body, encoding="utf-8")
    check("a month name in a filename is not read as a person",
          ir.candidate_names(ir.load(dated))["filename"] == set(),
          str(ir.candidate_names(ir.load(dated))))

    # Both quotes below are questions, which shuts the first-person fence on
    # signal 4 and isolates the role-bound signal.
    generic = files["dir"] / "Ines Mwangi Interview.md"
    generic.write_text(body + "\n**[2:20]** Does my crew get told about that?\n",
                       encoding="utf-8")
    m = vq.verify("Does my crew get told about that?", 1,
                  vq.prepare([ir.load(generic)]))
    check("an organisational role term fires the signal on any corpus",
          m.status == "pass" and m.stamp.startswith("likely Ines Mwangi [inferred],"),
          m.stamp)

    domain = files["dir"] / "Nadia Okonjo Interview.md"
    domain.write_text(body + "\n**[2:20]** Are my installers supposed to know that?\n",
                      encoding="utf-8")
    corpus = [ir.load(domain)]
    quote = "Are my installers supposed to know that?"

    m = vq.verify(quote, 1, vq.prepare(corpus))
    check("a domain job title is absent from the default role terms",
          m.status == "pass" and m.stamp.startswith("unattributed,"), m.stamp)

    try:
        ir.set_role_terms(["installers"])
        m = vq.verify(quote, 1, vq.prepare(corpus))
        check("--role-terms adds this corpus's vocabulary to the role-bound signal",
              m.stamp.startswith("likely Nadia Okonjo [inferred],"), m.stamp)
    finally:
        ir.set_role_terms([])  # back to the defaults for the rest of the run

    m = vq.verify(quote, 1, vq.prepare(corpus))
    check("role terms do not leak past the run that set them",
          m.stamp.startswith("unattributed,"), m.stamp)


# ---------------------------------------------------------------------------
# 6. Quote extraction from an artifact
# ---------------------------------------------------------------------------
def test_extraction():
    artifact = (
        'Participants described a gap. "We don\'t have a written policy for how that '
        'gets done."\n'
        '\n'
        'The team calls this "other duties" work.\n'
        '\n'
        '> The office assistant does it, but it is her other duties as assigned.\n'
        '\n'
        '```\n'
        'code = "this quoted string lives in a fenced block and is not speech"\n'
        '```\n'
    )
    quotes, skipped = vq.extract_quotes(artifact, vq.DEFAULT_MIN_CHARS, vq.DEFAULT_MIN_WORDS)
    texts = [q for q, _ in quotes]
    check("inline quoted string extracted",
          any("written policy" in t for t in texts), str(texts))
    check("blockquote extracted as a quote",
          any("other duties as assigned" in t for t in texts), str(texts))
    check("short scare quote skipped, not checked",
          any("other duties" == s.strip() for s, _ in skipped), str(skipped))
    check("fenced code block ignored",
          not any("fenced block" in t for t in texts), str(texts))
    check("line numbers reported for each quote", all(n > 0 for _, n in quotes))

    # Single quote marks, British style and straight, must be found as quotes,
    # while apostrophes inside and after words must not open or close one.
    singles = (
        "She said ‘we never get the parts on time, ever’ in March.\n"
        "\n"
        "It's the installers' board, 'which nobody updates after about ten' she said.\n"
        "\n"
        "'cause nobody checks it, and that's fine.\n"
    )
    quotes, _ = vq.extract_quotes(singles, vq.DEFAULT_MIN_CHARS, vq.DEFAULT_MIN_WORDS)
    texts = [q for q, _ in quotes]
    check("curly single-quoted string extracted",
          "we never get the parts on time, ever" in texts, str(texts))
    check("straight single-quoted string extracted, possessive apostrophe ignored",
          "which nobody updates after about ten" in texts, str(texts))
    check("apostrophes alone produce no quote", len(texts) == 2, str(texts))

    # A quote that wraps across lines in the source file is one quote, stamped
    # with the line it starts on. A blank line still ends the paragraph.
    wrapped = (
        "Intro line.\n"
        'He said "the dispatch board is always\n'
        'wrong by lunchtime" and meant it.\n'
    )
    quotes, _ = vq.extract_quotes(wrapped, vq.DEFAULT_MIN_CHARS, vq.DEFAULT_MIN_WORDS)
    check("quote wrapped across lines extracted whole",
          quotes == [("the dispatch board is always wrong by lunchtime", 2)], str(quotes))

    # A nested quote is covered by its outer quote and is not checked twice.
    nested = "\"He told me 'always call dispatch before you roll a truck' every day\"\n"
    quotes, _ = vq.extract_quotes(nested, vq.DEFAULT_MIN_CHARS, vq.DEFAULT_MIN_WORDS)
    check("nested quote checked once, as part of the outer quote",
          len(quotes) == 1 and quotes[0][0].startswith("He told me"), str(quotes))

    # An unclosed double quote cannot be delimited, so it must be reported
    # rather than silently left unchecked.
    unpaired = []
    stray = 'Fine "one closed quote here in this line".\n\nA stray "mark that never closes.\n'
    vq.extract_quotes(stray, vq.DEFAULT_MIN_CHARS, vq.DEFAULT_MIN_WORDS, unpaired=unpaired)
    check("unpaired double quote mark reported with its line", unpaired == [3], str(unpaired))

    # In a .docx each line is a paragraph, so a stray mark cannot pair across two.
    unpaired = []
    quotes, _ = vq.extract_quotes('A stray "mark in one paragraph.\nAnother "one in the next.',
                                  vq.DEFAULT_MIN_CHARS, vq.DEFAULT_MIN_WORDS,
                                  line_is_paragraph=True, unpaired=unpaired)
    check("docx paragraphs do not pair stray marks across paragraphs",
          quotes == [] and unpaired == [1, 2], f"{quotes} {unpaired}")


# ---------------------------------------------------------------------------
# 7. CLI contract: exit codes gate a build
# ---------------------------------------------------------------------------
def test_cli(root: Path, files):
    clean = root / "clean.md"
    clean.write_text('Finding: "We don\'t have a written policy for how that gets done."\n')
    dirty = root / "dirty.md"
    dirty.write_text('Finding: "nobody has a policy for how records get requested."\n')

    cmd = [sys.executable, str(SCRIPTS / "verify_quotes.py"), "--transcripts",
           str(files["labelled.md"])]
    ok = subprocess.run(cmd[:2] + [str(clean)] + cmd[2:], capture_output=True, text=True)
    bad = subprocess.run(cmd[:2] + [str(dirty)] + cmd[2:], capture_output=True, text=True)
    check("CLI exits 0 when every quote verifies", ok.returncode == 0,
          ok.stdout + ok.stderr)
    check("CLI exits 1 when a quote fails", bad.returncode == 1,
          bad.stdout + bad.stderr)

    js = subprocess.run(cmd[:2] + [str(dirty)] + cmd[2:] + ["--json"],
                        capture_output=True, text=True)
    try:
        payload = json.loads(js.stdout)
        check("CLI --json emits parsable results",
              payload["results"][0]["status"] == "fail", js.stdout[:400])
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        check("CLI --json emits parsable results", False, f"{exc}: {js.stdout[:400]}")

    empty = root / "empty.md"
    empty.write_text("No quotes at all in this document.\n")
    none = subprocess.run(cmd[:2] + [str(empty)] + cmd[2:], capture_output=True, text=True)
    check("a document with no quotes says so loudly rather than passing quietly",
          "NO QUOTED STRINGS FOUND" in none.stdout, none.stdout)

    stray = root / "stray.md"
    stray.write_text('Finding: "We don\'t have a written policy for how that gets done."\n\n'
                     'Also "an unclosed quote that was never checked.\n')
    st = subprocess.run(cmd[:2] + [str(stray)] + cmd[2:], capture_output=True, text=True)
    check("CLI exits 1 on an unpaired quote mark, even when every found quote passes",
          st.returncode == 1 and "UNPAIRED QUOTE MARK" in st.stdout, st.stdout)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="quote_evidence_fixture_") as tmp:
        root = Path(tmp)
        files = write_sources(root)

        print("--- parsers ---")
        test_parsers(files)
        test_docx_dtd_refused(files)

        prepared = vq.prepare([ir.load(files["labelled.md"])])
        print("\n--- matcher: constructions that must verify ---")
        test_accepts(prepared)
        print("\n--- matcher: constructions that must fail ---")
        test_rejects(prepared)
        print("\n--- mutation self-test ---")
        test_mutation(prepared)
        print("\n--- attribution ---")
        test_attribution(files)
        print("\n--- graded attribution / inference ---")
        test_inference(files)
        print("\n--- domain neutrality ---")
        test_domain_neutrality(files)
        print("\n--- artifact quote extraction ---")
        test_extraction()
        print("\n--- CLI contract ---")
        test_cli(root, files)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} assertion(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
