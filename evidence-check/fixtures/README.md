# Fixtures

`test_evidence_check.py` runs as a build gate. `package.sh` executes it before
packaging, and a non-zero exit stops the build.

It builds its own inputs in a temp directory: a minimal `.docx` assembled from
raw OOXML (no `python-docx` dependency), a markdown file, a project tree for
the registry, and, when `python-pptx` and `pypdf` are installed, a deck and a
PDF. Nothing is read from outside the temp directory and nothing is left
behind.

What it holds in place:

- **Anchors mean the same thing in both scripts.** `document_ir.py` emits
  `para_index` and `write_comments.py` resolves it. If either side changes its
  counting, the range-marker assertions fail. This is the coupling most likely
  to break silently, since a drifted anchor still writes a comment, just onto
  the wrong paragraph.
- **The deliverable never enters its own evidence base.** Regression here would
  have the audit citing the user's own draft back as corroboration.
- **The unit of analysis persists and can be changed deliberately.** It is set
  on `init`, survives `scan` and `add`, changes only through `set-unit`, and
  falls back to `sources` for a registry written before the field existed. A
  denominator that silently changed between runs would make every changed
  verdict unattributable.
- **Comment writing is additive.** The re-run assertion catches any change that
  would overwrite a colleague's markup instead of appending to it.
- **Refusals stay refusals.** In-place on pptx, formats with no comment layer,
  malformed verdicts, out-of-range anchors.

- **Real Word files survive the write.** The handcrafted docx used elsewhere
  here declares one namespace, so it cannot catch prefix renaming. One test
  builds a document with python-docx, which produces the ~17 prefixes and the
  `mc:Ignorable` attribute a real Word file carries, and asserts both come back
  unchanged. This is the assertion that justifies the lxml dependency.

`lxml` is checked before any test runs, and its absence exits with the install
command rather than a traceback. `python-pptx`, `pypdf` 3+, and `python-docx`
assertions skip with a printed note when absent rather than failing, so the
build still gates on the core path.

Optional formats are covered here only as far as this environment can check
them. LibreOffice neither imports nor exports PowerPoint comments, so no
tooling available here can confirm the pptx output opens correctly in
PowerPoint. See `references/decisions.md`.
