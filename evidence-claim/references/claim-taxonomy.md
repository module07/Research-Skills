# What counts as a load-bearing claim

**The test: a claim is load-bearing if its falsity would force something else
in the document to change.** If nothing downstream moves, drop it.

Everything below applies the test. When a unit is ambiguous, keep it. A claim
wrongly kept costs one sweep; a claim wrongly dropped is a silent gap in the
audit.

## In scope

**Findings.** Assertions about what the evidence shows: what people do, think,
need or experience, what a set of documents records, what a system did.

**Quantifiers and prevalence.** Most, many, several, consistently, rarely, all,
a majority, 7 of 12. These fail quietly and often, because the wording drifts
during writing while the underlying count does not.

**Numbers and proportions.** Including chart axis labels, data labels and
figure captions. A caption is a claim.

**Causal and explanatory claims.** Because, driven by, leads to, the reason is.
The highest-risk category: an observation and an explanation of it are two
claims, and the explanatory half is usually inference that the prose presents
as fact.

**Comparatives and superlatives.** Biggest pain point, most cited, worse than,
the primary blocker.

**Recommendations and implications.** We should, the opportunity is, this means.

**Attributed intent or emotion.** "Users were frustrated by the handoff" claims
both an emotion and its cause. Check both halves.

**Negative claims.** "No source mentioned X", "this never occurred." Hard to
support and often wrong. Sweep for X directly before accepting one, and
remember that silence is not the same as denial.

**Corpus composition.** How many units there are, what they are, and how they
came to be in the corpus. Load-bearing because every prevalence claim inherits
its denominator from this, so an error here propagates into every count in the
document.

## Out of scope

**Method narrative** that makes no factual claim about what the evidence shows.

**Connective prose,** transitions, and labels that only name a section.

**Claims sourced outside the corpus.** Published figures, prior literature,
context supplied from elsewhere. These get the `out-of-corpus` disposition,
rather than a grade. Keeping that
distinct matters: "the corpus does not support this" and "this was never a
corpus claim" look identical in a report with one bucket, and merging them has
the audit flagging correct citations as unsupported findings.

## Deck-specific

In decks the headline is usually the claim and the body is the evidence for it.
Extract slide titles as claims. A title like "The intake process is broken" is
a stronger assertion than anything in the body beneath it and is the thing a
reader will repeat.

Speaker notes are claims too when they assert something. They are also where
hedges live, so a headline that overstates and a note that qualifies is a real
finding: report the pair.

## Anchoring

Every kept claim carries the anchor of the unit it came from, straight through
to the verdict. Without the anchor, the write-back has nowhere to land.

When a claim spans two paragraphs, anchor to the first and say so in the
verdict. When one paragraph holds two separable claims, split them into two
claims sharing an anchor, and give each its own id.

## The inventory the user sees

Show both lists, then stop. The example is synthetic; the columns are not.
Claim id, anchor, type, and the claim as written:

```
CLAIMS TO SWEEP (14)
  C01  [d1]  finding+quantifier  Most operators work around the scheduling tool
  C02  [d2]  corpus composition  We interviewed 11 operators across 4 sites
  C06  [d6]  causal              Rebuild the handoff, because schedulers cannot
                                 see crew status
  ...

DROPPED (23)
  [d0]   heading, labels a section only
  [d9]   method narrative, makes no claim about what the evidence shows
  [d14]  connective prose
  [d18]  out-of-corpus, cites a published industry figure
```

The drop list is not an appendix. It is the only way the user can catch a claim
the triage swallowed, so it goes in front of them at the same moment as the
keep list, before any sweeping happens.
