#!/usr/bin/env python3
"""Semantic coherence test for frequency-sorted word list.

Builds word co-occurrence vectors from the raw corpus, then measures
whether frequency-adjacent words have higher cosine similarity than
randomly shuffled pairs.

This tests the hypothesis that words appearing with similar frequency
in a single-author corpus are semantically related — not just
syntactically compatible, but conceptually adjacent.
"""

import re
import sys
import random
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np

CORPUS = Path.home() / "Documents" / "rawcorpus.txt"
FREQFILE = Path.home() / "Documents" / "lexicalfrequency.txt"
OUTFILE = Path.home() / "Documents" / "semantic-embed-results.txt"

# --- Load frequency list (skip header) ---
print("Loading frequency list...")
freq_words = []
with open(FREQFILE) as f:
    for line in f:
        m = re.match(r'"(.+?)"\s+"(\d+)"', line)
        if m and m.group(1) != "*":
            freq_words.append(m.group(1))
print(f"  {len(freq_words)} words")

# --- Build co-occurrence matrix from corpus ---
print("Building co-occurrence vectors from corpus...")
WINDOW = 5  # context window size
MIN_FREQ = 10  # minimum corpus frequency to include

# Read corpus, tokenize
text = Path(CORPUS).read_text(encoding="utf-8")
tokens = re.findall(r"[a-z']+", text.lower())
print(f"  {len(tokens)} tokens in corpus")

# Count word frequencies in corpus
word_counts = Counter(tokens)

# Use freq_words that appear enough in corpus
vocab = [w for w in freq_words if word_counts.get(w, 0) >= MIN_FREQ]
word_to_idx = {w: i for i, w in enumerate(vocab)}
V = len(vocab)
print(f"  {V} vocab words (freq >= {MIN_FREQ})")

# Build co-occurrence counts (sparse, using dicts)
print("  Counting co-occurrences (window={})...".format(WINDOW))
cooccur = defaultdict(Counter)
for i, token in enumerate(tokens):
    if token not in word_to_idx:
        continue
    start = max(0, i - WINDOW)
    end = min(len(tokens), i + WINDOW + 1)
    for j in range(start, end):
        if j == i:
            continue
        neighbor = tokens[j]
        if neighbor in word_to_idx:
            cooccur[token][neighbor] += 1

print(f"  Co-occurrence built for {len(cooccur)} words")

# --- Compute cosine similarity between adjacent freq-list words ---
print("Computing cosine similarities...")

def sparse_cosine(w1, w2):
    """Cosine similarity using sparse co-occurrence vectors."""
    c1 = cooccur.get(w1, {})
    c2 = cooccur.get(w2, {})
    if not c1 or not c2:
        return None
    # Find shared keys
    shared = set(c1.keys()) & set(c2.keys())
    if not shared:
        return 0.0
    dot = sum(c1[k] * c2[k] for k in shared)
    norm1 = sum(v*v for v in c1.values()) ** 0.5
    norm2 = sum(v*v for v in c2.values()) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)

# Filter vocab to words present in freq list ordering
ordered = [w for w in freq_words if w in cooccur]
print(f"  {len(ordered)} words with co-occurrence data in freq order")

# Compute real adjacent similarities
real_sims = []
for i in range(len(ordered) - 1):
    s = sparse_cosine(ordered[i], ordered[i+1])
    if s is not None:
        real_sims.append(s)

real_mean = np.mean(real_sims)
real_median = np.median(real_sims)
print(f"\nReal adjacent similarity: mean={real_mean:.6f}, median={real_median:.6f}")
print(f"  ({len(real_sims)} pairs)")

# Shuffled baselines
N_TRIALS = 200
print(f"Running {N_TRIALS} shuffled trials...")
random.seed(42)
shuffled_means = []
for t in range(N_TRIALS):
    shuf = ordered[:]
    random.shuffle(shuf)
    sims = []
    for i in range(len(shuf) - 1):
        s = sparse_cosine(shuf[i], shuf[i+1])
        if s is not None:
            sims.append(s)
    shuffled_means.append(np.mean(sims))
    if (t+1) % 50 == 0:
        print(f"  trial {t+1}/{N_TRIALS}")

