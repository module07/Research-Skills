#!/usr/bin/env python3
"""
verify_quotes.py

Take an artifact that already contains quoted strings and prove each one
against a transcript corpus. This is the check that catches the failure the
whole skill exists for: a passage that was summarised, tidied, or
half-remembered and then wrapped in quotation marks, which cannot be traced
back to a source and misattributes wording to a participant.

    python3 verify_quotes.py <artifact> --transcripts <dir-or-files...>

Exit code 0 when every quote verifies, 1 when any quote fails, so this can
gate a build or a hand-off.

WHY THE MATCHER IS NOT A grep
-----------------------------
The quoting rules this checks against permit three constructions, and a naive
exact-string search fails every legitimate use of all three:

  1. Bracketed insertions    "[Infant learning are] a long standing partner"
     The bracket is the author's word, not the participant's, so it must be
     removed before matching. The source text sitting where the bracket goes
     is reported back, which is how you audit whether the insertion was fair.

  2. Ellipsis joins          "we don't have a policy ... everybody points fingers"
     Non-contiguous fragments from one speaker joined into one quote. Each
     fragment is verified separately, then constrained: fragments must appear
     in document order and must share a speaker. A join that reverses the
     order of the source, or crosses speakers, is a distortion and fails.

  3. Typographic drift       smart quotes, non-breaking spaces, en dashes
     Introduced by the tools between the transcript and the artifact, not by
     the author. Normalized on both sides so they never produce a false alarm.

A verifier with false positives gets ignored within a week, at which point it
is worse than nothing, because its presence implies a check that is not
happening. So every failure also reports the closest text in the corpus, which
is what tells you whether you are looking at a typo, a paraphrase that should
lose its quote marks, or a fabrication.

WHAT IT WILL NOT DO
-------------------
Assert a speaker the evidence does not support. Attribution is graded rather
than refused: a speaker marked in the source is stated plainly, a speaker the
signals point to is stamped "likely X [inferred]", and anything weaker stamps
"unattributed". The grade rides in the stamp string so it survives a copy of
the quote on its own. --speaker-map asserts an attribution explicitly and
outranks inference; --no-infer turns inference off entirely, at which point
every unlabelled source stamps as "unattributed". On a source with no speaker
labels the same-speaker constraint on ellipsis joins cannot be enforced, which
is reported as a warning on the run rather than buried per quote.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import transcript_ir as ir  # noqa: E402

# Maximum source characters a single [bracketed insertion] may stand in for.
# Beyond this the bracket is not clarifying a phrase, it is hiding a passage.
MAX_BRACKET_GAP = 80
# Segment distance beyond which an ellipsis join is reported for review. Joining
# distant passages is allowed and sometimes necessary; doing it silently is not.
FAR_JOIN_SEGMENTS = 8
# Similarity floor below which a "closest passage" is a distractor rather than a
# lead, and floor below which a shown near miss is labelled weak.
NEAR_MISS_FLOOR = 0.45
NEAR_MISS_WEAK = 0.60

DEFAULT_MIN_CHARS = 25
DEFAULT_MIN_WORDS = 4

_CHAR_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "′": "'", "´": "'", "`": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-",
    "—": "-", "―": "-", "−": "-",
    "…": "...",
    " ": " ", " ": " ", " ": " ", " ": " ", " ": " ",
    "​": "", "‌": "", "‍": "", "﻿": "", "­": "",
}


# ---------------------------------------------------------------------------
# Normalization, with an index map back to the untouched source characters
# ---------------------------------------------------------------------------
def normalize_with_map(s: str):
    """Return (normalized, idx_map) where idx_map[i] is the index in `s` that
    produced normalized[i]. The map is what lets a match report the source's
    original characters rather than the normalized stand-in."""
    out, idx = [], []
    prev_space = True
    for i, ch in enumerate(s):
        rep = _CHAR_MAP.get(ch, ch)
        if rep == "":
            continue
        if len(rep) == 1 and rep.isspace():
            if prev_space:
                continue
            out.append(" ")
            idx.append(i)
            prev_space = True
            continue
        for c in rep:
            out.append(c)
            idx.append(i)
        prev_space = False
    while out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


def normalize(s: str) -> str:
    return normalize_with_map(s)[0]


def lower_safe(s: str) -> str:
    """Lowercase only when it preserves length, so the index map stays valid."""
    low = s.lower()
    return low if len(low) == len(s) else s


# ---------------------------------------------------------------------------
# Quote shapes
# ---------------------------------------------------------------------------
_MD_EMPHASIS = re.compile(r"(\*{1,3}|_{1,3})(?=\S)(.+?)(?<=\S)\1", re.DOTALL)
_FOOTNOTE = re.compile(r"\[\^[^\]]*\]")
_BRACKET_SPAN = re.compile(r"\[[^\]]*\]")
_ELLIPSIS_SPLIT = re.compile(r"\s*\.\.\.\s*")


def strip_markup(s: str) -> str:
    s = _FOOTNOTE.sub("", s)
    prev = None
    while prev != s:
        prev = s
        s = _MD_EMPHASIS.sub(r"\2", s)
    return s


def split_quote(quote: str):
    """Normalized quote -> list of fragments, each a list of literal pieces.

    Fragments come from ellipsis joins. Pieces come from removing bracketed
    insertions; the gaps between pieces are where the author's words sit.
    """
    fragments = []
    for frag in _ELLIPSIS_SPLIT.split(quote):
        frag = frag.strip()
        if not frag:
            continue
        pieces = [p.strip() for p in _BRACKET_SPAN.split(frag)]
        pieces = [p for p in pieces if p]
        if pieces:
            fragments.append(pieces)
    return fragments


# ---------------------------------------------------------------------------
# Prepared corpus
# ---------------------------------------------------------------------------
_STOPWORDS = {
    "the", "and", "that", "have", "has", "had", "for", "not", "with", "you", "this",
    "but", "his", "her", "from", "they", "she", "will", "one", "all", "would",
    "there", "their", "what", "out", "about", "who", "get", "which", "when", "make",
    "can", "like", "just", "him", "know", "take", "into", "your", "some", "could",
    "them", "than", "then", "now", "only", "come", "its", "over", "also", "back",
    "after", "use", "two", "our", "well", "way", "even", "want", "because", "any",
    "these", "give", "most", "very", "was", "were", "are", "been", "being", "does",
    "did", "doing", "how", "why", "where", "here", "yeah", "okay", "right", "think",
}


def _content_words(s: str) -> set:
    return {w for w in re.findall(r"[a-z']{3,}", s.lower()) if w not in _STOPWORDS}


@dataclass
class PreparedSegment:
    seg: object
    norm: str
    low: str
    idx: list
    words: set = field(default_factory=set)


@dataclass
class PreparedTranscript:
    transcript: object
    segments: list
    speaker_override: Optional[str] = None
    note_unattributed: bool = False
    note_cleanliness: bool = False
    infer: bool = True


def prepare(corpus, speaker_map=None, infer=True) -> list:
    # When every source in the corpus lacks speaker labels, the run-level warning
    # states it once and a per-quote note would be pure noise. When the corpus is
    # mixed, which source a quote came from decides whether it can be attributed,
    # so the note earns its place.
    mixed = any(t.speaker_mode == "labelled" for t in corpus) and \
        any(t.speaker_mode == "none" for t in corpus)
    # Same reasoning for the cleanliness tier: uniform corpus, state it once in
    # the header; mixed corpus, say which tier each quote is actually citing.
    mixed_clean = len({t.cleanliness for t in corpus}) > 1
    prepared = []
    for t in corpus:
        segs = []
        for s in t.segments:
            norm, idx = normalize_with_map(s.text)
            low = lower_safe(norm)
            segs.append(PreparedSegment(seg=s, norm=norm, low=low, idx=idx,
                                        words=_content_words(low)))
        override = None
        if speaker_map and t.speaker_mode == "none":
            for key, who in speaker_map.items():
                if key.lower() in t.name.lower():
                    override = who
                    break
        prepared.append(PreparedTranscript(
            transcript=t, segments=segs, speaker_override=override,
            note_unattributed=mixed and t.speaker_mode == "none" and override is None,
            note_cleanliness=mixed_clean, infer=infer))
    return prepared


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
@dataclass
class Hit:
    seg_index: int
    spans: list  # [(start, end), ...] in normalized coordinates


@dataclass
class Match:
    status: str                       # "pass" | "fail"
    quote: str
    artifact_line: int
    transcript: Optional[object] = None
    hits: list = field(default_factory=list)
    stamp: str = ""
    source_text: list = field(default_factory=list)
    bracket_fill: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    near_miss: Optional[dict] = None


def _find_fragment(low: str, pieces_low: list, from_pos: int):
    """Locate one fragment's pieces in order within a single segment."""
    pos, spans = from_pos, []
    anchored = False
    for piece in pieces_low:
        if len(piece) < 3:
            continue  # too short to anchor anything, e.g. "[I] said"
        j = low.find(piece, pos)
        if j < 0:
            return None
        if spans and (j - spans[-1][1]) > MAX_BRACKET_GAP:
            return None
        spans.append((j, j + len(piece)))
        pos = j + len(piece)
        anchored = True
    return spans if anchored else None


