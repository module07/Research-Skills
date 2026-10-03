Fixtures for evidence-quote: golden inputs, trigger phrasings that must fire,
near-misses that must not, and output assertions.

`test_verify_quotes.py` is the build gate. package.sh runs it and treats a
nonzero exit as a build failure. It builds a sample transcript in each supported
format in a tempdir, asserts the parser reads them all into the same IR, then
asserts the matcher accepts every legitimate quote construction and rejects
every distorting one. It ends with a mutation self-test: a quote that verifies
is altered by one word and must then fail, which is what stops a matcher that
returns "pass" for everything from sailing through the rest of the suite.

## Trigger phrasings that must fire

- "check my quotes"
- "are these quotes real"
- "did she actually say that"
- "where does this quote come from"
- "verify this against the transcripts"
- "trace this quote back to the source"
- "does the evidence support this claim"
- "audit the quotes in the findings doc"
- "find me quotes about onboarding" (retrieval)
- "what did participants say about onboarding" (retrieval: the answer is
  built from quotes, so the gate applies)

## Near-misses that must not fire

- "find me a quote for the intro of this blog post" (writing, no corpus)
- "quote me a price for the work" (unrelated sense of quote)
- "clean up these transcripts" (transcript processing, not quoting)
- "check whether this deck's conclusions hold up against the interviews"
  (claims, not quotes: evidence-claim)

## Behaviour worth re-checking by hand after any matcher change

Run the verifier against a real artifact from whichever project is current, not
only against the synthetic fixtures. Two properties show up on real corpora and
not here:

- **Merged voices.** Auto-transcripts often put an interviewer's question and a
  participant's answer in one timestamped block, which is what the attribution
  signals have to survive.
- **Disfluency density.** Real repairs ("It's it's not always") are exactly the
  text a careless matcher normalizes away, and the fixtures are too clean to
  catch that.

Re-check on a corpus whose subject matter is not the one the last change was
written against. The domain-neutrality assertions cover the two known ways
project vocabulary creeps into the signals; they do not prove a third has not
appeared.
