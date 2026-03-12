#!/usr/bin/env python3
"""Generate paginated HTML corpus + ternary tree word index appendix.

Reads rawcorpus.txt and lexicalfrequency.txt, produces:
  rawcorpus.html  — corpus with page anchors (A4/12pt simulation)
  appendix.html   — top 81 words as 4-deep ternary tree, links into corpus
                    ordered by frequency (toggle for alphabetic), page refs
                    ranked by adjacency density (top 81 per word)
  ngram-coherence.html — HTMLized analysis results

Usage: gen-appendix.py <corpus_dir> <output_dir>
"""

import html
import json
import os
import re
import sys
from collections import defaultdict

# A4 pagination constants
LINES_PER_PAGE = 41
CHARS_PER_LINE = 62  # monospace at 12pt
MIN_OCCURRENCES = 3
TOP_PAGES_PER_WORD = 81  # top adjacency-dense occurrences

# Function words / stopwords — excluded from appendix so it shows
# where nontrivial semantics start
STOPWORDS = {
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'of', 'to', 'and', 'or', 'not', 'no', 'nor', 'but', 'if', 'so',
    'in', 'on', 'at', 'by', 'for', 'with', 'from', 'as', 'into', 'about',
    'it', 'its', 'this', 'that', 'these', 'those', 'they', 'them', 'their',
    'you', 'your', 'we', 'our', 'me', 'my', 'he', 'she', 'his', 'her',
    'i', 'us', 'who', 'whom', 'which', 'what', 'where', 'when', 'how',
    'why', 'because', 'than', 'then', 'there', 'here',
    'can', 'could', 'would', 'should', 'will', 'shall', 'may', 'might',
    'must', 'do', 'does', 'did', 'has', 'have', 'had',
    'just', 'only', 'also', 'very', 'more', 'most', 'now', 'all', 'any',
    'some', 'each', 'every', 'both', 'few', 'many', 'much', 'own',
    'one', 'two', 'first', 'like', 'want', 'let', 'same', 'between',
    'under', 'over', 'after', 'before', 'up', 'out', 'down',
    'without', 'within', 'through', 'during', 'against',
    'too', 'yet', 'still', 'already', 'even', 'right', 'well',
    'get', 'got', 'make', 'made', 'take', 'took', 'give', 'gave',
    'go', 'went', 'come', 'came', 'know', 'knew', 'see', 'saw',
    'say', 'said', 'think', 'thought', 'tell', 'told',
    'cannot', 're', 'non', 'next', 'new', 'set', 'way', 'use', 'used',
    'need', 'itself', 'about',
}

DARK_CSS = """
:root {
  --bg: #111; --fg: #ccc; --bg2: #1a1a1a; --fg2: #888;
  --border: #222; --link: #7aa2c8; --highlight: #2a2a00;
  --shadow: rgba(0,0,0,.3);
}
[data-theme="light"] {
  --bg: #f5f5f7; --fg: #1a1a1a; --bg2: #fff; --fg2: #555;
  --border: #ddd; --link: #2563eb; --highlight: #ffffcc;
  --shadow: rgba(0,0,0,.08);
}
body {
  font-family: 'Courier New', monospace;
  line-height: 1.4; max-width: 960px;
  margin: 0 auto; padding: 2rem 1.5rem;
  background: var(--bg); color: var(--fg);
}
a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }
.theme-toggle {
  position: fixed; top: 1rem; right: 1rem;
  background: var(--bg2); border: 1px solid var(--border);
  border-radius: 6px; padding: 0.3rem 0.6rem;
  color: var(--fg); cursor: pointer; font-size: 1rem;
  z-index: 1000; opacity: 0.7;
}
.theme-toggle:hover { opacity: 1; }
"""

TOGGLE_BTN = '<button class="theme-toggle" onclick="let t=document.documentElement;t.dataset.theme=t.dataset.theme===\'light\'?\'dark\':\'light\'">&#x263c;</button>'


def wrap_line(line, chars_per_line):
    """Word-wrap a single line at word boundaries within chars_per_line."""
    if not line:
        return ['']
    segments = []
    while len(line) > chars_per_line:
        # Find last space within the limit
        brk = line.rfind(' ', 0, chars_per_line + 1)
        if brk <= 0:
            # No space found — hard break (long unbroken token)
            brk = chars_per_line
        segments.append(line[:brk])
        line = line[brk:].lstrip(' ')
    if line:
        segments.append(line)
    return segments


