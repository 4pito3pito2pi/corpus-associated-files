# corpus-associated-files

Scripts for frequency analysis, coherence testing, and site generation for the corpus published at [unveil-insight.org](https://unveil-insight.org).

## Structure

- `gen-appendix.py` — generates the ternary frequency tree landing page (appendix.html)
- `gen-corpus-blobs.py` — paginates, encrypts (AES-256-GCM), and GPG-signs corpus blobs
- `frequency-coherence/` — analysis and coherence test scripts:
  - `extract-corpus.py` — extract text from HTML chat logs, handle KaTeX dedup
  - `extract-individual.py` — per-conversation extraction
  - `lexfilter.wl` — lexical frequency filter (Mathematica)
  - `wordcount.wl` — word/token counting (Mathematica)
  - `coherence-test.wl` — POS bigram coherence test
  - `ngram-coherence-test.wl` — n-gram WordNet hypernym test
  - `pos-sequence-test.wl` — POS fragment sequence test
  - `semantic-coherence-test.wl` — WordNet relatedness test
  - `semantic-embed-test.py` — co-occurrence vector coherence (Z=27.89, p=1.74e-171)
  - `sentence-fragment-test.wl` — GrammaticalQ window test

## Dependencies

- Python 3, numpy (for semantic-embed-test.py)
- Wolfram Language / Mathematica (for .wl scripts)
- `jq`, `gpg`, `cryptography` Python package (for gen-corpus-blobs.py)

## Related

- Corpus and analysis: [Zenodo DOI 10.5281/zenodo.18977320](https://zenodo.org/records/18977320)
- Site framework: [unveil-static-site](https://github.com/4pito3pito2pi/unveil-static-site)

## License

CC BY-NC 4.0 — Greg Garrison
