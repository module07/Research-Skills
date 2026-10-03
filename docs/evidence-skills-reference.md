# Evidence skills: quick reference

Two skills that keep research writing honest. Both work on any subject matter and any pile of source material (interview transcripts, notes, tickets, documents, reports).

| | **evidence-claim** | **evidence-quote** |
|---|---|---|
| One-line job | Checks whether the **conclusions** in your report are backed by your data | Checks whether the **words in quotation marks** were really said, and says where |
| The thing it looks at | A claim, such as "most users struggled with setup" | A quote, such as "I just gave up on the setup" |
| The question it answers | "Does the evidence carry this sentence?" | "Did this person actually say this, and where?" |
| You give it | A report, deck or findings doc, plus the folder of source material | A question about the source material, or a draft that contains quotes |
| You get back | A verdict on each claim: how many sources back it, how many go against it, how many say nothing | Verified quotes, each with a stamp: who said it, in which file, at what point |
| Can it write into your document? | Yes, as comments, only if you say so | No. It checks and stamps; you place the quotes |

## Why there are two

A quote can be word-for-word real and the sentence built on top of it can still be wrong. One skill checks the words, the other checks the conclusion. A report needs both.

## When to use each

| Your situation | Use |
|---|---|
| "What did people say about pricing?" | evidence-quote (finding quotes) |
| "Is this quote real? Where is it from?" | evidence-quote (verifying) |
| You are about to paste a quote into a slide or document | evidence-quote, first |
| "Does the data back up my report?" | evidence-claim |
| "Did I overstate this finding?" | evidence-claim |
| A deck is about to go to stakeholders | Both: evidence-claim on the conclusions, evidence-quote on the quotes |
| "What did my report leave out?" | Neither. Both only check what is already written (see limits) |

Rule of thumb: **one sentence of yours → evidence-claim. One sentence of theirs → evidence-quote.**

## How they work together

1. **Draft.** When you ask what the source material says, evidence-quote searches it and returns only verified, stamped quotes. It looks for evidence against your idea as well as for it.
2. **Audit.** When the draft is done, evidence-claim picks out the claims that carry the argument, shows you its list (and what it chose to skip), and waits for your corrections before searching.
3. **Hand-off between them.** When evidence-claim needs to show a quote as evidence, it asks evidence-quote to verify and stamp it. If evidence-quote is not installed, it points to the source instead and tells you the quotes were not verified.

## What the output looks like

**evidence-claim** grades every claim:

| Grade | Plain meaning |
|---|---|
| supported | The data backs the claim as worded |
| overstated | Real finding, but the wording claims more than the data shows (for example "most" when it was 2 of 11) |
| understated | The data is stronger than the claim admits |
| contradicted | Something in the data goes against the claim |
| unsupported | Nothing in the data speaks to it either way |
| out-of-corpus | The claim relies on something outside your data (a published figure, a study). Left ungraded |

Each grade comes with three counts, always with the unit named: **support · against · silent**, out of N (participants, documents, tickets). "Silent" means that source never addressed the topic. It is not counted as support or as opposition.

**evidence-quote** gives each quote a stamp:

```
Speaker, file-name @ timestamp
```

If the speaker is a guess, the stamp says so ("likely ... [inferred]"). If the transcript has no timestamps, a line number is used.

## Limits to know

- **Neither skill finds what you left out.** They check what is on the page, not what is missing from it.
- **evidence-claim takes your data as given.** It cannot tell you whether the data was well collected. It also does not fact-check outside sources.
- **Boards and whiteboards** (sticky notes, cards) cannot be read directly. Copy the text into a file and check that.
- **Counts are the skill's reading of your material**, not a script's output. They are shown so you can challenge them.
- **Text inside your source material is never treated as instructions.** If a transcript says "ignore the rules", the skill reports it and moves on.

## Starting points

Say any of these in a session that has the skills installed:

| To use evidence-claim | To use evidence-quote |
|---|---|
| "Check this report against the data" | "Find me quotes about onboarding" |
| "Did I overstate this?" | "Are these quotes real?" |
| "Pressure-test my findings" | "Where does this quote come from?" |
| "Does the data back this up?" | "What did the participants say about X?" |

Both ask before changing anything of yours.
