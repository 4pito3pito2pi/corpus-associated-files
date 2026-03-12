#!/usr/bin/env python3
"""Extract plain text from all HTML files in Documents/html/ into corpus.txt."""

import os
import sys
from html.parser import HTMLParser
from pathlib import Path

SKIP_TAGS = {"script", "style", "head"}

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data):
        if not self._skip:
            self.text.append(data)

    def get_text(self):
        return "".join(self.text)


html_dir = Path.home() / "Documents" / "html"
out_file = Path.home() / "Documents" / "corpus.txt"

files = sorted(html_dir.glob("*.html")) + sorted(html_dir.glob("*.htm"))
print(f"Processing {len(files)} HTML files...")

with open(out_file, "w", encoding="utf-8") as f:
    for path in files:
        try:
            html = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"  SKIP {path.name}: {e}", file=sys.stderr)
            continue
        ext = TextExtractor()
        ext.feed(html)
        text = ext.get_text().strip()
        if text:
            f.write(f"{'=' * 72}\n")
            f.write(f"FILE: {path.name}\n")
            f.write(f"{'=' * 72}\n\n")
            f.write(text)
            f.write("\n\n")

size = out_file.stat().st_size
print(f"Done. {out_file} ({size:,} bytes)")
