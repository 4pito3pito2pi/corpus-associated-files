#!/usr/bin/env python3
"""Strip file separator headers and chat export boilerplate from corpus.txt → rawcorpus.txt"""

import re
from pathlib import Path

corpus = Path.home() / "Documents" / "corpus.txt"
out = Path.home() / "Documents" / "rawcorpus.txt"

text = corpus.read_text(encoding="utf-8")

# Strip separator lines and FILE: headers
text = re.sub(r'^={10,}\n(?:FILE:.*\n={10,}\n)?', '', text, flags=re.MULTILINE)

# Strip common chat export headers
text = re.sub(r'^Google\n', '', text, flags=re.MULTILINE)
text = re.sub(r'^\s*Exported from (?:Gemini|Claude).*\n', '', text, flags=re.MULTILINE)

# Fix missing space after period: "word.Done" → "word. Done"
text = re.sub(r'([a-z])\.([A-Z])', r'\1. \2', text)

# Collapse excessive blank lines
text = re.sub(r'\n{4,}', '\n\n\n', text)
text = text.strip() + '\n'

out.write_text(text, encoding="utf-8")
print(f"Done. {out} ({out.stat().st_size:,} bytes)")