shuf_mean = np.mean(shuffled_means)
shuf_sd = np.std(shuffled_means)
z_score = (real_mean - shuf_mean) / shuf_sd if shuf_sd > 0 else float('inf')

# p-value (one-tailed)
from math import erfc, sqrt
p_value = 0.5 * erfc(z_score / sqrt(2))

print(f"\n{'='*50}")
print(f"RESULTS: Semantic Co-occurrence Coherence Test")
print(f"{'='*50}")
print(f"Real adjacent mean similarity:     {real_mean:.6f}")
print(f"Shuffled mean similarity:          {shuf_mean:.6f}")
print(f"Shuffled StdDev:                   {shuf_sd:.6f}")
print(f"Z-score:                           {z_score:.4f}")
print(f"p-value:                           {p_value:.2e}")
print(f"Ratio (real/shuffled):             {real_mean/shuf_mean:.4f}")
print(f"Pairs tested:                      {len(real_sims)}")
print(f"Shuffled trials:                   {N_TRIALS}")

# Breakdown by frequency band
print(f"\nBy frequency band:")
bands = [
    ("Top 1000 (common)", 0, 1000),
    ("1000-5000 (mid)", 1000, 5000),
    ("5000-10000 (uncommon)", 5000, 10000),
    ("10000+ (rare)", 10000, len(ordered)),
]
band_results = []
for label, lo, hi in bands:
    band = ordered[lo:min(hi, len(ordered))]
    if len(band) < 2:
        continue
    bsims = []
    for i in range(len(band) - 1):
        s = sparse_cosine(band[i], band[i+1])
        if s is not None:
            bsims.append(s)
    if bsims:
        # Shuffled baseline for this band
        shuf_band = []
        for _ in range(100):
            sb = band[:]
            random.shuffle(sb)
            ss = [sparse_cosine(sb[i], sb[i+1]) for i in range(len(sb)-1)]
            ss = [x for x in ss if x is not None]
            if ss:
                shuf_band.append(np.mean(ss))
        sb_mean = np.mean(shuf_band) if shuf_band else 0
        sb_sd = np.std(shuf_band) if shuf_band else 0
        bz = (np.mean(bsims) - sb_mean) / sb_sd if sb_sd > 0 else 0
        print(f"  {label}: real={np.mean(bsims):.6f} shuf={sb_mean:.6f} z={bz:.2f}")
        band_results.append((label, np.mean(bsims), sb_mean, sb_sd, bz))

# Save results
with open(OUTFILE, "w") as f:
    f.write("Semantic Co-occurrence Coherence Test\n")
    f.write("=" * 50 + "\n\n")
    f.write(f"Method: Cosine similarity of co-occurrence vectors (window={WINDOW})\n")
    f.write(f"Corpus: {CORPUS}\n")
    f.write(f"Vocab: {V} words (min freq {MIN_FREQ})\n")
    f.write(f"Pairs: {len(real_sims)}\n")
    f.write(f"Shuffled trials: {N_TRIALS}\n\n")
    f.write(f"Real adjacent mean similarity:  {real_mean:.6f}\n")
    f.write(f"Shuffled mean:                  {shuf_mean:.6f}\n")
    f.write(f"Shuffled SD:                    {shuf_sd:.6f}\n")
    f.write(f"Z-score:                        {z_score:.4f}\n")
    f.write(f"p-value:                        {p_value:.2e}\n")
    f.write(f"Ratio:                          {real_mean/shuf_mean:.4f}\n\n")
    f.write("By frequency band:\n")
    for label, rm, sm, sd, bz in band_results:
        f.write(f"  {label}: real={rm:.6f} shuf={sm:.6f} z={bz:.2f}\n")
    f.write("\nInterpretation:\n")
    f.write("  Z > 2: significant semantic clustering (p < 0.025)\n")
    f.write("  Z > 3: highly significant (p < 0.001)\n")

print(f"\nSaved to {OUTFILE}")
