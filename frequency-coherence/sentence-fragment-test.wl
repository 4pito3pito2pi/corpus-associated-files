(* Sentence fragment test: measure how often consecutive runs of N words
   in the frequency list form parseable English fragments.
   Uses Wolfram's GrammaticalQ or TextStructure for validation.

   Test: for window sizes 3,4,5 — what fraction of consecutive word
   triples/quads/quints are grammatically valid vs shuffled? *)

lines = Rest[Import["/home/claude/Documents/lexicalfrequency.txt", "Lines"]];
words = StringCases[#, "\"" ~~ w__ ~~ "\" \"" ~~ __ ~~ "\"" :> w][[1]] & /@ lines;
Print["Total words: " <> ToString[Length[words]]];

(* Sample 500 positions across the list *)
nSamples = 500;
SeedRandom[123];
samplePositions = Sort[RandomSample[Range[1, Length[words] - 4], nSamples]];

(* Test if a word sequence could be a grammatical fragment *)
isFragment[ws_List] := Module[{phrase, result},
  phrase = StringRiffle[ws, " "];
  result = Quiet[GrammaticalQ[phrase]];
  TrueQ[result]
];

(* Test trigrams *)
Print["\nTesting trigrams at " <> ToString[nSamples] <> " positions..."];
realTrigramHits = Count[
  Table[isFragment[words[[i ;; i + 2]]], {i, samplePositions}],
  True
];
Print["Real trigram hits: " <> ToString[realTrigramHits] <> " / " <> ToString[nSamples]];

(* Shuffled trigram test *)
nTrials = 50;
Print["Running " <> ToString[nTrials] <> " shuffled trials..."];
SeedRandom[42];
shuffledTrigramHits = Table[
  Module[{shuf = RandomSample[words]},
    Count[
      Table[isFragment[shuf[[i ;; i + 2]]], {i, samplePositions}],
      True
    ]
  ],
  {nTrials}
];

shufMean3 = N[Mean[shuffledTrigramHits]];
shufSD3 = N[StandardDeviation[shuffledTrigramHits]];
z3 = If[shufSD3 > 0, N[(realTrigramHits - shufMean3) / shufSD3], "N/A"];

Print["\n========== TRIGRAM RESULTS =========="];
Print["Real: " <> ToString[realTrigramHits] <> " (" <> ToString[N[100. realTrigramHits/nSamples]] <> "%)"];
Print["Shuffled mean: " <> ToString[shufMean3] <> " (" <> ToString[N[100. shufMean3/nSamples]] <> "%)"];
Print["Shuffled SD: " <> ToString[shufSD3]];
Print["Z-score: " <> ToString[z3]];

result = StringJoin[
  "Sentence Fragment Coherence Test\n",
  "================================\n\n",
  "Method: GrammaticalQ on consecutive word windows\n",
  "Sample positions: " <> ToString[nSamples] <> " (of " <> ToString[Length[words]] <> ")\n",
  "Shuffled trials: " <> ToString[nTrials] <> "\n\n",
  "TRIGRAMS (3-word fragments):\n",
  "  Real hits: " <> ToString[realTrigramHits] <> " / " <> ToString[nSamples] <> " (" <> ToString[N[100. realTrigramHits/nSamples]] <> "%)\n",
  "  Shuffled mean: " <> ToString[shufMean3] <> " (" <> ToString[N[100. shufMean3/nSamples]] <> "%)\n",
  "  Shuffled SD: " <> ToString[shufSD3] <> "\n",
  "  Z-score: " <> ToString[z3] <> "\n\n",
  "Interpretation: Z > 3 = highly significant grammatical clustering\n"
];
Export["/home/claude/Documents/sentence-fragment-results.txt", result, "Text"];
Print["\nSaved to sentence-fragment-results.txt"];
