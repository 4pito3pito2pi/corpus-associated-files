#!/usr/bin/env python3
"""Extract plain text from each HTML file in Documents/html/ into Documents/txt/
Preserves Unicode (math symbols, etc). One .txt per .html."""

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
        # Add linebreaks for block elements
        if tag.lower() in ("p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6",
                           "li", "tr", "blockquote", "pre", "hr"):
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        if tag.lower() in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
                           "li", "tr", "blockquote", "pre"):
            self.text.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.text.append(data)

    def handle_entityref(self, name):
        from html import unescape
        if not self._skip:
            self.text.append(unescape(f"&{name};"))

    def handle_charref(self, name):
        if not self._skip:
            try:
                if name.startswith("x"):
                    self.text.append(chr(int(name[1:], 16)))
                else:
                    self.text.append(chr(int(name)))
            except (ValueError, OverflowError):
                pass

    def get_text(self):
        import re
        t = "".join(self.text)
        t = re.sub(r'\n{3,}', '\n\n', t)
        return t.strip()


html_dir = Path.home() / "Documents" / "html"
txt_dir = Path.home() / "Documents" / "txt"
txt_dir.mkdir(exist_ok=True)

files = sorted(html_dir.glob("*.html")) + sorted(html_dir.glob("*.htm"))
print(f"Extracting {len(files)} HTML files to {txt_dir}/")

count = 0
errors = 0
for path in files:
    try:
        html = path.read_text(encoding="utf-8", errors="replace")
        ext = TextExtractor()
        ext.feed(html)
        text = ext.get_text()
        if text:
            out = txt_dir / (path.stem + ".txt")
            out.write_text(text, encoding="utf-8")
            count += 1
        else:
            print(f"  EMPTY: {path.name}", file=sys.stderr)
    except Exception as e:
        print(f"  ERROR: {path.name}: {e}", file=sys.stderr)
        errors += 1

total_size = sum(f.stat().st_size for f in txt_dir.glob("*.txt"))
print(f"Done. {count} files extracted, {errors} errors, {total_size:,} bytes total")
