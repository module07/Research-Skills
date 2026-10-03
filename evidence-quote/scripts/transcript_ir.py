#!/usr/bin/env python3
"""
transcript_ir.py

Parse any interview transcript into one intermediate representation (IR) so
that quote verification never has to care about the source format.

Everything downstream reads only the IR. Adding support for a new export
(Rev, a new Otter layout, a vendor JSON) means writing one parser here and
changing nothing else.

The IR is a list of Segment records:

    index        position in the transcript, 0-based
    speaker      speaker label, or None when the source does not mark speakers
    start / end  normalized "h:mm:ss" timestamps, or None
    text         the segment's text, exactly as it appears in the source
    line         1-based line number where the segment starts
    char_offset  character offset into the raw file where the segment starts

Two parsers cover every format in practice:

  1. parse_captions   structured caption/JSON formats (VTT, SRT, JSON exports)
  2. parse_text       heuristic line parser. Otter, Reduct, Rev, hand-cleaned
                      markdown and unmarked transcripts all reduce to
                      "optional speaker label plus optional timestamp at line
                      start, then text", so they share one parser.

Two properties recorded per transcript matter as much as the segments:

  locator_kind      "timestamp" when the source carries time anchors,
                    otherwise "line". A transcript with no timestamps is still
                    fully citable by line number, so nothing is ever unanchored.

  speaker_mode      "labelled" or "none". When it is "none" the transcript
                    cannot support within-file attribution and the IR says so.
                    Inferring a speaker from interview structure (interviewer
                    asks, participant answers) is right most of the time and
                    silently wrong exactly where it matters, so it is not done.
                    A speaker map supplied by the user is the only way to
                    attribute an unlabelled file.

  cleanliness       "asr-raw", "lightly-cleaned" or "unknown", inferred from
                    disfluency density. This is what makes a quote's stamp
                    honest: a quote taken verbatim from a clean-read transcript
                    is not verbatim from the participant's mouth, and the tier
                    records which one is being cited. "unknown" is returned
                    rather than "clean-read" whenever the evidence is only an
                    absence of disfluencies, since a fluent speaker looks the
                    same as a cleaned transcript.

Run directly to inspect what the parser sees:

    python3 transcript_ir.py <file-or-dir> [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, Optional
from xml.etree import ElementTree as ET

TEXT_SUFFIXES = {".md", ".txt", ".markdown", ".text"}
CAPTION_SUFFIXES = {".vtt", ".srt"}
JSON_SUFFIXES = {".json"}
DOCX_SUFFIXES = {".docx"}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | CAPTION_SUFFIXES | JSON_SUFFIXES | DOCX_SUFFIXES

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


# ---------------------------------------------------------------------------
# IR
# ---------------------------------------------------------------------------
@dataclass
class Segment:
    index: int
    text: str
    line: int
    char_offset: int
    speaker: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None


@dataclass
class Transcript:
    path: str
    fmt: str
    segments: list = field(default_factory=list)
    speaker_mode: str = "none"          # "labelled" | "none"
    locator_kind: str = "line"          # "timestamp" | "line"
    cleanliness: str = "unknown"        # "asr-raw" | "lightly-cleaned" | "unknown"
    header_note: Optional[str] = None
    explicit_no_speakers: bool = False
    # True when segments merge more than one voice (an interviewer question and
    # a participant answer inside one timestamped block). Sentence position
    # carries no attribution information in such a file, so inference from
    # filename or structure is refused and stamps degrade to unattributed.
    merged_voices: bool = False

    @property
    def name(self) -> str:
        return Path(self.path).name

    def to_dict(self) -> dict:
        d = asdict(self)
        d["segments"] = [asdict(s) for s in self.segments]
        d["name"] = self.name
        return d


def locator(transcript: Transcript, seg: Segment) -> str:
    """The within-file locator for a segment, degrading timestamp -> line."""
    if seg.start:
        return f"@ {seg.start}"
    return f":L{seg.line}"


def stamp(transcript: Transcript, seg: Segment, speaker: Optional[str] = None,
          inferred: bool = False) -> str:
    """The source stamp for a quote found in this segment.

    Reads "speaker, file, locator". When the transcript cannot support
    attribution the speaker field says so out loud rather than being omitted,
    because a stamp missing its speaker field looks like an oversight while
    "unattributed" is a claim about the source.

    Attribution is graded, and the grade rides in the stamp string rather than
    in a run-level warning, because quotes get lifted onto stickies and slides
    one at a time and a footer does not survive that copy:

        A. Participant, file.md @ 0:42:07                    marked in the source
        likely A. Participant [inferred], file.md @ 0:42:07   inferred from signals
        unattributed, file.md @ 0:42:07                       no usable signal

    `inferred` is ignored when the segment carries a marked speaker, since a
    marked speaker is never an inference.
    """
    if seg.speaker:
        return f"{seg.speaker}, {transcript.name} {locator(transcript, seg)}"
    if speaker:
        who = f"likely {speaker} [inferred]" if inferred else speaker
    else:
        who = "unattributed"
    return f"{who}, {transcript.name} {locator(transcript, seg)}"


# ---------------------------------------------------------------------------
# Speaker inference
# ---------------------------------------------------------------------------
# Signals that a name in the text belongs to the person speaking, strongest
# first. Each returns the matched name, or None. A signal is only allowed to
# fire on a name we already know is a participant in this corpus, which keeps
# it from attributing to a third party mentioned in passing.
_SELF_ID = re.compile(
    r"\b(?:I'?m|I am|this is|my name(?:'s| is))\s+([A-Z][a-z]+(?: [A-Z][a-z]+)?)")
_ADDRESS = re.compile(
    r"(?:^|[.,?!]\s+)([A-Z][a-z]+),\s|,\s([A-Z][a-z]+)[.?!]\s*$")
_FIRST_PERSON = re.compile(
    r"\b(?:I|my|mine|myself|we|us|our|ours)(?:['’](?:m|ve|ll|d|re))?\b", re.I)

# Nouns that follow "my" and denote a scope of responsibility rather than a
# personal relationship: "my unit" is role-bound, "my brother" is not. The list
# is organisational rather than occupational on purpose, so the signal carries
# across domains instead of encoding whichever field the last project was in.
# Occupational vocabulary ("my nurses", "my installers", "my analysts") is
# corpus-specific and is added per run with --role-terms.
DEFAULT_ROLE_TERMS = (
    "unit", "units", "team", "teams", "staff", "crew", "crews", "shop", "store",
    "department", "division", "branch", "office", "program", "programme",
    "project", "projects", "practice", "site", "sites", "region", "territory",
    "district", "caseload", "portfolio", "accounts", "clients", "customers",
    "patients", "students", "reports", "direct reports", "group", "desk", "lab",
    "floor", "shift", "queue", "budget", "org", "people", "guys",
)


def _compile_role_bound(terms) -> "re.Pattern":
    alts = "|".join(re.escape(t) for t in terms)
    return re.compile(rf"\bmy (?:own )?(?:{alts})\b", re.I)


_ROLE_BOUND = _compile_role_bound(DEFAULT_ROLE_TERMS)


def set_role_terms(terms, replace: bool = False):
    """Extend (or replace) the nouns the role-bound signal recognises.

    Domain vocabulary belongs to a corpus, not to this file. A run over HVAC
    interviews wants "my installers"; a run over a hospital wants "my nurses";
    hard-coding either one leaves the signal inert on every other project. The
    fence that makes the signal safe is unchanged either way: it still only
    fires when the filename resolves to exactly one person.
    """
    global _ROLE_BOUND
    terms = tuple(t.strip() for t in terms if t and t.strip())
    combined = terms if replace else DEFAULT_ROLE_TERMS + terms
    _ROLE_BOUND = _compile_role_bound(combined)
    return _ROLE_BOUND


# Words that make a title-case bigram a document description rather than a
# person. Generic on purpose: these are the words that show up in exported
# recording and note filenames whatever the subject matter is.
_NON_PERSON = re.compile(
    r"\b(?:meeting|recording|interview|session|call|sync|standup|stand\s*up|"
    r"workshop|walk\s*through|walkthrough|kickoff|kick\s*off|debrief|demo|"
    r"review|retro|retrospective|transcript|transcription|notes?|minutes|"
    r"summary|report|records?|research|study|survey|analysis|findings|draft|"
    r"final|full|part|copy|clean|cleaned|raw|edited|audio|video|zoom|teams|"
    r"meet|webex|process|overview|discussion|feedback|training|onboarding|"
    r"about|with|for|and|the|of|en|us|new|old)\b", re.I)

# Applied to filename fragments only. A self-identification ("I'm Jan") is
# evidence about a person; a date in a filename is not, and month and weekday
# names are the commonest way a filename produces a convincing-looking bigram.
_DATE_WORD = re.compile(
    r"\b(?:january|february|march|april|may|june|july|august|september|october|"
    r"november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)


def _person_like(name: str) -> bool:
    """Does this look like a person's name rather than a document description?"""
    if _NON_PERSON.search(name):
        return False
    return bool(re.fullmatch(r"[A-Z][a-z]{1,15}(?: [A-Z][a-z]{1,15})?", name))


