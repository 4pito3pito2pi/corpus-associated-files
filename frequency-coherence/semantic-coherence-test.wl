(* Semantic coherence test: are frequency-adjacent words more
   semantically related than expected by chance?
   Uses WordData nearest-word relationships *)

lines = Rest[Import["/home/claude/Documents/lexicalfrequency.txt", "Lines"]];
words = StringCases[#, "\"" ~~ w__ ~~ "\" \"" ~~ __ ~~ "\"" :> w][[1]] & /@ lines;

(* Sample windows throughout the list — full 24K is too expensive *)
(* Take 200-word windows at 10 positions across the frequency range *)
windowSize = 30;
nWindows = 40;
step = Floor[Length[words] / nWindows];
positions = Table[i * step, {i, 1, nWindows}];
positions = Select[positions, # + windowSize <= Length[words] &];

Print["Testing " <> ToString[Length[positions]] <> " windows of " <> ToString[windowSize] <> " words"];

(* For each window, measure: how many adjacent pairs share a
   Wolfram "semantic neighbor" relationship *)
(* Use Nearest on WordData embeddings — but simpler: count how many
   adjacent word pairs have overlapping related words *)

getRelated[w_] := Module[{r},
  r = Quiet[WordData[w, "RelatedWords"]];
  If[ListQ[r], r, {}]
];

(* Measure: fraction of adjacent pairs where one word appears in
   the other's related-words list, or they share related words *)
pairScore[w1_, w2_] := Module[{r1, r2},
  r1 = getRelated[w1]; r2 = getRelated[w2];
  If[MemberQ[r1, w2] || MemberQ[r2, w1], 2,
    If[Length[Intersection[r1, r2]] > 0, 1, 0]]
];

(* Score real windows *)
Print["Scoring real adjacency..."];
realScores = Table[
  Module[{win = words[[pos ;; pos + windowSize - 1]], s = 0},
    Do[s += pairScore[win[[j]], win[[j + 1]]], {j, Length[win] - 1}];
    N[s / (Length[win] - 1)]
  ],
  {pos, positions}
];
realMean = Mean[realScores];
Print["Real mean relatedness: " <> ToString[realMean]];

(* Score shuffled windows — shuffle within each window *)
nTrials = 100;
Print["Running " <> ToString[nTrials] <> " shuffled trials..."];
SeedRandom[42];
shuffledMeans = Table[
  Mean[Table[
    Module[{win = RandomSample[words[[pos ;; pos + windowSize - 1]]], s = 0},
      Do[s += pairScore[win[[j]], win[[j + 1]]], {j, Length[win] - 1}];
      N[s / (Length[win] - 1)]
    ],
    {pos, positions}
  ]],
  {nTrials}
];

shufMean = Mean[shuffledMeans];
shufSD = StandardDeviation[shuffledMeans];
z = (realMean - shufMean) / shufSD;

Print["\nResults:"];
Print["  Real mean relatedness: " <> ToString[realMean]];
Print["  Shuffled mean: " <> ToString[shufMean]];
Print["  Shuffled SD: " <> ToString[shufSD]];
Print["  Z-score: " <> ToString[z]];

result = StringJoin[
  "Semantic Coherence Test\n",
  "======================\n\n",
  "Method: WordData RelatedWords overlap between adjacent pairs\n",
  "Windows: " <> ToString[Length[positions]] <> " x " <> ToString[windowSize] <> " words\n",
  "Shuffled trials: " <> ToString[nTrials] <> "\n\n",
  "Real mean relatedness score: " <> ToString[realMean] <> "\n",
  "Shuffled mean: " <> ToString[shufMean] <> "\n",
  "Shuffled SD: " <> ToString[shufSD] <> "\n",
  "Z-score: " <> ToString[z] <> "\n",
  "Interpretation: Z > 2 suggests significant semantic clustering\n"
];
Export["/home/claude/Documents/semantic-coherence-results.txt", result, "Text"];
Print["Saved to semantic-coherence-results.txt"];
