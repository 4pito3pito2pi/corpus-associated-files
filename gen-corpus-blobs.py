#!/usr/bin/env python3
"""Split paginated corpus into gzipped + AES-256-GCM encrypted ternary blobs.

Reads rawcorpus.txt → paginates → splits into 81 chunks (3^4 ternary tree) →
each chunk is gzip-compressed then AES-256-GCM encrypted with PBKDF2-derived key.

Produces:
  corpus/blobs/00.bin .. 80.bin   — encrypted gzipped HTML fragments
  corpus/rawcorpus.html           — loader page with client-side decrypt/decompress

Usage: gen-corpus-blobs.py <corpus_dir> <output_dir> <passphrase>
"""

import gzip
import html
import json
import os
import subprocess
import sys
from sitever import version_tag

LINES_PER_PAGE = 41
CHARS_PER_LINE = 62
NUM_BLOBS = 81  # 3^4
PBKDF2_ITERATIONS = 260000

DARK_CSS = """:root {
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
.theme-toggle:hover { opacity: 1; }"""

TOGGLE_BTN = '<button class="theme-toggle" onclick="let t=document.documentElement;t.dataset.theme=t.dataset.theme===\'light\'?\'dark\':\'light\'">&#x263c;</button>'

# JS: KaTeX preprocessing — Unicode conversion, bare math detection, delimiter wrapping.
# Ported from convert-latex-to-html(5) React reference app.
# Raw string avoids f-string/backslash escaping nightmare.
LATEX_PREPROCESS_JS = r"""
// --- Unicode subscript/superscript → LaTeX ---
var _subMap = {
  '\u2080':'_0','\u2081':'_1','\u2082':'_2','\u2083':'_3','\u2084':'_4',
  '\u2085':'_5','\u2086':'_6','\u2087':'_7','\u2088':'_8','\u2089':'_9',
  '\u2090':'_a','\u2091':'_e','\u2092':'_o','\u2093':'_x','\u2095':'_h',
  '\u2096':'_k','\u2097':'_l','\u2098':'_m','\u2099':'_n','\u209A':'_p',
  '\u209B':'_s','\u209C':'_t','\u1D62':'_i','\u2C7C':'_j','\u1D63':'_r',
  '\u1D64':'_u','\u1D65':'_v'
};
var _supMap = {
  '\u2070':'^0','\u00B9':'^1','\u00B2':'^2','\u00B3':'^3','\u2074':'^4',
  '\u2075':'^5','\u2076':'^6','\u2077':'^7','\u2078':'^8','\u2079':'^9',
  '\u2071':'^i','\u02B2':'^j','\u207F':'^n','\u1D4F':'^k','\u02E3':'^x'
};

function preprocessLatex(text) {
  // 1. Unicode subscripts/superscripts → LaTeX
  for (var u in _subMap) text = text.split(u).join(_subMap[u]);
  for (var u in _supMap) text = text.split(u).join(_supMap[u]);
  // 2. := → \coloneqq, =: → \eqqcolon
  text = text.replace(/:\s*=(?![a-zA-Z])/g, '\\coloneqq ');
  text = text.replace(/=\s*:(?![a-zA-Z])/g, '\\eqqcolon ');
  // 3. Remove zero-width characters
  text = text.replace(/[\u200B\u200C\u200D\u2060\uFEFF]/g, '');
  return text;
}

// --- Protect existing delimiters, then wrap bare math as display/inline ---
function autoWrapBareMath(text) {
  // Protect already-delimited math from double-wrapping
  var _protected = [];
  function protect(m) {
    var idx = _protected.length;
    _protected.push(m);
    return '\x00PROT' + idx + '\x00';
  }
  text = text.replace(/\$\$[\s\S]*?\$\$/g, protect);
  text = text.replace(/\\\[[\s\S]*?\\\]/g, protect);
  text = text.replace(/\\\([\s\S]*?\\\)/g, protect);
  text = text.replace(/\$[^$\n]*\$/g, protect);

  // Pattern: identifier := \command{...} (with optional Unicode subscripts) → display math
  text = text.replace(
    /([A-Za-z][\w₀-₉ᵢⱼᵣᵤᵥ]*\s*:=\s*)(\\[a-z]+[_{[\s\S]*?)(?=\n|$)/gim,
    function(m, prefix, math) {
      if (math.match(/\\(?:frac|lim|sum|prod|int|mathcal|operatorname)/))
        return '$$' + prefix + math.replace(/\s+$/, '') + '$$';
      return m;
    }
  );

  // Pattern: standalone \lim ... \frac{...}{...}
  text = text.replace(
    /(\\lim\b[\s\S]*?\\frac\s*\{[\s\S]*?\}\s*\{[\s\S]*?\})/gim,
    function(m) {
      return '$$' + m.replace(/\s+$/, '') + '$$';
    }
  );

  // Pattern: standalone \frac{...}{...} not already wrapped
  text = text.replace(
    /(\\frac\s*\{[\s\S]*?\}\s*\{[\s\S]*?\})/gim,
    function(m) {
      return '$$' + m.replace(/\s+$/, '') + '$$';
    }
  );

  // Restore protected blocks
  for (var i = 0; i < _protected.length; i++) {
    text = text.replace('\x00PROT' + i + '\x00', _protected[i]);
  }
  return text;
}

// --- Detect bare LaTeX commands in <pre> and wrap in $ for KaTeX auto-render ---
var MATH_CMDS = 'frac|mathcal|operatorname|otimes|oplus|sqrt|sum|prod|int|oint|Delta|alpha|beta|gamma|theta|sigma|lambda|omega|pi|infty|partial|nabla|cdot|times|approx|equiv|sim|leq|geq|neq|overline|underline|hat|tilde|vec|mathrm|left|right|quad|qquad|arg|max|min|sup|inf|lim|rho|phi|psi|epsilon|zeta|eta|mu|nu|xi|kappa|chi|text|in|notin|subset|supset|subseteq|supseteq|cup|cap|forall|exists|setminus|cong|to|mapsto|Arf|ell|hbar|mathbb|mathbf|boldsymbol|bmod|pmod|log|ln|sin|cos|tan|det|dim|ker|begin|end|coloneqq|eqqcolon|varepsilon';
var _cmdTest = new RegExp('\\\\(?:' + MATH_CMDS + ')(?:[{_^\\\\]|\\b)');
var _exprRe = new RegExp(
  '(\\\\(?:' + MATH_CMDS + ')' +
  '(?:' +
    '\\{[^}]*\\}' +
    '|[_^]\\{[^}]*\\}' +
    '|[_^]\\S' +
    '|\\\\(?:' + MATH_CMDS + '|[;,!| ])' +
    '|[a-zA-Z0-9 +\\-=(){}\\[\\]|:,.]' +
  ')*)', 'g');
function addLatexDelimiters(html) {
  return html.replace(/(<pre>)([\s\S]*?)(<\/pre>)/g, function(m, open, content, close) {
    // 1. Unicode + := preprocessing
    var processed = preprocessLatex(content);
    // 2. Wrap bare multi-expression patterns as display math
    processed = autoWrapBareMath(processed);
    // 3. Wrap remaining bare \commands as inline math
    processed = processed.split('\n').map(function(line) {
      if (/\$/.test(line) || !_cmdTest.test(line)) return line;
      _exprRe.lastIndex = 0;
      return line.replace(_exprRe, function(match) {
        var t = match.replace(/\s+$/, '');
        return t.length >= 4 ? '$' + t + '$' : match;
      });
    }).join('\n');
    return open + processed + close;
  });
}
"""


