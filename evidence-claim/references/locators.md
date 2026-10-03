# Stamps and links, by source type

**Every evidence item carries a stamp, and a link wherever the source type has
one.** The stamp says what the source is and where in it; the link is what gets
the reader back there in one click. A verdict whose evidence cannot be reopened
is a verdict that has to be taken on trust.

Filenames and paths throughout this file are placeholders. Use whatever the
project actually names its sources.

## Transcripts

Stamps come from `evidence-quote`, unchanged: speaker, file, locator, with the
attribution grade in the stamp string.

```
J. Okafor, session-07.md @ 0:31:48
likely M. Delgado [inferred], session-04.md @ 0:22:11
unattributed, walkthrough-2026-07-02.md @ 0:06:45
```

Link: the `file://` URI from the registry. A timestamp is not a link, so both go
in.

Do not hand-write these. Verbatim transcript quotes run through
`evidence-quote` before the report is written. If it is not installed, drop to
pointer-only evidence for transcripts and say so in the report header.

## Notes and documents

```
field-notes.md :L142
discovery-readout.docx ¶18
2026-07-summary.pdf p6
```

Line number for text, paragraph index for docx, page for pdf. Link is the
`file://` URI. When a passage is quoted from a note rather than a transcript,
the quote still has to be verbatim, and the stamp carries the file and locator
the same way.

## Board stickies

```
Miro / Synthesis / cluster "Tooling" / sticky 34
```

Board name, frame or cluster, then the item. Link is the board URL with the
item selected where the connector exposes one:

```
https://miro.com/app/board/<boardId>/?moveToWidget=<itemId>
```

For a board that arrived as an image export rather than a live connector, the
stamp names the export file and the visible cluster, and the link is the
`file://` URI of the export:

```
board-export.png / cluster "Tooling", upper left
file:///path/to/project/boards/board-export.png
```

Say "cluster, upper left" rather than inventing a sticky id that nothing can
resolve. An approximate locator that is honest beats a precise one that is
fabricated.

## Bear notes

```
Field notes, day 2 (Bear) ¶4
bear://x-callback-url/open-note?id=<note-id>
```

## Drive files

```
Synthesis working doc (Google Doc) ¶31
https://docs.google.com/document/d/<fileId>/edit
```

## Figma

```
Figma / Onboarding v3 / frame "Handoff step 2"
https://www.figma.com/file/<fileKey>/<name>?node-id=<nodeId>
```

## Charts and derived numbers

When evidence is a count you computed rather than a passage you read, say so
and show the derivation:

```
derived: 3 of 11 participants, from session-04, session-07, session-09
```

The unit is named inside the derivation, because a bare "3 of 11" does not say
what was counted. Never present a derived number as though it were a source.
The three files it rests on are the source, and they get their own stamps.

## When no link exists

Degrade to the stamp alone and say why in one clause: "no link, image export"
or "no link, connector not authorized". Silence about a missing link reads as
an oversight; the clause makes it a stated condition.