def wrap_lines(text_lines, chars_per_line):
    """Wrap corpus lines to simulate fixed-width page layout."""
    for idx, line in enumerate(text_lines):
        line = line.rstrip('\n')
        for segment in wrap_line(line, chars_per_line):
            yield (idx, segment)


def paginate_corpus(corpus_path):
    """Read corpus, wrap lines, assign pages. Return (pages, line_to_page, raw_lines)."""
    with open(corpus_path) as f:
        raw_lines = f.readlines()

    pages = []
    line_to_page = {}
    current_page = []
    page_num = 1

    for idx, line in enumerate(raw_lines):
        line_text = line.rstrip('\n')
        if idx not in line_to_page:
            line_to_page[idx] = page_num
        segments = wrap_line(line_text, CHARS_PER_LINE)
        for segment in segments:
            current_page.append(segment)
            if len(current_page) >= LINES_PER_PAGE:
                pages.append(current_page)
                current_page = []
                page_num += 1

    if current_page:
        pages.append(current_page)

    return pages, line_to_page, raw_lines


def find_word_positions(raw_lines, line_to_page, words):
    """For each word, find all (page, line_idx) positions."""
    word_re = {w: re.compile(r'\b' + re.escape(w) + r'\b', re.IGNORECASE) for w in words}
    positions = {w: [] for w in words}

    for line_idx, line in enumerate(raw_lines):
        page = line_to_page.get(line_idx)
        if page is None:
            continue
        for w in words:
            if word_re[w].search(line):
                positions[w].append(page)

    return positions