def _person_like_filename(name: str) -> bool:
    """As `_person_like`, plus the date filtering only filenames need."""
    return _person_like(name) and not _DATE_WORD.search(name)


def candidate_names(transcript: "Transcript") -> dict:
    """Names that plausibly identify a speaker, keyed to how they were found.

    Returns {"selfid": {...}, "filename": {...}}. Self-identification is the
    reliable set. The filename set is weak on its own: a filename containing a
    participant's name does not make the file single-speaker, so it is only
    ever used to disambiguate a signal that has already fired in the text.

    The filename set assumes files are named for the people in them. On a
    corpus named for topics instead, a title-case bigram can survive the
    non-person filter and be read as a participant, which is what --no-infer
    and an explicit speaker map exist for.
    """
    selfid = set()
    for seg in transcript.segments:
        for m in _SELF_ID.finditer(seg.text):
            if _person_like(m.group(1)):
                selfid.add(m.group(1))
    fromfile = set()
    stem = re.sub(r"[-_]", " ", Path(transcript.path).stem)
    for m in re.finditer(r"\b([A-Z][a-z]+ [A-Z][a-z]+)\b", stem):
        if _person_like_filename(m.group(1)):
            fromfile.add(m.group(1))
    return {"selfid": selfid, "filename": fromfile}