def _find_safe_break(line, limit):
    """Find a break point at or before limit that doesn't split $...$ math."""
    # Find best space break point
    brk = line.rfind(' ', 0, limit + 1)
    if brk <= 0:
        brk = limit

    # Check if breaking here splits a $...$ block.
    # Count unescaped $ signs before the break point.
    # Odd count means we're inside inline math — push break past the closing $.
    prefix = line[:brk]
    dollar_count = 0
    i = 0
    while i < len(prefix):
        if prefix[i] == '$':
            dollar_count += 1
        elif prefix[i] == '\\' and i + 1 < len(prefix):
            i += 1  # skip escaped char
        i += 1

    if dollar_count % 2 == 1:
        # Inside inline math — find the closing $ and break after it
        close = line.find('$', brk)
        if close >= 0:
            # Break after the closing $ (find next space after it)
            next_space = line.find(' ', close + 1)
            if next_space >= 0:
                return next_space
            return len(line)  # no space — don't break this line
        # No closing $ found — break at the original point (malformed math)
    return brk


def wrap_line(line, chars_per_line, in_display_math=False):
    if not line:
        return ['']
    stripped = line.strip()
    # Never wrap lines inside display math ($$, \[...\], \begin)
    if in_display_math:
        return [line]
    if stripped.startswith('$$') or stripped.endswith('$$'):
        return [line]
    if stripped.startswith('\\begin{') or stripped.startswith('\\end{'):
        return [line]
    if stripped == '\\[' or stripped == '\\]':
        return [line]
    segments = []
    while len(line) > chars_per_line:
        brk = _find_safe_break(line, chars_per_line)
        if brk >= len(line):
            break  # can't break safely — keep whole line
        segments.append(line[:brk])
        line = line[brk:].lstrip(' ')
    if line:
        segments.append(line)
    return segments


