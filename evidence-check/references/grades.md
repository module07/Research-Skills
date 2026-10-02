# Grades, counts, and how to decide between them

## The grades

| Grade | Meaning | Decision rule |
| --- | --- | --- |
| `supported` | The corpus carries the claim as written. | Support present, no contradiction, and the claim's strength matches the count. |
| `overstated` | The finding is real, the wording claims more than the evidence carries. | Support present but thinner than the claim's quantifier, scope or certainty. |
| `understated` | The evidence is stronger or broader than the claim admits. | Support materially exceeds what the wording claims. |
| `contradicted` | The corpus carries evidence against the claim. | At least one source directly opposes it. Report alongside any support. |
| `unsupported` | Nothing in the corpus bears on the claim either way. | Sweep returned nothing relevant. Not the same as contradicted. |
| `out-of-corpus` | The claim cites something outside the evidence base. | External figure, published literature, context supplied from elsewhere. Not graded. |

`contradicted` and `overstated` can both apply. When they do, grade
`contradicted` and note the overstatement in the rationale, because a reader
scanning grades needs the more serious one to surface.

Misreadings do not get their own grade. A claim that inverts or distorts what a
source says is `contradicted` when the source opposes it and `overstated` when
the source is thinner than the claim, and the rationale line says what the
misreading was. A separate `misinterpreted` grade would compete with those two
for the same cases without changing the repair.

## Counting

**Count units of analysis, not mentions.** The unit is whatever the registry
holds for this project: participants, documents, tickets, sessions, sites,
respondents. One unit saying the same thing five times counts once. Five units
saying it once counts five.

**Name the unit in the count.** "3 of 11" is unreadable on its own. "3 of 11
participants" and "3 of 11 incident reports" are different claims, and the
denominator is the part a reader checks first.

**Silence is its own count.** Units that never addressed the topic are neither
support nor contradiction. Report them as a third number. A claim with 3
support, 0 disconfirm and 8 silent is a different object from one with 3
support, 0 disconfirm and 0 silent, and collapsing the two is how thin findings
get promoted.

Silence means different things across corpus types, and the difference belongs
in the rationale rather than in the arithmetic. An interviewee who was never
asked is silent for a reason that has nothing to do with the claim; a document
that omits a required field may be silent in a way that carries weight. Count
both as silent, and say which kind it is when it changes the reading.

**Every verdict shows all three counts.** Never a grade alone.

## Quantifier calibration

Rough mapping for prevalence wording against the unit denominator. Treat it as
a prompt for judgment rather than a threshold to apply mechanically, and say
which way you leaned when a case is close.

| Wording | Reasonable support |
| --- | --- |
| all, every, universally | every unit that addressed it, and few silent |
| most, the majority | more than half of those who addressed it |
| many | a substantial minority, roughly a third or more |
| several, a number of | three or more |
| some, a few | two or more |
| one, a single | exactly one, and say so |

The common failure is "most" resting on three of eleven. The finding is real
and the word is wrong, which is `overstated` rather than `unsupported`, and the
fix is one word rather than a cut. Say that in the rationale so the repair
being proposed is explicit.

## Emphasis

`overstated` and `understated` also cover placement. A claim carried by two
passing remarks that runs as the headline is overstated by position even if its
wording is careful. A claim carried by nine units and buried in an appendix
bullet is understated.

Both judgments compare corpus weight against document prominence, and both
sides are estimates. Keep the count visible inside the verdict so the estimate
can be overruled. Never report an emphasis grade without the number that
produced it.

## Verdict shape

The two examples below are synthetic, and their subject matter is arbitrary.
What is not arbitrary is the shape: grade, anchor, the claim as written, all
three counts with the unit named, evidence under its own heading with stamps
and links, then a rationale that says which repair is being proposed.

An interview corpus, unit `participants`:

```
C07  overstated                                    [deck p4, slide title]
     "Most operators work around the scheduling tool"

     support 3 · disconfirm 2 · silent 6 · of 11 participants

     Supporting
       "I just message the supervisor, I don't even open it"
         likely P04 [inferred], session-04.md @ 0:22:11
         file:///path/to/project/transcripts/session-04.md
       "we gave up on it about a year in"
         P07, session-07.md @ 0:31:48
         file:///path/to/project/transcripts/session-07.md

     Disconfirming
       "the scheduler saves me an hour a day"
         P02, session-02.md @ 0:15:30
         file:///path/to/project/transcripts/session-02.md

     Board
       sticky "workaround = only the longer-tenured crews"
         Miro / Synthesis / cluster "Tooling" / sticky 34
         https://miro.com/app/board/<boardId>/?moveToWidget=34

     Rationale
       3 of 11 supports "several", not "most". Two participants describe the
       opposite. The board sticky suggests the split runs by tenure, which the
       claim flattens. Fix is the quantifier, not the finding.
```

A document corpus, unit `reports`. Same shape, different denominator, and the
stamps are page and paragraph locators rather than timestamps:

```
C12  contradicted                                  [report ¶31]
     "No site recorded a manual override after the March change"

     support 0 · disconfirm 2 · silent 14 · of 16 reports

     Disconfirming
       "override applied at 04:12, logged by the duty officer"
         site-09-april.pdf p3
         file:///path/to/project/reports/site-09-april.pdf
       "two manual overrides this period"
         site-14-april.pdf p1
         file:///path/to/project/reports/site-14-april.pdf

     Rationale
       A negative claim, so the sweep looked for the thing denied rather than
       for support. Two reports record exactly it. The 14 silent reports are
       not support: a report that does not mention overrides is not a report
       stating none occurred. Fix is a cut or a scope limit, not a quantifier.
```

Speaker labels in the first example are ids because the example is synthetic.
In a real verdict the stamp carries whatever the source marks, and the
attribution grade, both per `quote-evidence`.

Order the report worst grade first: `contradicted`, `overstated`,
`unsupported`, `understated`, `supported`, `out-of-corpus`. Triage is the
point, so the claims needing work come before the ones that hold.
