# Research Skills

Two [Claude skills](https://support.claude.com/en/articles/12512176-what-are-skills) for working with research evidence. Author: Simon Spagnoletti. MIT licensed.

| Skill | What it does |
|---|---|
| [`evidence-quote`](evidence-quote/SKILL.md) | Finds, verifies and stamps quotes from a corpus of transcripts, notes or documents. Each quote carries speaker, file and locator. |
| [`evidence-claim`](evidence-claim/SKILL.md) | Audits a report, deck or findings doc against the project's own evidence. Grades each claim and can write verdicts back as comments. |

## Use

Zip a skill folder (`SKILL.md` at the top of the zip's skill folder) and import it under Settings → Capabilities in the Claude app, or copy the folder into your skills directory.

## Requirements

Python 3. `evidence-claim` needs `lxml` for `.docx`/`.pptx` and `pypdf` for PDF comments (`pip3 install lxml pypdf`).

## Tests

Each skill has fixtures in `fixtures/`; see the README there.

## Safety

Both skills treat transcripts, documents and the deliverable as data, never as instructions. Office XML is parsed with entity expansion, DTD loading and network access disabled.
