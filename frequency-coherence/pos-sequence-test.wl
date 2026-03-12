(* POS sequence test: instead of just bigrams, look for runs of 3+ words
   that follow valid English POS patterns (sentence fragments).

   Approach: tag all words with POS, define fragment patterns,
   scan for runs of length 3-6 that match any pattern. *)

lines = Rest[Import["/home/claude/Documents/lexicalfrequency.txt", "Lines"]];
words = StringCases[#, "\"" ~~ w__ ~~ "\" \"" ~~ __ ~~ "\"" :> w][[1]] & /@ lines;
Print["Words loaded: " <> ToString[Length[words]]];

posMap = <|"Noun" -> "N", "Verb" -> "V", "Adjective" -> "A",
           "Adverb" -> "D", "Preposition" -> "P",
           "Conjunction" -> "C", "Determiner" -> "T",
           "Pronoun" -> "R"|>;

getPOS[w_] := Module[{p},
  p = Quiet[WordData[w, "PartsOfSpeech"]];
  If[!ListQ[p] || Length[p] == 0, "X",
    posMap[First[p]] /. _Missing -> "X"]
];

Print["Tagging POS..."];
tags = getPOS /@ words;
tagStr = StringJoin[tags];
Print["Tagged. Sample: " <> StringTake[tagStr, Min[100, StringLength[tagStr]]]];

(* Define valid English fragment patterns as POS sequences *)
(* These represent common grammatical runs *)
fragmentPatterns = {
  (* 3-word patterns *)
  "TAN",  (* the big house *)
  "NAV",  (* dog runs fast *)
  "NVN",  (* man sees dog *)
  "ANV",  (* big dog runs *)
  "VTN",  (* see the house *)
  "VAN",  (* see big house *)
  "PAN",  (* in big house *)
  "PTN",  (* on the floor *)
  "RVN",  (* he sees things *)
  "RVA",  (* it seems clear *)
  "RVD",  (* we run fast *)
  "NPN",  (* man in house *)
  "DVN",  (* always see things *)
  "NVA",  (* thing seems clear *)
  "CVN",  (* and see things *)
  (* 4-word patterns *)
  "NVPN",  (* man walks in house *)
  "RVAN",  (* we see big things *)
  "TANV",  (* the big dog runs *)
  "NVTN",  (* see the big house *)
  "PTAN",  (* in the big house *)
  "RVPN",  (* he runs to home *)
  "ANVN",  (* big man sees dog *)
  "NVAN",  (* man sees big dog *)
  (* 5-word patterns *)
  "RVTAN",  (* we see the big house *)
  "TANVN",  (* the big dog sees cat *)
  "NVPAN",  (* man walks in big house *)
  "PTANV"   (* in the big house sits *)
};

(* Count pattern matches in a tag sequence *)
countFragments[ts_String] := Module[{count = 0},
  Do[
    count += Length[StringPosition[ts, pat]];,
    {pat, fragmentPatterns}
  ];
  count
];

realCount = countFragments[tagStr];
Print["\nReal fragment matches: " <> ToString[realCount]];

(* Shuffled baseline *)
nTrials = 500;
Print["Running " <> ToString[nTrials] <> " shuffled trials..."];
SeedRandom[42];
shuffledCounts = Table[
  countFragments[StringJoin[RandomSample[tags]]],
  {nTrials}
];

shufMean = N[Mean[shuffledCounts]];
shufSD = N[StandardDeviation[shuffledCounts]];
z = If[shufSD > 0, N[(realCount - shufMean) / shufSD], "N/A"];
pval = If[NumericQ[z], N[1 - CDF[NormalDistribution[], z]], "N/A"];

Print["\n========== RESULTS =========="];
Print["Real fragment count: " <> ToString[realCount]];
Print["Shuffled mean: " <> ToString[shufMean]];
Print["Shuffled SD: " <> ToString[shufSD]];
Print["Z-score: " <> ToString[z]];
Print["p-value: " <> ToString[ScientificForm[pval]]];
Print["Ratio (real/expected): " <> ToString[N[realCount/shufMean, 4]]];

(* Also report which patterns matched in real data *)
Print["\nPattern breakdown (real):"];
Do[
  n = Length[StringPosition[tagStr, pat]];
  If[n > 0, Print["  " <> pat <> ": " <> ToString[n]]];,
  {pat, fragmentPatterns}
];

result = StringJoin[
  "POS Fragment Sequence Test\n",
  "=========================\n\n",
  "Method: Count POS pattern matches (3-5 word grammatical fragments)\n",
  "Patterns tested: " <> ToString[Length[fragmentPatterns]] <> "\n",
  "Shuffled trials: " <> ToString[nTrials] <> "\n\n",
  "Real fragment count: " <> ToString[realCount] <> "\n",
  "Shuffled mean: " <> ToString[shufMean] <> "\n",
  "Shuffled SD: " <> ToString[shufSD] <> "\n",
  "Z-score: " <> ToString[z] <> "\n",
  "p-value: " <> ToString[ScientificForm[pval]] <> "\n",
  "Ratio: " <> ToString[N[realCount/shufMean, 4]] <> "\n\n",
  "Interpretation:\n",
  "  Z > 2: significant (p < 0.025)\n",
  "  Z > 3: highly significant (p < 0.001)\n",
  "  Ratio > 1: more grammatical fragments than chance\n"
];
Export["/home/claude/Documents/pos-sequence-results.txt", result, "Text"];
Print["\nSaved to pos-sequence-results.txt"];