def _match_in_transcript(fragments_low, pt: PreparedTranscript):
    """All fragments, in document order, within one transcript."""
    cur_seg, cur_pos, hits = 0, 0, []
    for pieces_low in fragments_low:
        found = None
        for si in range(cur_seg, len(pt.segments)):
            start_pos = cur_pos if si == cur_seg else 0
            spans = _find_fragment(pt.segments[si].low, pieces_low, start_pos)
            if spans:
                found = Hit(seg_index=si, spans=spans)
                break
        if found is None:
            return None
        hits.append(found)
        cur_seg, cur_pos = found.seg_index, found.spans[-1][1]
    return hits


def _raw_slice(ps: PreparedSegment, start: int, end: int) -> str:
    if start >= len(ps.idx) or end - 1 >= len(ps.idx) or end <= start:
        return ""
    return ps.seg.text[ps.idx[start]:ps.idx[end - 1] + 1]


def _near_miss(sought_low: str, prepared: list):
    """Closest text in the corpus to a quote that did not verify.

    Ranks by shared content words first, then finds the best character window
    inside the top candidates. Ranking on characters alone misses the case that
    matters most: a paraphrase keeps the participant's content words while
    rewriting everything around them, which scores poorly on raw string
    similarity and is exactly the passage the author meant to quote.
    """
    if len(sought_low) < 12:
        return None
    sought_words = _content_words(sought_low)
    if not sought_words:
        return None

    ranked = []
    for pt in prepared:
        for ps in pt.segments:
            if ps.low:
                overlap = len(sought_words & ps.words)
                if overlap:
                    ranked.append((overlap, pt, ps))
    ranked.sort(key=lambda r: -r[0])
    if not ranked or ranked[0][0] < 2:
        return None

    best = None
    sm = difflib.SequenceMatcher(autojunk=False)
    sm.set_seq2(sought_low)
    for _, pt, ps in ranked[:5]:
        s = ps.low
        window_len = min(len(sought_low) + 24, len(s))
        step = max(4, len(sought_low) // 6)
        for start in range(0, max(1, len(s) - window_len + 1), step):
            sm.set_seq1(s[start:start + window_len])
            ratio = sm.ratio()
            if best is None or ratio > best[0]:
                best = (ratio, pt, ps, start, window_len)
    # Below this similarity the best candidate is a distractor, not a lead. Saying
    # "nothing close" is the more useful answer, because it distinguishes a quote
    # that drifted from its source from one that was never in this research.
    #
    # The cut is calibrated on a handful of real cases, not a corpus, so treat it
    # as a rough divider rather than a measurement: a template string with no
    # source behind it scored 0.33, a loose paraphrase of a real passage 0.48, a
    # drifted real quote 0.67. The reported percentage is what the reader should
    # actually judge on, which is why it is always printed alongside the text.
    if best is None or best[0] < NEAR_MISS_FLOOR:
        return None
    ratio, pt, ps, start, window_len = best
    # Snap the window out to word boundaries so the reported near miss is
    # readable rather than clipped mid-word.
    lo, hi = start, min(start + window_len, len(ps.idx))
    while lo > 0 and ps.low[lo - 1] not in " \t":
        lo -= 1
    while hi < len(ps.low) and ps.low[hi - 1] not in " \t":
        hi += 1
    raw = _raw_slice(ps, lo, hi)
    return {
        "ratio": round(ratio, 3),
        "text": raw.strip(),
        "stamp": ir.stamp(pt.transcript, ps.seg, pt.speaker_override),
    }


def verify(quote: str, artifact_line: int, prepared: list) -> Match:
    norm = normalize(strip_markup(quote))
    fragments = split_quote(norm)
    if not fragments:
        return Match(status="fail", quote=quote, artifact_line=artifact_line,
                     notes=["quote contains no literal text to verify"])
    fragments_low = [[lower_safe(p) for p in frag] for frag in fragments]

    for pt in prepared:
        hits = _match_in_transcript(fragments_low, pt)
        if hits is None:
            continue

        m = Match(status="pass", quote=quote, artifact_line=artifact_line,
                  transcript=pt.transcript, hits=hits)
        first = pt.segments[hits[0].seg_index]

        # Attribution is graded. A map is the user's own claim and outranks
        # inference; inference outranks nothing and marks itself in the stamp.
        inferred_who = inferred_signal = None
        if not pt.speaker_override and not first.seg.speaker and pt.infer:
            inferred_who, inferred_signal = ir.infer_speaker(
                pt.transcript, first.seg, quote)
        m.stamp = ir.stamp(pt.transcript, first.seg,
                           pt.speaker_override or inferred_who,
                           inferred=inferred_who is not None)

        speakers = set()
        for h in hits:
            ps = pt.segments[h.seg_index]
            speakers.add(ps.seg.speaker)
            m.source_text.append(_raw_slice(ps, h.spans[0][0], h.spans[-1][1]))
            for a, b in zip(h.spans, h.spans[1:]):
                fill = _raw_slice(ps, a[1], b[0]).strip()
                if fill:
                    m.bracket_fill.append(fill)

        # Notes: everything a reader would need to audit the quote's fairness.
        if pt.speaker_override:
            m.notes.append(f"speaker '{pt.speaker_override}' comes from the supplied "
                           f"speaker map, not from the source")
        elif inferred_who:
            m.notes.append(f"speaker '{inferred_who}' is inferred from the "
                           f"'{inferred_signal}' signal, not marked in the source; "
                           f"the stamp says so and must keep saying so wherever "
                           f"the quote is pasted")
        elif inferred_signal:
            m.notes.append(f"unattributed ({inferred_signal}), so the quote is "
                           f"traced to a file and a moment but not to a person")
        elif pt.note_unattributed:
            m.notes.append("this source carries no speaker attribution, so the quote is "
                           "traced to a file and a moment but not to a person")
        elif len(speakers) > 1:
            m.status = "fail"
            m.notes.append(f"joined fragments cross speakers ({', '.join(sorted(str(s) for s in speakers))}), "
                           f"which attributes one speaker's words to another")

        if len(hits) > 1:
            span = hits[-1].seg_index - hits[0].seg_index
            first_seg = pt.segments[hits[0].seg_index].seg
            last_seg = pt.segments[hits[-1].seg_index].seg
            where = f"{ir.locator(pt.transcript, first_seg)} to {ir.locator(pt.transcript, last_seg)}"
            m.notes.append(f"{len(hits)} joined fragments, {where}")
            if span >= FAR_JOIN_SEGMENTS:
                m.notes.append(f"joined fragments are {span} segments apart; confirm the "
                               f"join does not change what the speaker meant")

        for got, want in zip(m.source_text, [" ".join(f) for f in fragments]):
            if got and normalize(got) != normalize(want) and \
                    normalize(got).lower() == normalize(want).lower():
                m.notes.append(f"case differs from source, which reads: {got!r}")

        if pt.note_cleanliness:
            m.notes.append(f"source tier is '{pt.transcript.cleanliness}', so this quote is "
                           f"verbatim from that transcript rather than necessarily from "
                           f"the participant's mouth")
        return m

    sought = " ".join(p for frag in fragments for p in frag)
    return Match(status="fail", quote=quote, artifact_line=artifact_line,
                 notes=["no verbatim match in any transcript in the corpus"],
                 near_miss=_near_miss(lower_safe(normalize(sought)), prepared))


# ---------------------------------------------------------------------------
# Pulling quoted strings out of an artifact
# ---------------------------------------------------------------------------
_QUOTED = re.compile(r'"([^"]+)"')
# A single-quoted span opens on a quote mark with no letter or digit before it
# and closes on one with none after it. That separates quote marks from the
# apostrophes inside words (don't, it's). Run on normalized text, where curly
# single quotes are already straight.
_SINGLE_QUOTED = re.compile(r"(?<![\w'])'(?=[^\s'])(.+?)(?<=[^\s'])'(?![\w'])", re.DOTALL)
_BLOCKQUOTE = re.compile(r"^\s{0,3}>\s?(.*)$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def artifact_text(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        return ir.docx_text(path)
    return path.read_text(encoding="utf-8", errors="replace")


def _normalize_marks(s: str) -> str:
    return "".join(_CHAR_MAP.get(c, c) for c in s)


def _quoted_spans(text: str):
    """(start, end, inner) for every double- and single-quoted span in `text`.

    A span that sits inside another span is dropped, because checking the outer
    quote already checks it: a nested quote in either style is part of the
    words the outer quote claims.
    """
    spans = [(m.start(), m.end(), m.group(1)) for m in _QUOTED.finditer(text)]
    spans += [(m.start(), m.end(), m.group(1)) for m in _SINGLE_QUOTED.finditer(text)]
    spans.sort(key=lambda sp: (sp[0], -sp[1]))
    kept = []
    for sp in spans:
        if any(k[0] <= sp[0] and sp[1] <= k[1] for k in kept):
            continue
        kept.append(sp)
    return kept


def extract_quotes(text: str, min_chars: int, min_words: int, blockquotes: bool = True,
                   line_is_paragraph: bool = False, unpaired=None):
    """Return (quotes, skipped). Each quote is (text, line_number).

    Quotes are found per paragraph, not per line, so a quote that wraps across
    lines in the source file is still one quote. A paragraph ends at a blank
    line, a blockquote or a fence. Pass `line_is_paragraph` for text where each
    line already is a paragraph (a .docx), so a stray mark cannot pair across
    paragraphs.

    Short quoted strings are skipped rather than checked, because scare quotes
    and quoted UI labels are not participant speech. The count is reported so
    the skip is visible rather than silent.

    A paragraph with an odd number of double quote marks holds a quote that
    could not be delimited, so it was not checked. Its line number goes into
    `unpaired` when a list is passed, so the caller can say so.
    """
    quotes, skipped = [], []
    in_fence = False
    bq_buf, bq_line = [], None
    para_buf, para_line = [], None

    def flush_bq():
        nonlocal bq_buf, bq_line
        if bq_buf:
            joined = " ".join(bq_buf).strip()
            if joined:
                _classify(joined, bq_line, quotes, skipped, min_chars, min_words)
        bq_buf, bq_line = [], None

    def flush_para():
        nonlocal para_buf, para_line
        if para_buf:
            para = _normalize_marks("\n".join(para_buf))
            if unpaired is not None and para.count('"') % 2:
                unpaired.append(para_line)
            for start, _end, inner in _quoted_spans(para):
                line = para_line + para.count("\n", 0, start)
                inner = re.sub(r"\s*\n\s*", " ", inner).strip()
                _classify(inner, line, quotes, skipped, min_chars, min_words)
        para_buf, para_line = [], None

    for n, line in enumerate(text.splitlines(), start=1):
        if _FENCE.match(line):
            flush_para()
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        bq = _BLOCKQUOTE.match(line) if blockquotes else None
        if bq:
            flush_para()
            if bq_line is None:
                bq_line = n
            bq_buf.append(bq.group(1).strip())
            continue
        flush_bq()

        if not line.strip():
            flush_para()
            continue
        if para_line is None:
            para_line = n
        para_buf.append(line)
        if line_is_paragraph:
            flush_para()
    flush_bq()
    flush_para()
    return quotes, skipped


def _classify(candidate: str, line: int, quotes: list, skipped: list,
              min_chars: int, min_words: int) -> None:
    body = strip_markup(candidate).strip()
    words = len(re.findall(r"\b[\w']+\b", body))
    if len(body) < min_chars or words < min_words:
        skipped.append((candidate, line))
    else:
        quotes.append((candidate, line))


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def shorten(name: str, width: int = 46) -> str:
    if len(name) <= width:
        return name
    keep = (width - 3) // 2
    return f"{name[:keep]}...{name[-keep:]}"


def report(matches, skipped, corpus, artifact: str, verbose: bool,
           unpaired=None) -> int:
    fails = [m for m in matches if m.status == "fail"]
    noted = [m for m in matches if m.status == "pass" and m.notes]

    print(f"artifact: {artifact}")
    tiers = {}
    for t in corpus:
        tiers[t.cleanliness] = tiers.get(t.cleanliness, 0) + 1
    tier_s = ", ".join(f"{k}: {v}" for k, v in sorted(tiers.items()))
    print(f"corpus:   {len(corpus)} transcript(s) ({tier_s})")

    unattributed = [t for t in corpus if t.speaker_mode == "none"]
    if unattributed:
        print(f"warning:  {len(unattributed)} of {len(corpus)} transcript(s) carry no speaker "
              f"attribution.\n"
              f"          Quotes traced to them are anchored to a file and a moment but not\n"
              f"          to a person, and same-speaker checks on joined quotes cannot run.")
    print()

    for m in matches:
        tag = "FAIL" if m.status == "fail" else ("NOTE" if m.notes else "PASS")
        head = m.quote if len(m.quote) <= 88 else m.quote[:85] + "..."
        print(f"{tag}  L{m.artifact_line:<4} \"{head}\"")
        if m.stamp:
            print(f"      {shorten(m.stamp, 200)}")
        for note in m.notes:
            print(f"      note: {note}")
        if m.near_miss:
            weak = " weak match, judge it yourself" if m.near_miss["ratio"] < NEAR_MISS_WEAK else ""
            print(f"      closest in corpus ({int(m.near_miss['ratio'] * 100)}% similar{weak}): "
                  f"\"{m.near_miss['text']}\"")
            print(f"      closest found at: {m.near_miss['stamp']}")
        elif m.status == "fail" and "no verbatim match" in " ".join(m.notes):
            print("      nothing close in the corpus either, so this wording does not "
                  "appear in this research at all")
        if verbose and m.bracket_fill:
            for fill in m.bracket_fill:
                print(f"      bracket replaces source text: \"{fill}\"")
        if tag != "PASS" or verbose:
            print()

    if skipped:
        print(f"skipped {len(skipped)} short quoted string(s) below the length floor "
              f"(scare quotes, labels). Re-run with --min-words 1 to check them too.")
    if unpaired:
        where = ", ".join(f"L{n}" for n in unpaired)
        print(f"UNPAIRED QUOTE MARK in {len(unpaired)} paragraph(s) starting at {where}. "
              f"A quote there could not be delimited, so it was NOT checked. Fix the "
              f"quote marks and re-run.")
    if not matches:
        print("NO QUOTED STRINGS FOUND. Nothing was verified. Check that the artifact "
              "actually contains quotes and that --min-words is not set too high.")

    print(f"\n{len(matches)} quote(s) checked: {len(matches) - len(fails)} pass "
          f"({len(noted)} with notes), {len(fails)} fail")
    return 1 if fails or unpaired else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Verify every quoted string in an artifact against a transcript corpus.")
    ap.add_argument("artifact", help="the .md, .txt or .docx file containing quotes")
    ap.add_argument("--transcripts", nargs="+", required=True,
                    help="transcript files or directories to verify against")
    ap.add_argument("--speaker-map", help="JSON mapping filename substrings to speaker names, "
                                          "used only for sources with no speaker labels")
    ap.add_argument("--min-chars", type=int, default=DEFAULT_MIN_CHARS)
    ap.add_argument("--min-words", type=int, default=DEFAULT_MIN_WORDS)
    ap.add_argument("--no-blockquotes", action="store_true",
                    help="do not treat markdown blockquotes as quotes")
    ap.add_argument("--no-infer", action="store_true",
                    help="do not infer speakers from signals; unlabelled sources "
                         "stamp as 'unattributed'")
    ap.add_argument("--role-terms",
                    help="comma-separated domain nouns that follow 'my' and name a "
                         "scope of responsibility (e.g. 'installers,nurses,analysts'), "
                         "added to the role-bound attribution signal for this corpus")
    ap.add_argument("--json", action="store_true", help="emit results as JSON")
    ap.add_argument("--verbose", action="store_true",
                    help="show bracket fills and per-quote detail for passes too")
    args = ap.parse_args()

    artifact_path = Path(args.artifact)
    if not artifact_path.is_file():
        print(f"ERROR: artifact not found: {artifact_path}", file=sys.stderr)
        return 2

    if args.role_terms:
        ir.set_role_terms(args.role_terms.split(","))

    corpus = ir.load_corpus(args.transcripts)
    if not corpus:
        print("ERROR: no parsable transcripts found. Nothing to verify against, so a "
              "clean result here would be meaningless.", file=sys.stderr)
        return 2

    speaker_map = json.loads(Path(args.speaker_map).read_text()) if args.speaker_map else None
    prepared = prepare(corpus, speaker_map, infer=not args.no_infer)

    unpaired: list = []
    quotes, skipped = extract_quotes(artifact_text(artifact_path), args.min_chars,
                                     args.min_words, not args.no_blockquotes,
                                     line_is_paragraph=artifact_path.suffix.lower() == ".docx",
                                     unpaired=unpaired)
    matches = [verify(q, line, prepared) for q, line in quotes]

    if args.json:
        print(json.dumps({
            "artifact": str(artifact_path),
            "transcripts": [t.name for t in corpus],
            "unattributed_sources": [t.name for t in corpus if t.speaker_mode == "none"],
            "skipped": len(skipped),
            "unpaired_quote_marks": unpaired,
            "results": [{
                "quote": m.quote,
                "artifact_line": m.artifact_line,
                "status": m.status,
                "stamp": m.stamp,
                "source_text": m.source_text,
                "bracket_fill": m.bracket_fill,
                "notes": m.notes,
                "near_miss": m.near_miss,
            } for m in matches],
        }, indent=2))
        return 1 if unpaired or any(m.status == "fail" for m in matches) else 0

    return report(matches, skipped, corpus, str(artifact_path), args.verbose, unpaired)


if __name__ == "__main__":
    sys.exit(main())