def infer_speaker(transcript: "Transcript", seg: "Segment", quote: str = ""):
    """Infer the likely speaker of `quote` within `seg`. Returns (name, signal).

    Returns (None, reason) when no signal fires or signals conflict. Graded
    attribution is the point: a wrong name stated confidently is worse than no
    name, so anything short of a clean signal degrades to unattributed.

    Signals, strongest first:
      1. self-id     the speaker names themselves inside the quoted words
      2. role-bound  the quoted words claim a scope of responsibility only one
                     participant holds ("my unit", "my caseload"), resolved
                     against the filename. See DEFAULT_ROLE_TERMS and
                     set_role_terms for how domain vocabulary is added.
      3. address     another participant names them at the point of speaking

    Signals are evaluated against the quoted text first and the containing
    segment only as a fallback, because in a merged segment (interviewer
    question and participant answer sharing one block) the block tells you
    almost nothing about which voice a given sentence belongs to. That is also
    why a merged segment with no signal reports the merge as its reason: the
    caller should understand it as "could be the interviewer", not "silent".
    """
    if seg.speaker:
        return seg.speaker, "marked"

    names = candidate_names(transcript)
    known = names["selfid"] | names["filename"]
    text = quote or seg.text

    m = _SELF_ID.search(text)
    if m and _person_like(m.group(1)):
        return m.group(1), "self-id"

    # Role-bound first person inside the quote itself. Needs exactly one
    # person-like name on the file to resolve to, which is what makes this
    # safe on a single-participant interview and inert on a group session.
    if _ROLE_BOUND.search(text) and len(names["filename"]) == 1:
        return next(iter(names["filename"])), "role-bound"

    hits = {g for mm in _ADDRESS.finditer(text) for g in mm.groups() if g}
    named = {h for h in hits if any(h == k or k.startswith(h + " ") for k in known)}
    if len(named) == 1:
        who = named.pop()
        full = next((k for k in known if k == who or k.startswith(who + " ")), who)
        return full, "address"

    # Weakest signal that is still worth having: first-person testimony in a
    # file named for exactly one participant. This is the inference a careful
    # reader makes unaided, and refusing to make it leaves most of a
    # single-participant corpus unattributed for no gain. It is fenced three
    # ways: the quoted words must carry a first-person marker, they must not be
    # a question (interviewers ask, participants answer), and the filename must
    # resolve to exactly one person. Anything else degrades.
    if (len(names["filename"]) == 1
            and _FIRST_PERSON.search(text)
            and "?" not in text):
        return next(iter(names["filename"])), "first-person in single-participant file"

    if transcript.merged_voices:
        return None, "merged segment: sentence could belong to either voice"
    return None, "no attribution signal"


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------
def norm_timestamp(raw) -> Optional[str]:
    """Normalize any timestamp shape to h:mm:ss.

    Accepts "h:mm:ss(.mmm)", "mm:ss", a bare number of seconds, or None.
    Two-part values are read as mm:ss, which is what every transcript tool
    means by "12:29".
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        total = float(raw)
    else:
        s = str(raw).strip().replace(",", ".")
        if not s:
            return None
        parts = s.split(":")
        try:
            nums = [float(p) for p in parts]
        except ValueError:
            return None
        if len(parts) == 3:
            total = nums[0] * 3600 + nums[1] * 60 + nums[2]
        elif len(parts) == 2:
            total = nums[0] * 60 + nums[1]
        elif len(parts) == 1:
            total = nums[0]
        else:
            return None
    if total < 0:
        return None
    total = int(total)
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


# ---------------------------------------------------------------------------
# Cleanliness inference
# ---------------------------------------------------------------------------
_REPEAT_RE = re.compile(r"\b(\w+)\b[,\s]+\b\1\b", re.IGNORECASE)
_FILLER_RE = re.compile(
    r"\b(?:um+|uh+|erm|mmm+|hmm+|you know|i mean|kind of|sort of|like i said)\b",
    re.IGNORECASE,
)


def infer_cleanliness(text: str) -> str:
    words = len(re.findall(r"\b\w+\b", text))
    if words < 200:
        return "unknown"
    hits = len(_REPEAT_RE.findall(text)) + len(_FILLER_RE.findall(text))
    per_1000 = hits * 1000.0 / words
    if per_1000 >= 8:
        return "asr-raw"
    if per_1000 >= 2:
        return "lightly-cleaned"
    # Below the threshold the only evidence is an absence of disfluencies, and a
    # fluent speaker is indistinguishable from a cleaned transcript. Say unknown.
    return "unknown"


# ---------------------------------------------------------------------------
# Line-start patterns for the heuristic text parser
# ---------------------------------------------------------------------------
_TS = r"\d{1,3}:\d{2}(?::\d{2})?(?:[.,]\d{1,3})?"
_SPK = r"[A-Za-z][\w.'’-]*(?:[ \t][\w.'’-]+){0,3}"

# **[0:04]** text            (auto-transcripts exported to Word or markdown)
P_MD_TS = re.compile(rf"^\*\*\[({_TS})\]\*\*\s*(.*)$")
# **[0:04] Speaker:** text
P_MD_TS_SPK = re.compile(rf"^\*\*\[({_TS})\]\s*({_SPK}):\*\*\s*(.*)$")
# [0:04] Speaker: text
P_TS_SPK = re.compile(rf"^\[?({_TS})\]?\s+({_SPK}):\s*(.*)$")
# [0:04] text
P_TS_ONLY = re.compile(rf"^\[({_TS})\]\s*(.*)$")
# Speaker  00:14        (Otter: label and time alone on their own line)
P_SPK_TS_ALONE = re.compile(rf"^({_SPK})\s+({_TS})\s*$")
# Speaker: text
P_SPK_COLON = re.compile(rf"^({_SPK}):\s+(\S.*)$")
# **Speaker:** text
P_MD_SPK_COLON = re.compile(rf"^\*\*({_SPK}):\*\*\s*(.*)$")

# Markdown metadata lines that must never be read as "Speaker: text".
_META_LABELS = {"date", "source", "note", "participant", "duration", "attendees",
                "recorded", "transcript", "meeting", "title", "summary"}


def _looks_like_meta(label: str) -> bool:
    return label.strip().strip("*").lower() in _META_LABELS


def _match_line(stripped: str):
    """Return (speaker, start, text, matched) for a line, or None if no pattern."""
    m = P_MD_TS_SPK.match(stripped)
    if m:
        return m.group(2), m.group(1), m.group(3)
    m = P_MD_TS.match(stripped)
    if m:
        return None, m.group(1), m.group(2)
    m = P_MD_SPK_COLON.match(stripped)
    if m and not _looks_like_meta(m.group(1)):
        return m.group(1), None, m.group(2)
    m = P_TS_SPK.match(stripped)
    if m and not _looks_like_meta(m.group(2)):
        return m.group(2), m.group(1), m.group(3)
    m = P_TS_ONLY.match(stripped)
    if m:
        return None, m.group(1), m.group(2)
    m = P_SPK_TS_ALONE.match(stripped)
    if m:
        return m.group(1), m.group(2), ""
    m = P_SPK_COLON.match(stripped)
    if m and not _looks_like_meta(m.group(1)) and not stripped.startswith(("#", ">", "-", "*")):
        return m.group(1), None, m.group(2)
    return None


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------
def parse_text(raw: str, path: str) -> Transcript:
    """Heuristic line parser covering Otter, Reduct, Rev, markdown and plain text."""
    lines = raw.splitlines()
    offsets, running = [], 0
    for ln in lines:
        offsets.append(running)
        running += len(ln) + 1

    segments: list[Segment] = []
    header: list[str] = []
    cur: Optional[dict] = None
    saw_speaker = saw_ts = False

    def flush():
        nonlocal cur
        if cur is None:
            return
        text = "\n".join(cur["text"]).strip()
        if text:
            segments.append(Segment(
                index=len(segments),
                text=text,
                line=cur["line"],
                char_offset=cur["offset"],
                speaker=cur["speaker"],
                start=norm_timestamp(cur["start"]),
            ))
        cur = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        hit = _match_line(stripped)
        if hit is not None:
            speaker, ts, text = hit
            # An Otter-style bare "Speaker  00:14" line continues the same
            # speaker's turn only if it carries no text; start a segment anyway
            # so the timestamp anchors what follows.
            flush()
            saw_speaker = saw_speaker or speaker is not None
            saw_ts = saw_ts or ts is not None
            cur = {"speaker": speaker, "start": ts, "text": [text] if text else [],
                   "line": i + 1, "offset": offsets[i]}
        elif cur is not None:
            cur["text"].append(stripped)
        else:
            header.append(stripped)
    flush()

    fmt = "text-plain"
    if saw_speaker and saw_ts:
        fmt = "text-speaker-timestamped"
    elif saw_ts:
        fmt = "text-timestamped"
    elif saw_speaker:
        fmt = "text-speaker"

    if not segments:
        # No line pattern matched anywhere. Fall back to paragraph segments so
        # an unmarked wall of text is still citable by line number.
        segments = _paragraph_segments(lines, offsets)
        fmt = "text-plain"
        header = []

    t = Transcript(path=path, fmt=fmt, segments=segments)
    _finalize(t, raw, header)
    return t


def _paragraph_segments(lines, offsets) -> list:
    segments, buf, start_i = [], [], None
    for i, line in enumerate(lines):
        if line.strip():
            if start_i is None:
                start_i = i
            buf.append(line.strip())
        elif buf:
            segments.append(Segment(index=len(segments), text="\n".join(buf),
                                    line=start_i + 1, char_offset=offsets[start_i]))
            buf, start_i = [], None
    if buf:
        segments.append(Segment(index=len(segments), text="\n".join(buf),
                                line=start_i + 1, char_offset=offsets[start_i]))
    return segments


def parse_captions(raw: str, path: str) -> Transcript:
    """WebVTT and SRT. Cue blocks separated by blank lines, arrow time range."""
    arrow = re.compile(rf"({_TS})\s*-->\s*({_TS})")
    lines = raw.splitlines()
    offsets, running = [], 0
    for ln in lines:
        offsets.append(running)
        running += len(ln) + 1

    segments: list[Segment] = []
    i = 0
    saw_speaker = False
    while i < len(lines):
        m = arrow.search(lines[i])
        if not m:
            i += 1
            continue
        start_line, start_off = i + 1, offsets[i]
        start, end = m.group(1), m.group(2)
        i += 1
        body = []
        while i < len(lines) and lines[i].strip():
            body.append(lines[i].strip())
            i += 1
        text = " ".join(body).strip()
        # VTT voice spans: <v Speaker>text</v>
        speaker = None
        vm = re.match(r"^<v\s+([^>]+)>(.*?)(?:</v>)?$", text)
        if vm:
            speaker, text = vm.group(1).strip(), vm.group(2).strip()
        else:
            cm = re.match(rf"^({_SPK}):\s+(\S.*)$", text)
            if cm and not _looks_like_meta(cm.group(1)):
                speaker, text = cm.group(1), cm.group(2)
        text = re.sub(r"<[^>]+>", "", text).strip()
        if text:
            saw_speaker = saw_speaker or speaker is not None
            segments.append(Segment(index=len(segments), text=text, line=start_line,
                                    char_offset=start_off, speaker=speaker,
                                    start=norm_timestamp(start), end=norm_timestamp(end)))

    fmt = "vtt" if raw.lstrip().upper().startswith("WEBVTT") else "srt"
    t = Transcript(path=path, fmt=fmt, segments=segments)
    _finalize(t, raw, [])
    return t


_JSON_TEXT_KEYS = ("text", "transcript", "content", "value", "words")
_JSON_SPEAKER_KEYS = ("speaker", "speaker_name", "speaker_label", "name", "who")
_JSON_START_KEYS = ("start", "start_time", "startTime", "from", "offset", "time")
_JSON_END_KEYS = ("end", "end_time", "endTime", "to")


def _first_key(d: dict, keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def parse_json(raw: str, path: str) -> Transcript:
    """Vendor JSON exports. Finds the first list of dicts that carries text."""
    data = json.loads(raw)

    def find_segments(node):
        if isinstance(node, list):
            if node and isinstance(node[0], dict) and _first_key(node[0], _JSON_TEXT_KEYS) is not None:
                return node
            for item in node:
                found = find_segments(item)
                if found:
                    return found
        elif isinstance(node, dict):
            for key in ("segments", "monologues", "results", "utterances", "paragraphs", "transcript"):
                if key in node:
                    found = find_segments(node[key])
                    if found:
                        return found
            for v in node.values():
                found = find_segments(v)
                if found:
                    return found
        return None

    rows = find_segments(data) or []
    segments, saw_speaker = [], False
    for row in rows:
        text = _first_key(row, _JSON_TEXT_KEYS)
        if isinstance(text, list):  # word-level export
            text = " ".join(str(_first_key(w, _JSON_TEXT_KEYS) or w) for w in text)
        text = str(text or "").strip()
        if not text:
            continue
        speaker = _first_key(row, _JSON_SPEAKER_KEYS)
        speaker = str(speaker).strip() if speaker is not None else None
        saw_speaker = saw_speaker or speaker is not None
        segments.append(Segment(
            index=len(segments), text=text, line=1, char_offset=0,
            speaker=speaker,
            start=norm_timestamp(_first_key(row, _JSON_START_KEYS)),
            end=norm_timestamp(_first_key(row, _JSON_END_KEYS)),
        ))
    t = Transcript(path=path, fmt="json", segments=segments)
    _finalize(t, raw, [])
    return t


def docx_text(path: Path) -> str:
    """Plain text from a .docx, one line per paragraph. No third-party deps."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        # Word never writes a DTD; one here is an entity-expansion attempt.
        raise ValueError(f"{path}: refusing a .docx whose XML declares a DTD or entity")
    root = ET.fromstring(xml)
    out = []
    for para in root.iter(f"{{{W_NS}}}p"):
        runs = [(node.text or "") for node in para.iter(f"{{{W_NS}}}t")]
        out.append("".join(runs))
    return "\n".join(out)


