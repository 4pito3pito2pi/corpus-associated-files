(* N-gram coherence test: do frequency-adjacent word pairs occur
   together in natural English more than expected by chance?
   Uses Wolfram's WordFrequencyData for bigram-like scoring *)

lines = Rest[Import["/home/claude/Documents/lexicalfrequency.txt", "Lines"]];
words = StringCases[#, "\"" ~~ w__ ~~ "\" \"" ~~ __ ~~ "\"" :> w][[1]] & /@ lines;

(* Sample evenly across the frequency list *)
windowSize = 20;
nWindows = 50;
step = Max[1, Floor[(Length[words] - windowSize) / nWindows]];
positions = Table[1 + i * step, {i, 0, nWindows - 1}];
positions = Select[positions, # + windowSize - 1 <= Length[words] &];
Print["Testing " <> ToString[Length[positions]] <> " windows of " <> ToString[windowSize] <> " words"];

(* Score a pair: log probability that these two words appear adjacent
   in English. Use string search of Wolfram's built-in text resources.
   Simpler approach: measure if words share a WordNet synset or hypernym *)

sameCategory[w1_, w2_] := Module[{c1, c2},
  c1 = Quiet[WordData[w1, "BroaderTerms"]];
  c2 = Quiet[WordData[w2, "BroaderTerms"]];
  If[!ListQ[c1] || !ListQ[c2], 0,
    If[Length[Intersection[c1, c2]] > 0, 1, 0]]
];

Print["Scoring real adjacency (broader-term overlap)..."];
realScores = Table[
  Module[{win = words[[pos ;; pos + windowSize - 1]], s = 0},
    Do[s += sameCategory[win[[j]], win[[j + 1]]], {j, Length[win] - 1}];
    N[s]
  ],
  {pos, positions}
];
realTotal = Total[realScores];
nPairsTotal = Length[positions] * (windowSize - 1);
Print["Real: " <> ToString[realTotal] <> " / " <> ToString[nPairsTotal] <> " pairs share broader terms"];

(* Shuffle test *)
nTrials = 200;
Print["Running " <> ToString[nTrials] <> " shuffled trials..."];
SeedRandom[42];
shuffledTotals = Table[
  Total[Table[
    Module[{win = RandomSample[words[[pos ;; pos + windowSize - 1]]], s = 0},
      Do[s += sameCategory[win[[j]], win[[j + 1]]], {j, Length[win] - 1}];
      N[s]
    ],
    {pos, positions}
  ]],
  {nTrials}
];

shufMean = N[Mean[shuffledTotals]];
shufSD = N[StandardDeviation[shuffledTotals]];
z = If[shufSD > 0, N[(realTotal - shufMean) / shufSD], "N/A"];

Print["\n========== RESULTS =========="];
Print["Real shared-category pairs: " <> ToString[realTotal]];
Print["Shuffled mean: " <> ToString[shufMean]];
Print["Shuffled SD: " <> ToString[shufSD]];
Print["Z-score: " <> ToString[z]];
Print["Real rate: " <> ToString[N[100 realTotal / nPairsTotal]] <> "%"];
Print["Shuffled rate: " <> ToString[N[100 shufMean / nPairsTotal]] <> "%"];

result = StringJoin[
  "N-gram Coherence Test (WordNet Broader Terms)\n",
  "=============================================\n\n",
  "Method: Count adjacent word pairs sharing a WordNet hypernym\n",
  "Windows: " <> ToString[Length[positions]] <> " x " <> ToString[windowSize] <> "\n",
  "Total pairs tested: " <> ToString[nPairsTotal] <> "\n",
  "Shuffled trials: " <> ToString[nTrials] <> "\n\n",
  "Real shared-category pairs: " <> ToString[realTotal] <> " (" <> ToString[N[100 realTotal/nPairsTotal]] <> "%)\n",
  "Shuffled mean: " <> ToString[shufMean] <> " (" <> ToString[N[100 shufMean/nPairsTotal]] <> "%)\n",
  "Shuffled SD: " <> ToString[shufSD] <> "\n",
  "Z-score: " <> ToString[z] <> "\n\n",
  "Interpretation: Z > 2 = significant semantic clustering beyond chance\n"
];
Export["/home/claude/Documents/ngram-coherence-results.txt", result, "Text"];
Print["Saved to ngram-coherence-results.txt"];
