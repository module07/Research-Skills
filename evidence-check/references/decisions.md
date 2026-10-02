# Decisions, and what was rejected

Recorded at build time so a later change is a decision rather than a drift.

## Claim-first only, omissions out of scope

Chosen over a two-pass design that would also read the corpus cold and diff its
themes against the deliverable. Claim-first cannot surface omissions, because
the search is prompted by what is in the document. The limit is written into
`SKILL.md` at the top rather than buried, so the skill does not imply coverage
it lacks.

Revisit if "what did I miss" starts being asked of this skill. The fix is a
second corpus-first pass, and not a tweak to this one.

## Discovery-based intake with a registry

Chosen over a fixed folder argument and over stateless discovery.

Stateless discovery was rejected for two reasons. Scope instability: fuzzy
matching can match differently between runs, so a changed verdict cannot be
attributed to changed evidence rather than a changed search. Lost exclusions:
drafts and prior projects have to be re-excluded every run, and the failure
when they are not is that the audit cites the user's own draft as
corroboration.

The registry's own risk is a stale exclusion persisting invisibly. Countered by
printing the exclusion list on every run.

## Load-bearing triage with a visible drop list

Chosen over auditing every assertion. The drop list is what keeps the triage
honest and is shown at the same time as the keep list, before the sweep. The
user confirms before the expensive step.

## The unit of analysis is named and stored, not assumed

Added when the skill was generalised past its first project. The counting rules
had `participants` written into them, which reads as a general rule but holds
only for moderated research: point the skill at a document review or a ticket
audit and the quantifier table has no denominator to bind to. The unit is now a
registry field, proposed from the corpus on the first run and confirmed before
the sweep.

Two alternatives were rejected. Inferring the unit per run reproduces the
failure the registry exists to prevent, because a denominator that changes
between runs makes a changed verdict unattributable. Supporting several units
in one audit was rejected as well: mixed denominators in one report invite
exactly the comparison the counts are meant to make impossible, and a claim
resting on a different kind of source is better handled in the rationale line.

## Written without project or personal identifiers

The reference docs previously carried a real project's participant names, file
names and absolute paths as worked examples. Replaced with synthetic ones,
marked as synthetic, and the prose addresses the user in the second person.

The reason is not privacy alone. Concrete examples from one domain read as a
description of the expected input, so a document-corpus audit looked like an
off-label use of a research tool. The examples now cover more than one corpus
type for that reason, and the second-person prose makes the skill portable
between users without an edit.

## Counts visible in every verdict

Support, disconfirm and silent are reported separately and never folded into
the grade. Silence is not evidence in either direction.

## No separate `misinterpreted` grade

A misreading is `contradicted` when the source opposes the claim and
`overstated` when the source is thinner than it. A third grade would compete
for the same cases without changing the repair. The rationale line names the
misreading.

## Compose with quote-evidence, do not duplicate it

Verbatim transcript quotes go through `quote-evidence` for verification and
stamping. The two skills are parallel: separate triggers, neither owns the
other. The composition is at one point only, the moment a verbatim string is
printed.

The principle is that shared *semantics* should not be duplicated. Stamp format
and attribution grading are shared truths about provenance, so they live in one
place. This is also why `write_comments.py` implements OOXML comment writing
itself rather than calling the docx skill's `comment.py`: a file format is not a
shared semantic, that helper cannot anchor a comment to a paragraph (which is
the hard part), and depending on it would buy a small amount of XML templating
in exchange for a path dependency on another skill's install location.

## Comment write-back, per format

`.docx` and `.pdf` are verified end to end here: comments and annotations are
written, reopened, and in the docx case confirmed to import as real comments in
LibreOffice.

`.pptx` is shipped copy-only and unverified against PowerPoint. LibreOffice
neither imports nor exports pptx comments, so it cannot validate that path, and
no PowerPoint is available. The writer produces structurally valid legacy
comments and the file reopens cleanly. `--in-place` is refused for pptx until
someone confirms the output once in PowerPoint. When that happens, drop the
refusal and this caveat.

Markdown and plain text have no comment layer and get the report instead.

## Write-back is asked every run

Two separate questions, comments and markdown, either or both or neither.
Approval is per file and never carries to the next one. The script does not
ask; the skill does.
