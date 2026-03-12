(* Coherence test: do frequency-adjacent words form grammatical bigrams
   more often than chance? *)

(* Load lexical frequency list, skip header *)
lines = Rest[Import["/home/claude/Documents/lexicalfrequency.txt", "Lines"]];
words = StringCases[#, "\"" ~~ w__ ~~ "\" \"" ~~ __ ~~ "\"" :> w][[1]] & /@ lines;
Print["Words loaded: " <> ToString[Length[words]]];

(* Get POS tags — map to simplified categories *)
posMap = <|"Noun" -> "N", "Verb" -> "V", "Adjective" -> "Adj",
           "Adverb" -> "Adv", "Preposition" -> "Prep",
           "Conjunction" -> "Conj", "Determiner" -> "Det",
           "Pronoun" -> "Pro", "Interjection" -> "Int"|>;

getPOS[w_] := Module[{p},
  p = Quiet[WordData[w, "PartsOfSpeech"]];
  If[!ListQ[p] || Length[p] == 0, "X",
    posMap[First[p]] /. _Missing -> "X"]
];

Print["Tagging POS (this takes a while)..."];
tags = getPOS /@ words;
known = Count[tags, Except["X"]];
Print["POS tagged: " <> ToString[known] <> " / " <> ToString[Length[words]]];

(* Valid grammatical bigrams — simplified English transitions *)
validPairs = {
  {"Det", "N"}, {"Det", "Adj"}, {"Adj", "N"}, {"Adj", "Adj"},
  {"N", "V"}, {"N", "N"}, {"N", "Prep"}, {"N", "Conj"},
  {"V", "N"}, {"V", "Adv"}, {"V", "Adj"}, {"V", "Det"},
  {"V", "Prep"}, {"V", "Pro"}, {"V", "V"},
  {"Adv", "V"}, {"Adv", "Adj"}, {"Adv", "Adv"},
  {"Prep", "N"}, {"Prep", "Det"}, {"Prep", "Adj"}, {"Prep", "Pro"},
  {"Pro", "V"}, {"Pro", "N"}, {"Pro", "Adv"},
  {"Conj", "N"}, {"Conj", "V"}, {"Conj", "Det"}, {"Conj", "Adj"}, {"Conj", "Pro"}
};
validSet = Association[# -> True & /@ validPairs];

(* Count valid grammatical bigrams in a tag sequence *)
countValid[t_List] := Count[Partition[t, 2, 1], p_ /; KeyExistsQ[validSet, p]];

(* Real score *)
realScore = countValid[tags];
nPairs = Length[tags] - 1;
Print["\nReal sequence:"];
Print["  Valid bigrams: " <> ToString[realScore] <> " / " <> ToString[nPairs]];
Print["  Rate: " <> ToString[N[100 realScore / nPairs, 4]] <> "%"];

(* Shuffled baselines *)
nTrials = 1000;
Print["\nRunning " <> ToString[nTrials] <> " shuffled trials..."];
SeedRandom[42];
shuffledScores = Table[countValid[RandomSample[tags]], {nTrials}];

meanShuf = N[Mean[shuffledScores]];
sdShuf = N[StandardDeviation[shuffledScores]];
zScore = N[(realScore - meanShuf) / sdShuf];
pValue = N[1 - CDF[NormalDistribution[meanShuf, sdShuf], realScore]];

Print["\nShuffled baseline:"];
Print["  Mean valid bigrams: " <> ToString[meanShuf]];
Print["  StdDev: " <> ToString[sdShuf]];
Print["  Shuffled rate: " <> ToString[N[100 meanShuf / nPairs, 4]] <> "%"];
Print["\nResult:"];
Print["  Z-score: " <> ToString[zScore]];
Print["  p-value: " <> ToString[ScientificForm[pValue]]];
Print["  Real/Expected ratio: " <> ToString[N[realScore / meanShuf, 4]]];

(* Save results *)
result = StringJoin[
  "Coherence Test: Frequency-Adjacent Grammatical Bigrams\n",
  "======================================================\n\n",
  "Words: " <> ToString[Length[words]] <> "\n",
  "POS tagged: " <> ToString[known] <> "\n",
  "Bigram pairs: " <> ToString[nPairs] <> "\n\n",
  "Real sequence valid bigrams: " <> ToString[realScore] <> " (" <> ToString[N[100 realScore/nPairs, 4]] <> "%)\n",
  "Shuffled mean (n=" <> ToString[nTrials] <> "): " <> ToString[meanShuf] <> " (" <> ToString[N[100 meanShuf/nPairs, 4]] <> "%)\n",
  "Shuffled StdDev: " <> ToString[sdShuf] <> "\n",
  "Z-score: " <> ToString[zScore] <> "\n",
  "p-value: " <> ToString[ScientificForm[pValue]] <> "\n",
  "Real/Expected ratio: " <> ToString[N[realScore/meanShuf, 4]] <> "\n"
];
Export["/home/claude/Documents/coherence-results.txt", result, "Text"];
Print["\nSaved to coherence-results.txt"];
