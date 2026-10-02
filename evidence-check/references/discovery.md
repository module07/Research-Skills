# Discovery, the registry, and the manifest

## Why there is a registry

Scope decisions are the thing worth remembering. Where a project's sources
live, which board is the real synthesis board, which folder holds drafts that
must never be cited as evidence, and what a count is counting. Rediscovering
those every run means re-deciding them every run, and a stateless sweep will
happily fold an earlier draft into the corpus and quote it back as
corroboration.

The registry stores locations, exclusions and the unit of analysis. It does not
cache contents, so every run re-reads the sources and re-walks the tree. An
additive corpus needs no maintenance.

## Registry

`<project>/.evidence-check/registry.json`, managed by
`scripts/corpus_inventory.py`. Fields that matter when reading one by hand:

- `unit_of_analysis`, the noun every denominator counts. Set on `init --unit`,
  changed only through `set-unit`. Registries written before this field existed
  read as `sources`.
- `sources[]` with `type` (file, bear, miro, mural, drive, figma, notion, url),
  `kind` (transcript, note, doc, deck, sheet, board, board_export, image, data),
  `locator`, `link`, `status` (present, missing, excluded), `first_seen`,
  `last_seen`.
- `exclusions[]` with `pattern` and, required, `reason`. A pattern with no
  reason is a future mystery.
- `deliverables[]`, the documents under audit. Always excluded from evidence.
- `runs[]`, the last twenty runs, for spotting when the corpus changed shape.

`status: missing` means a file that was registered is gone. It stays in the
registry rather than being deleted, because a source disappearing between runs
is information: a verdict that changed may have changed for that reason.

## What discovery sweeps

Start from the project folder, then widen to connectors.

**Reachable now:** local folders, Bear, Google Drive, and the Miro-shaped board
connector.

**Needs authorizing first:** Figma, Notion, Linear, Asana, Slack, Atlassian.
When one of these is plausibly part of the corpus and is not authorized, put it
in the manifest as a named gap. Do not sweep around it silently.

**Matching signals**, in rough order of reliability: the project folder itself,
an explicit project name, source or participant identifiers that appear in the
deliverable, the date range the evidence covers, and a shared tag. Fuzzy name
matching is the weakest signal, so anything it turns up gets confirmed with the
user before it enters the registry rather than being added on its own.

**Register everything you read.** A source you consulted over MCP and did not
record with `add` is absent from the manifest, and the manifest is the output
people treat as complete.

## First run on a project

1. `init` the registry.
2. `scan` with the deliverable named, so it is excluded from its own evidence.
3. Sweep connectors, propose what you found, and confirm the set with the user.
4. `add` the confirmed connector sources.
5. `exclude` anything that is reachable and is not evidence, with a reason.
6. Propose the unit of analysis from what the corpus turned out to contain, and
   confirm it before any sweeping. A corpus of interviews usually counts
   participants; documents, reports or tickets count themselves; observational
   work may count sites or sessions rather than people. Where the deliverable
   already states a denominator, propose that one and say where it came from.

Drafts, prior projects sharing sources, working notes about the deliverable,
and pilot material deliberately cut are the usual exclusions.

## Every later run

`scan` again, sweep connectors again, then report four things before the
findings: what is in the corpus, what is new since the last run, what is
excluded, and the unit of analysis in force. The exclusion list is printed
every time on purpose. A stale exclusion is invisible otherwise, and an
exclusion made in March can be wrong by June with nothing to prompt a
re-check.

The unit is printed for the same reason. If the corpus has grown into a shape
the stored unit no longer fits, say so and offer `set-unit` rather than
counting in a denominator that has quietly stopped matching the evidence.

## Reading the manifest

The manifest is what makes `unsupported` legible. It reads as "unsupported by
the sources listed here", which is a claim about coverage as much as about
evidence. Put the manifest and the verdicts in the same document so the two are
read together, and repeat any named gap in the header of the findings rather
than leaving it in an appendix.