def paginate_corpus(corpus_path):
    with open(corpus_path) as f:
        raw_lines = f.readlines()

    pages = []
    current_page = []
    page_num = 1
    in_display_math = False

    for idx, line in enumerate(raw_lines):
        line_text = line.rstrip('\n')
        stripped = line_text.strip()

        # Track \[...\] display math blocks
        if stripped == '\\[':
            in_display_math = True
        elif stripped == '\\]':
            in_display_math = False

        # Track $$...$$ multi-line blocks (opening $$ without closing on same line)
        if stripped.startswith('$$') and not stripped.endswith('$$'):
            in_display_math = True
        elif stripped.endswith('$$') and in_display_math:
            in_display_math = False

        segments = wrap_line(line_text, CHARS_PER_LINE, in_display_math)
        for segment in segments:
            current_page.append(segment)
            if len(current_page) >= LINES_PER_PAGE:
                pages.append(current_page)
                current_page = []
                page_num += 1

    if current_page:
        pages.append(current_page)

    return pages


def render_chunk_html(pages, start_page_num):
    """Render a list of pages as HTML fragment (no <html>/<body> wrapper).

    Lines inside $$...$$ or $...$ math delimiters are NOT html-escaped,
    since html.escape() turns < into &lt; which breaks KaTeX parsing.
    Non-math lines are escaped normally for safety.
    """
    parts = []
    in_display_math = False
    for i, page in enumerate(pages):
        pnum = start_page_num + i
        parts.append(f'<div class="page" id="p{pnum}">')
        parts.append(f'<div class="page-num">p. {pnum}</div>')
        parts.append('<pre>')
        for line in page:
            stripped = line.strip()
            # Track multi-line display math: $$...$$ and \[...\]
            if stripped == '\\[' or (stripped.startswith('$$') and not stripped.endswith('$$')):
                in_display_math = True
                parts.append(line)
            elif (stripped == '\\]' or stripped.endswith('$$')) and in_display_math:
                in_display_math = False
                parts.append(line)
            elif in_display_math:
                parts.append(line)
            elif '$' in line or '\\(' in line or '\\)' in line:
                # Line has inline math — escape only non-math parts
                parts.append(_escape_around_math(line))
            else:
                parts.append(html.escape(line))
        parts.append('</pre>')
        parts.append('</div>')
    return '\n'.join(parts)


def _escape_around_math(line):
    """HTML-escape a line while preserving math delimiters unescaped."""
    import re
    result = []
    pos = 0
    # Match $$...$$, $...$, \(...\) — order matters (longest first)
    for m in re.finditer(r'\$\$.*?\$\$|\$[^$\n]+?\$|\\\(.*?\\\)', line):
        result.append(html.escape(line[pos:m.start()]))
        result.append(m.group())
        pos = m.end()
    result.append(html.escape(line[pos:]))
    return ''.join(result)