def _detect_merged_voices(t: Transcript) -> bool:
    """Do segments merge more than one voice into a single block?

    Only meaningful on unlabelled transcripts: a labelled one already separates
    voices. The tell is a question mark followed by substantial further text
    inside one segment, which is an interviewer's question and the answer to it
    sharing a block. One such segment could be rhetorical, so this requires the
    pattern to recur across a fifth of the file before it fires.
    """
    if t.speaker_mode == "labelled" or len(t.segments) < 5:
        return False
    merged = 0
    for s in t.segments:
        for m in re.finditer(r"\?\s+", s.text):
            if len(s.text) - m.end() > 120:
                merged += 1
                break
    return merged >= max(2, len(t.segments) // 5)


def _finalize(t: Transcript, raw: str, header: list) -> None:
    t.speaker_mode = "labelled" if any(s.speaker for s in t.segments) else "none"
    t.locator_kind = "timestamp" if any(s.start for s in t.segments) else "line"
    t.cleanliness = infer_cleanliness(" ".join(s.text for s in t.segments))
    t.merged_voices = _detect_merged_voices(t)
    for line in header:
        if re.search(r"no speaker attribution|speakers? (are )?not (identified|attributed|labell?ed)",
                     line, re.IGNORECASE):
            t.header_note = line.strip("* ")
            t.explicit_no_speakers = True


def load(path) -> Transcript:
    """Parse one transcript file into the IR, choosing a parser by suffix."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in DOCX_SUFFIXES:
        return parse_text(docx_text(p), str(p))
    raw = p.read_text(encoding="utf-8", errors="replace")
    if suffix in CAPTION_SUFFIXES:
        return parse_captions(raw, str(p))
    if suffix in JSON_SUFFIXES:
        return parse_json(raw, str(p))
    return parse_text(raw, str(p))


def load_corpus(paths: Iterable) -> list:
    """Load every supported transcript under the given files and directories."""
    out, seen = [], set()
    for entry in paths:
        p = Path(entry)
        candidates = sorted(p.rglob("*")) if p.is_dir() else [p]
        for c in candidates:
            if not c.is_file() or c.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            if c.name.startswith("."):
                continue
            key = str(c.resolve())
            if key in seen:
                continue
            seen.add(key)
            try:
                out.append(load(c))
            except Exception as exc:  # a corpus is not held hostage by one bad file
                print(f"warning: could not parse {c}: {exc}", file=sys.stderr)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Inspect what the transcript parser sees.")
    ap.add_argument("paths", nargs="+", help="transcript files or directories")
    ap.add_argument("--json", action="store_true", help="emit the full IR as JSON")
    ap.add_argument("--segments", type=int, default=0, help="print the first N segments")
    args = ap.parse_args()

    corpus = load_corpus(args.paths)
    if args.json:
        print(json.dumps([t.to_dict() for t in corpus], indent=2))
        return 0

    for t in corpus:
        print(f"{t.name}")
        print(f"  format      {t.fmt}")
        print(f"  segments    {len(t.segments)}")
        print(f"  locator     {t.locator_kind}")
        print(f"  speakers    {t.speaker_mode}"
              + ("  (source states there is no speaker attribution)" if t.explicit_no_speakers else ""))
        print(f"  cleanliness {t.cleanliness}")
        for s in t.segments[:args.segments]:
            head = s.text[:100].replace("\n", " ")
            print(f"    [{s.index}] {stamp(t, s)}  {head}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