def score_by_adjacency(page_list, top_n=81):
    """Score each occurrence by local density within a sliding window.

    For each occurrence, count how many other occurrences fall within
    a window of +/- W pages. Select the top_n densest points, then
    deduplicate to spread selections across the corpus.
    """
    if len(page_list) <= top_n:
        return page_list

    pages = sorted(page_list)
    n = len(pages)
    # Window radius: ~1% of corpus span, min 50 pages
    span = pages[-1] - pages[0]
    W = max(50, span // 100)

    # Count neighbors within window for each occurrence (two-pointer)
    density = []
    lo = 0
    hi = 0
    for i, p in enumerate(pages):
        while lo < n and pages[lo] < p - W:
            lo += 1
        while hi < n and pages[hi] <= p + W:
            hi += 1
        count = hi - lo - 1  # exclude self
        density.append((count, p))

    # Sort by density descending, spread picks across corpus
    density.sort(key=lambda x: -x[0])
    selected = set()
    # Minimum gap between selected pages to ensure spread
    min_gap = max(1, span // (top_n * 2))
    for _, p in density:
        if len(selected) >= top_n:
            break
        if any(abs(p - s) < min_gap for s in selected):
            continue
        selected.add(p)

    # If spread constraint was too tight, relax and fill remaining
    if len(selected) < top_n:
        for _, p in density:
            if len(selected) >= top_n:
                break
            selected.add(p)

    return sorted(selected)


def ternary_address(n, depth=4):
    """Convert index 0-80 to ternary address of given depth."""
    digits = []
    for _ in range(depth):
        digits.append(n % 3)
        n //= 3
    return list(reversed(digits))


def build_tree(words_with_data):
    """Build nested ternary tree structure from list of (word, freq, pages)."""
    root = {}
    for i, (word, freq, pages) in enumerate(words_with_data):
        addr = ternary_address(i)
        node = root
        for d in range(len(addr) - 1):
            digit = addr[d]
            if digit not in node:
                node[digit] = {}
            node = node[digit]
        node[addr[-1]] = {'_leaf': (word, freq, pages)}
    return root


def render_tree_html(node, depth=0, path=""):
    """Render tree as nested HTML with <details> for unfolding."""
    parts = []
    for digit in (0, 1, 2):
        if digit not in node:
            continue
        child = node[digit]
        label = f"{path}{digit}"
        if '_leaf' in child:
            word, freq, pages = child['_leaf']
            page_links = compress_pages(pages)
            parts.append(
                f'<div class="leaf" data-word="{html.escape(word)}" '
                f'data-freq="{freq}" style="margin-left:{depth*1.5}rem">'
                f'<span class="node-addr">[{label}]</span> '
                f'<strong>{html.escape(word)}</strong> '
                f'<span class="freq">{freq:,}</span> '
                f'<span class="pg-count">({len(pages)} pp.)</span>'
                f'<div class="page-refs">{page_links}</div>'
                f'</div>\n'
            )
        else:
            leaf_count = count_leaves(child)
            parts.append(
                f'<details style="margin-left:{depth*1.5}rem">'
                f'<summary class="branch">'
                f'<span class="node-addr">[{label}]</span> '
                f'{leaf_count} terms</summary>\n'
                f'{render_tree_html(child, depth + 1, label)}'
                f'</details>\n'
            )
    return ''.join(parts)


def count_leaves(node):
    count = 0
    for digit in (0, 1, 2):
        if digit not in node:
            continue
        child = node[digit]
        if '_leaf' in child:
            count += 1
        else:
            count += count_leaves(child)
    return count


def compress_pages(pages):
    """Generate page reference links, compressing consecutive runs."""
    if not pages:
        return ''
    parts = []
    i = 0
    while i < len(pages):
        start = pages[i]
        end = start
        while i + 1 < len(pages) and pages[i + 1] == end + 1:
            i += 1
            end = pages[i]
        if start == end:
            parts.append(f'<a href="corpus/rawcorpus.html#p{start}">{start}</a>')
        elif end - start <= 2:
            for p in range(start, end + 1):
                parts.append(f'<a href="corpus/rawcorpus.html#p{p}">{p}</a>')
        else:
            parts.append(
                f'<a href="corpus/rawcorpus.html#p{start}">{start}</a>'
                f'\u2013<a href="corpus/rawcorpus.html#p{end}">{end}</a>'
            )
        i += 1
    return ' '.join(parts)


def write_corpus_html(pages, output_path):
    """Write paginated corpus as HTML with page anchors."""
    with open(output_path, 'w') as f:
        f.write(f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Corpus</title>
<style>{DARK_CSS}
.page {{ margin-bottom: 2rem; padding-bottom: 1rem; border-bottom: 1px solid var(--border); }}
.page-num {{ font-size: .7rem; color: var(--fg2); text-align: right; }}
pre {{ margin: 0; white-space: pre-wrap; word-wrap: break-word; font-size: 12px; }}
:target {{ background: var(--highlight); }}
</style>
</head>
<body>
{TOGGLE_BTN}
<h1>Corpus</h1>
<p style="font-size:.8rem;color:var(--fg2)">{len(pages)} pages (A4 simulation, 12pt monospace, {LINES_PER_PAGE} lines/page)</p>
''')
        for i, page in enumerate(pages, 1):
            f.write(f'<div class="page" id="p{i}">\n')
            f.write(f'<div class="page-num">p. {i}</div>\n<pre>')
            for line in page:
                f.write(html.escape(line) + '\n')
            f.write('</pre>\n</div>\n')
        f.write('</body>\n</html>\n')


def render_alpha_list(words_with_data):
    """Render flat alphabetical list (hidden by default, toggled by JS)."""
    alpha = sorted(words_with_data, key=lambda x: x[0].lower())
    parts = []
    for word, freq, pages in alpha:
        page_links = compress_pages(pages)
        parts.append(
            f'<div class="leaf">'
            f'<strong>{html.escape(word)}</strong> '
            f'<span class="freq">{freq:,}</span> '
            f'<span class="pg-count">({len(pages)} pp.)</span>'
            f'<div class="page-refs">{page_links}</div>'
            f'</div>\n'
        )
    return ''.join(parts)


def write_appendix_html(tree, words_with_data, total_pages, output_path):
    """Write ternary tree appendix as HTML with freq/alpha toggle."""
    tree_html = render_tree_html(tree)
    alpha_html = render_alpha_list(words_with_data)
    with open(output_path, 'w') as f:
        f.write(f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Invariant Forms Emerge from Constrained Stochastic Process</title>
<style>{DARK_CSS}
details {{ margin: .3rem 0; }}
summary {{ cursor: pointer; padding: .2rem .4rem; border-radius: 4px; }}
summary:hover {{ background: var(--bg2); }}
.branch {{ font-size: .9rem; }}
.node-addr {{ font-family: monospace; color: var(--fg2); font-size: .75rem; }}
.leaf {{ padding: .2rem .4rem; margin: .2rem 0; }}
.freq {{ font-size: .75rem; color: var(--fg2); font-style: italic; }}
.pg-count {{ font-size: .75rem; color: var(--fg2); }}
.page-refs {{ font-size: .7rem; margin-top: .2rem; line-height: 1.8; }}
.page-refs a {{ margin-right: .3rem; }}
h1 {{ font-size: 1.4rem; border-bottom: 2px solid var(--border); padding-bottom: .5rem; }}
h2 {{ font-size: 1.1rem; color: var(--fg2); margin-top: 2rem; }}
.intro {{ font-size: .85rem; color: var(--fg2); margin-bottom: 1.5rem; line-height: 1.6; }}
.nav {{ margin: 1.5rem 0; padding: 1rem; background: var(--bg2);
  border: 1px solid var(--border); border-radius: 6px; font-size: .85rem; line-height: 1.8; }}
.nav a {{ margin-right: 1.5rem; }}
.view-toggle {{ background: var(--bg2); border: 1px solid var(--border); border-radius: 6px;
  padding: .3rem .8rem; color: var(--fg); cursor: pointer; font-size: .8rem; margin-bottom: 1rem; }}
.view-toggle:hover {{ opacity: .8; }}
#alpha-view {{ display: none; }}
footer {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border);
  font-size: .75rem; color: var(--fg2); line-height: 1.8; }}
</style>
</head>
<body>
{TOGGLE_BTN}
<h1>Invariant Forms Emerge from Constrained Stochastic Process</h1>

<div class="intro">
A corpus of 476 conversations between a human and multiple AI systems, extracted
from HTML chat logs. The conversations were developed through an iterative process
in which multiple AI systems refined human intuitions under noise and constraints
until what persisted fell out naturally. The author does not assert any particular
meaning or conclusion for this corpus beyond that which speaks for itself and
presents the result of an empirical dialectic process as an artifact of general interest.
</div>

<div class="nav">
<a href="corpus/rawcorpus.html">Corpus</a>
<a href="corpus/analysis.html">Analysis</a>
<a href="files/index.html">Conversations</a>
<a href="LICENSE">License</a>
</div>

<h2>Word Index</h2>
<div class="intro">
Top 81 content words by frequency (&ge;{MIN_OCCURRENCES} occurrences, stopwords excluded),
organized as a depth-4 ternary tree (3<sup>4</sup> = 81 leaves).
Each leaf links to the <a href="corpus/rawcorpus.html">corpus</a> ({total_pages:,} pages).
</div>

<button class="view-toggle" onclick="let t=document.getElementById('tree-view'),a=document.getElementById('alpha-view');if(t.style.display==='none'){{t.style.display='';a.style.display='none';this.textContent='A\u2013Z'}}else{{t.style.display='none';a.style.display='';this.textContent='Tree'}}">A\u2013Z</button>
<div id="tree-view">
{tree_html}
</div>
<div id="alpha-view">
{alpha_html}
</div>

<h2>Method</h2>
<div class="intro">
The corpus (939,556 lines, {total_pages:,} paginated pages, 114,231 tokens,
24,587 unique words) was tokenized and analyzed for semantic structure in the
frequency domain.
</div>
<div class="intro">
The primary test (<code>semantic-embed-test.py</code>) builds co-occurrence vectors
from the raw corpus (window=5, vocab &ge;10 occurrences) and measures mean cosine
similarity between frequency-adjacent word pairs vs. 200 shuffled baselines.
</div>
<div class="intro">
<strong>Result:</strong> Z=27.89, p=1.74&times;10<sup>&minus;171</sup>, ratio=1.028.
Words adjacent in the frequency list are semantically closer than chance. The effect
concentrates in mid-frequency and rare words, not in common words where high
co-occurrence is trivially expected:
</div>
<div class="intro" style="font-family:monospace;font-size:.8rem">
Top 1000 (common): Z=&minus;0.08 &middot;
1k&ndash;5k (mid): Z=2.21 &middot;
5k&ndash;10k (uncommon): Z=10.25 &middot;
10k+ (rare): Z=5.63
</div>
<div class="intro">
Secondary tests (POS bigrams Z=0.70, n-gram coherence Z=1.31, POS fragments
Z=&minus;2.42, WordNet overlap indeterminate, GrammaticalQ 0 hits) did not reach
significance. The co-occurrence result stands alone.
</div>

<div class="intro">
<strong>Page references.</strong> For each word, all occurrences are located in the corpus.
A sliding-window density score (neighbors within &plusmn;1&#37; of corpus span) identifies the
most locally concentrated regions. The {TOP_PAGES_PER_WORD} densest pages are selected with
a minimum-gap constraint to ensure coverage across the full corpus.
</div>

<div class="intro">
<strong>Reproducibility.</strong> All scripts are available in the
<a href="https://github.com/4pito3pito2pi/Claude-Winter">repository</a>:
<code>frequency-coherence/</code> (statistical tests),
<code>scripts/gen-appendix.py</code> (this page).
</div>

<footer>
<p>&copy; 2026 Greg Garrison &middot;
<a href="https://creativecommons.org/licenses/by-nc/4.0/">CC BY-NC 4.0</a> &middot;
Contact: admin@unveil-insight.org</p>
<p>Built with <a href="https://github.com/4pito3pito2pi/unveil-static-site">unveil-static-site</a></p>
</footer>
</body>
</html>
''')


def write_ngram_html(corpus_dir, output_path):
    """HTMLize all *-results.txt files into a single analysis page."""
    result_files = sorted(f for f in os.listdir(corpus_dir) if f.endswith('-results.txt'))
    sections = []
    for fname in result_files:
        path = os.path.join(corpus_dir, fname)
        with open(path) as f:
            content = f.read().strip()
        title = fname.replace('-results.txt', '').replace('-', ' ').title()
        sections.append(
            f'<section>\n<h2>{html.escape(title)}</h2>\n'
            f'<pre>{html.escape(content)}</pre>\n</section>\n'
        )

    with open(output_path, 'w') as f:
        f.write(f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Corpus Analysis Results</title>
<style>{DARK_CSS}
section {{ margin: 2rem 0; padding: 1.5rem; background: var(--bg2);
  border-radius: 8px; border: 1px solid var(--border); }}
h1 {{ font-size: 1.4rem; border-bottom: 2px solid var(--border); padding-bottom: .5rem; }}
h2 {{ font-size: 1.1rem; margin-top: 0; color: var(--link); }}
pre {{ white-space: pre-wrap; font-size: .85rem; }}
</style>
</head>
<body>
{TOGGLE_BTN}
<h1>Corpus Analysis Results</h1>
{''.join(sections)}
</body>
</html>
''')
    print(f"  Wrote {output_path} ({len(sections)} sections)")


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <corpus_dir> <output_dir>", file=sys.stderr)
        sys.exit(1)

    corpus_dir, output_dir = sys.argv[1], sys.argv[2]
    os.makedirs(output_dir, exist_ok=True)

    corpus_path = os.path.join(corpus_dir, 'rawcorpus.txt')
    freq_path = os.path.join(corpus_dir, 'lexicalfrequency.txt')

    # Load words with frequencies, skip stopwords, filter >= MIN_OCCURRENCES, take top 81
    all_words = []
    with open(freq_path) as f:
        for line in f:
            parts = line.strip().split('"')
            if len(parts) >= 4:
                w, count = parts[1], int(parts[3])
                if w == '*':
                    continue
                if count < MIN_OCCURRENCES:
                    continue
                if w.lower() in STOPWORDS:
                    continue
                all_words.append((w, count))
                if len(all_words) >= 81:
                    break

    print(f"Top {len(all_words)} words loaded (>={MIN_OCCURRENCES} occurrences): "
          f"{all_words[0][0]}({all_words[0][1]:,})..{all_words[-1][0]}({all_words[-1][1]:,})")

    # Paginate corpus
    print("Paginating corpus...")
    pages, line_to_page, raw_lines = paginate_corpus(corpus_path)
    print(f"  {len(pages)} pages, {len(raw_lines)} source lines")

    # Find all positions for each word
    print("Indexing word positions...")
    words_only = [w for w, _ in all_words]
    positions = find_word_positions(raw_lines, line_to_page, words_only)

    # Score by adjacency density, keep top 81 pages per word
    print("Scoring by adjacency density...")
    words_with_data = []
    for w, freq in all_words:
        all_pages = positions[w]
        top_pages = score_by_adjacency(all_pages, TOP_PAGES_PER_WORD)
        words_with_data.append((w, freq, top_pages))
        if len(words_with_data) <= 5:
            print(f"  '{w}': {len(all_pages)} total pages -> {len(top_pages)} densest")

    # Build ternary tree (frequency order preserved from input)
    tree = build_tree(words_with_data)

    # Write outputs
    corpus_out = os.path.join(output_dir, 'rawcorpus.html')
    appendix_out = os.path.join(output_dir, 'appendix.html')
    analysis_out = os.path.join(output_dir, 'analysis.html')

    print(f"Writing {corpus_out}...")
    write_corpus_html(pages, corpus_out)

    print(f"Writing {appendix_out}...")
    write_appendix_html(tree, words_with_data, len(pages), appendix_out)

    print(f"Writing {analysis_out}...")
    write_ngram_html(corpus_dir, analysis_out)

    print("Done.")


if __name__ == '__main__':
    main()