def encrypt_blob(data_bytes, passphrase):
    """AES-256-GCM encrypt with PBKDF2-derived key. Returns salt(16) + iv(12) + ciphertext + tag(16)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    salt = os.urandom(16)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                     salt=salt, iterations=PBKDF2_ITERATIONS)
    key = kdf.derive(passphrase.encode('utf-8'))

    iv = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(iv, data_bytes, None)  # ct includes 16-byte tag

    return salt + iv + ct


def gpg_sign(data: bytes) -> str:
    """Detached ASCII-armored GPG signature of data."""
    result = subprocess.run(
        ["gpg", "--batch", "--yes", "--detach-sign", "--armor"],
        input=data, capture_output=True)
    if result.returncode != 0:
        print(f"  GPG sign failed: {result.stderr.decode().strip()}", file=sys.stderr)
        return None
    return result.stdout.decode()


def gpg_fingerprint() -> str:
    """Get first GPG key fingerprint."""
    try:
        r = subprocess.run(["gpg", "--list-keys", "--with-colons"],
                           capture_output=True, text=True)
        for line in r.stdout.splitlines():
            if line.startswith("fpr:"):
                return line.split(":")[9]
    except Exception:
        pass
    return None


def main():
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <corpus_dir> <output_dir> <passphrase>", file=sys.stderr)
        sys.exit(1)

    corpus_dir, output_dir, passphrase = sys.argv[1], sys.argv[2], sys.argv[3]
    blob_dir = os.path.join(output_dir, 'blobs')
    os.makedirs(blob_dir, exist_ok=True)

    corpus_path = os.path.join(corpus_dir, 'rawcorpus.txt')
    print("Paginating corpus...")
    pages = paginate_corpus(corpus_path)
    total_pages = len(pages)
    print(f"  {total_pages} pages")

    # Split into NUM_BLOBS chunks
    chunk_size = (total_pages + NUM_BLOBS - 1) // NUM_BLOBS
    manifest = []
    total_raw = 0
    total_enc = 0

    print(f"Splitting into {NUM_BLOBS} blobs (~{chunk_size} pages each)...")
    for i in range(NUM_BLOBS):
        start = i * chunk_size
        end = min(start + chunk_size, total_pages)
        if start >= total_pages:
            break
        chunk_pages = pages[start:end]
        start_page = start + 1  # 1-indexed

        # Render HTML fragment
        frag = render_chunk_html(chunk_pages, start_page)
        frag_bytes = frag.encode('utf-8')
        total_raw += len(frag_bytes)

        # Gzip compress
        compressed = gzip.compress(frag_bytes, compresslevel=9)

        # Encrypt
        encrypted = encrypt_blob(compressed, passphrase)
        total_enc += len(encrypted)

        # Write blob
        blob_name = f"{i:02d}.bin"
        blob_path = os.path.join(blob_dir, blob_name)
        with open(blob_path, 'wb') as f:
            f.write(encrypted)

        # GPG sign the encrypted blob
        sig = gpg_sign(encrypted)
        sig_name = f"{blob_name}.sig"
        if sig:
            sig_path = os.path.join(blob_dir, sig_name)
            with open(sig_path, 'w') as f:
                f.write(sig)

        manifest.append({
            'id': i,
            'file': f'blobs/{blob_name}',
            'sig': f'blobs/{sig_name}' if sig else None,
            'pages': f'{start_page}-{start_page + len(chunk_pages) - 1}',
            'startPage': start_page,
            'endPage': start_page + len(chunk_pages) - 1,
            'size': len(encrypted),
        })

        if i < 3 or i == NUM_BLOBS - 1:
            ratio = len(compressed) / len(frag_bytes) * 100
            print(f"  blob {i:02d}: pages {start_page}-{start_page+len(chunk_pages)-1}, "
                  f"{len(frag_bytes)//1024}KB -> {len(compressed)//1024}KB gz -> {len(encrypted)//1024}KB enc "
                  f"({ratio:.0f}%)")

    # Write manifest
    fpr = gpg_fingerprint()
    manifest_path = os.path.join(output_dir, 'corpus-manifest.json')
    with open(manifest_path, 'w') as f:
        json.dump({'totalPages': total_pages, 'blobs': manifest,
                   'pbkdf2Iterations': PBKDF2_ITERATIONS,
                   'gpgFingerprint': fpr}, f, indent=2)
    print(f"  Manifest: {manifest_path}")
    if fpr:
        print(f"  GPG fingerprint: {fpr}")

    # Write loader HTML
    write_loader_html(output_dir, total_pages, manifest)

    print(f"\nTotal: {total_raw//1024//1024}MB raw → {total_enc//1024//1024}MB encrypted")
    print("Done.")


def write_loader_html(output_dir, total_pages, manifest):
    """Write the client-side loader/decryptor HTML page."""
    loader_path = os.path.join(output_dir, 'rawcorpus.html')
    manifest_json = json.dumps(manifest)

    with open(loader_path, 'w') as f:
        vtag = version_tag(__file__)
        f.write(f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
{vtag}
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Corpus</title>
<style>{DARK_CSS}
.page {{ margin-bottom: 2rem; padding-bottom: 1rem; border-bottom: 1px solid var(--border); }}
.page-num {{ font-size: .7rem; color: var(--fg2); text-align: right; }}
pre {{ margin: 0; white-space: pre-wrap; word-wrap: break-word;
  font-size: clamp(10px, 1.3vw, 14px); }}
:target {{ background: var(--highlight); }}
#unlock {{ max-width: 400px; margin: 4rem auto; text-align: center; }}
#unlock input {{ font-family: monospace; padding: .5rem; width: 80%;
  background: var(--bg2); border: 1px solid var(--border); color: var(--fg);
  border-radius: 4px; }}
#unlock button {{ margin-top: .5rem; padding: .4rem 1.2rem; cursor: pointer;
  background: var(--bg2); border: 1px solid var(--border); color: var(--fg);
  border-radius: 4px; }}
#status {{ font-size: .8rem; color: var(--fg2); margin: 1rem 0; }}
.blob-loading {{ text-align: center; padding: 2rem; color: var(--fg2); font-size: .8rem; }}
.katex {{ font-size: 1em; }}
.katex-display {{ overflow-x: auto; margin: .25em 0; }}
#nav {{ position: sticky; top: 0; z-index: 999; background: var(--bg);
  border-bottom: 1px solid var(--border); padding: .4rem .5rem;
  display: none; align-items: center; gap: .5rem; flex-wrap: wrap;
  font-size: .75rem; color: var(--fg2); }}
#nav button {{ background: var(--bg2); border: 1px solid var(--border);
  border-radius: 4px; padding: .2rem .6rem; color: var(--fg);
  cursor: pointer; font-family: monospace; font-size: .75rem; }}
#nav button:disabled {{ opacity: .3; cursor: default; }}
#nav input[type=number] {{ width: 5em; font-family: monospace; padding: .2rem .3rem;
  background: var(--bg2); border: 1px solid var(--border); color: var(--fg);
  border-radius: 4px; font-size: .75rem; }}
#nav input[type=number]::-webkit-inner-spin-button {{ -webkit-appearance: none; }}
</style>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css"
  onerror="document.documentElement.dataset.nokatex='1'">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"
  onerror="document.documentElement.dataset.nokatex='1'"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"></script>
</head>
<body>
{TOGGLE_BTN}
<p style="font-size:.8rem;margin-bottom:.5rem"><a href="../">&larr; Back to index</a></p>
<h1 style="text-align:center">Corpus</h1>
<p style="font-size:.8rem;color:var(--fg2);text-align:center">{total_pages:,} pages (A4 simulation, 12pt monospace, {LINES_PER_PAGE} lines/page)</p>

<div id="unlock">
  <p style="font-size:.85rem;color:var(--fg2)">This corpus is encrypted and GPG-signed. Enter the passphrase to view.</p>
  <input type="text" id="passphrase" placeholder="passphrase" autofocus
    onkeydown="if(event.key==='Enter')unlock()">
  <br>
  <button onclick="unlock()">Unlock</button>
  <div id="status"></div>
</div>

<div id="nav">
  <button id="prev-btn" onclick="navBlob(curBlob-1)">&larr; Prev</button>
  <span id="nav-info"></span>
  <button id="next-btn" onclick="navBlob(curBlob+1)">Next &rarr;</button>
  <span>|</span>
  <label>Page <input type="number" id="goto-page" min="1" onkeydown="if(event.key==='Enter')gotoPage(+this.value)"></label>
  <button onclick="gotoPage(+document.getElementById('goto-page').value)">Go</button>
</div>
<div id="corpus" style="display:none"></div>

<script>
const MANIFEST = {manifest_json};
const ITERATIONS = {PBKDF2_ITERATIONS};
const keyCache = new Map();
const blobHTML = new Map();
let curBlob = -1;

{LATEX_PREPROCESS_JS}
// KaTeX rendering — safe fallback: if CDN fails or parse errors, raw text stays
function renderMath(el) {{
  if (document.documentElement.dataset.nokatex || typeof renderMathInElement === 'undefined') return;
  try {{
    renderMathInElement(el, {{
      delimiters: [
        {{ left: '$$', right: '$$', display: true }},
        {{ left: '\\\\[', right: '\\\\]', display: true }},
        {{ left: '$', right: '$', display: false }},
        {{ left: '\\\\(', right: '\\\\)', display: false }}
      ],
      ignoredTags: ['script', 'noscript', 'style', 'textarea', 'code'],
      throwOnError: false,
      trust: true,
      strict: false,
      macros: {{
        '\\\\R': '\\\\mathbb{{R}}',
        '\\\\N': '\\\\mathbb{{N}}',
        '\\\\Z': '\\\\mathbb{{Z}}',
        '\\\\Q': '\\\\mathbb{{Q}}',
        '\\\\C': '\\\\mathbb{{C}}',
        '\\\\F': '\\\\mathbb{{F}}',
        '\\\\P': '\\\\mathbb{{P}}',
        '\\\\E': '\\\\mathbb{{E}}',
        '\\\\eps': '\\\\varepsilon',
        '\\\\veps': '\\\\varepsilon',
        '\\\\1': '\\\\mathbf{{1}}',
        '\\\\id': '\\\\mathrm{{id}}',
        '\\\\op': '\\\\mathrm{{op}}',
        '\\\\Hom': '\\\\mathrm{{Hom}}',
        '\\\\End': '\\\\mathrm{{End}}',
        '\\\\Aut': '\\\\mathrm{{Aut}}',
        '\\\\Spec': '\\\\mathrm{{Spec}}',
        '\\\\Proj': '\\\\mathrm{{Proj}}',
        '\\\\coloneqq': '\\\\mathrel{{\\\\vcenter{{:}}}}=',
        '\\\\eqqcolon': '=\\\\mathrel{{\\\\vcenter{{:}}}}',
        '\\\\d': '\\\\,\\\\mathrm{{d}}',
        '\\\\bigO': '\\\\mathcal{{O}}'
      }}
    }});
  }} catch (e) {{ console.warn('KaTeX render skipped:', e); }}
}}

// 1. Key cache — derive once per unique salt
async function deriveKey(passphrase, salt) {{
  const hex = Array.from(new Uint8Array(salt), b => b.toString(16).padStart(2,'0')).join('');
  if (keyCache.has(hex)) return keyCache.get(hex);
  const enc = new TextEncoder();
  const km = await crypto.subtle.importKey('raw', enc.encode(passphrase), 'PBKDF2', false, ['deriveKey']);
  const key = await crypto.subtle.deriveKey(
    {{ name: 'PBKDF2', salt, iterations: ITERATIONS, hash: 'SHA-256' }},
    km, {{ name: 'AES-GCM', length: 256 }}, false, ['decrypt']);
  keyCache.set(hex, key);
  return key;
}}

async function decryptBlob(encrypted, passphrase) {{
  const salt = encrypted.slice(0, 16);
  const iv = encrypted.slice(16, 28);
  const ct = encrypted.slice(28);
  const key = await deriveKey(passphrase, salt);
  const compressed = await crypto.subtle.decrypt({{ name: 'AES-GCM', iv }}, key, ct);
  const ds = new DecompressionStream('gzip');
  const writer = ds.writable.getWriter();
  writer.write(new Uint8Array(compressed));
  writer.close();
  const reader = ds.readable.getReader();
  const chunks = [];
  while (true) {{
    const {{ done, value }} = await reader.read();
    if (done) break;
    chunks.push(value);
  }}
  const total = chunks.reduce((a, c) => a + c.length, 0);
  const result = new Uint8Array(total);
  let off = 0;
  for (const c of chunks) {{ result.set(c, off); off += c.length; }}
  return new TextDecoder().decode(result);
}}

// --- Blob paging: one blob at a time, no giant scroll height ---
function updateNav() {{
  const blob = MANIFEST[curBlob];
  document.getElementById('nav-info').textContent =
    'Pages ' + blob.startPage + '\\u2013' + blob.endPage + '  (' + (curBlob + 1) + '/' + MANIFEST.length + ')';
  document.getElementById('prev-btn').disabled = curBlob === 0;
  document.getElementById('next-btn').disabled = curBlob === MANIFEST.length - 1;
  document.getElementById('goto-page').max = MANIFEST[MANIFEST.length - 1].endPage;
}}

async function showBlob(idx, scrollToPage) {{
  if (idx < 0 || idx >= MANIFEST.length) return;
  const corpus = document.getElementById('corpus');
  const blob = MANIFEST[idx];
  curBlob = idx;
  updateNav();

  if (blobHTML.has(blob.id)) {{
    corpus.innerHTML = blobHTML.get(blob.id);
    renderMath(corpus);
  }} else {{
    corpus.innerHTML = '<div class="blob-loading">Loading pages ' + blob.pages + '...</div>';
    try {{
      const resp = await fetch(blob.file);
      const encrypted = new Uint8Array(await resp.arrayBuffer());
      const passphrase = sessionStorage.getItem('corpus-pass');
      const html = await decryptBlob(encrypted, passphrase);
      const sig = blob.sig
        ? '<div style="text-align:right;font-size:.65rem;margin-top:.5rem">'
          + '<a href="' + blob.sig + '" style="color:var(--fg2)">GPG signature</a></div>'
        : '';
      const full = addLatexDelimiters(html + sig);
      blobHTML.set(blob.id, full);
      // Keep cache bounded — evict oldest if > 5
      if (blobHTML.size > 5) {{
        const oldest = blobHTML.keys().next().value;
        if (oldest !== blob.id) blobHTML.delete(oldest);
      }}
      corpus.innerHTML = full;
      renderMath(corpus);
    }} catch (e) {{
      corpus.innerHTML = '<div class="blob-loading">Failed to decrypt chunk ' + blob.id + '</div>';
      console.error('Blob ' + blob.id + ':', e);
    }}
  }}

  if (scrollToPage) {{
    setTimeout(function() {{
      var pg = document.getElementById('p' + scrollToPage);
      if (pg) pg.scrollIntoView({{ behavior: 'instant' }});
      else window.scrollTo(0, 0);
    }}, 30);
  }} else {{
    window.scrollTo(0, 0);
  }}
}}

function navBlob(idx) {{ showBlob(idx); }}

function gotoPage(p) {{
  if (!p || p < 1) return;
  var blob = MANIFEST.find(function(b) {{ return p >= b.startPage && p <= b.endPage; }});
  if (blob) {{
    if (blob.id === curBlob) {{
      var pg = document.getElementById('p' + p);
      if (pg) pg.scrollIntoView({{ behavior: 'smooth' }});
    }} else {{
      showBlob(blob.id, p);
    }}
  }}
}}

async function unlock() {{
  const passInput = document.getElementById('passphrase');
  const status = document.getElementById('status');
  const passphrase = passInput.value;
  if (!passphrase) return;

  status.textContent = 'Deriving key...';
  try {{
    const resp = await fetch(MANIFEST[0].file);
    const encrypted = new Uint8Array(await resp.arrayBuffer());
    status.textContent = 'Decrypting...';
    await decryptBlob(encrypted, passphrase);
  }} catch (e) {{
    status.textContent = 'Wrong passphrase.';
    return;
  }}

  sessionStorage.setItem('corpus-pass', passphrase);
  document.getElementById('unlock').style.display = 'none';
  document.getElementById('corpus').style.display = '';
  document.getElementById('nav').style.display = 'flex';

  // Handle #pN deep links
  let targetPage = null;
  if (location.hash) {{
    const match = location.hash.match(/^#p(\\d+)$/);
    if (match) targetPage = parseInt(match[1]);
  }}

  if (targetPage) {{
    const blob = MANIFEST.find(b => targetPage >= b.startPage && targetPage <= b.endPage);
    if (blob) await showBlob(blob.id, targetPage);
    else await showBlob(0);
  }} else {{
    await showBlob(0);
  }}
}}

// Listen for hash changes (index links while already unlocked)
window.addEventListener('hashchange', function() {{
  var m = location.hash.match(/^#p(\\d+)$/);
  if (m) gotoPage(parseInt(m[1]));
}});

// Auto-unlock if passphrase in sessionStorage
(async () => {{
  const saved = sessionStorage.getItem('corpus-pass');
  if (saved) {{
    document.getElementById('passphrase').value = saved;
    await unlock();
  }}
}})();
</script>
</body>
</html>
''')
    print(f"  Loader: {loader_path}")


if __name__ == '__main__':
    main()
