dict = Association[# -> True & /@ DictionaryLookup["*"]];
Print["Dictionary size: " <> ToString[Length[dict]]];

lines = Import["/home/claude/Documents/frequency.txt", "Lines"];
header = First[lines];

out = {header};
kept = 0;
Do[
  parts = StringCases[line, "\"" ~~ w__ ~~ "\" \"" ~~ n__ ~~ "\"" :> {w, n}];
  If[Length[parts] > 0,
    {word, count} = First[parts];
    If[KeyExistsQ[dict, word],
      AppendTo[out, line];
      kept++;
    ];
  ];,
  {line, Rest[lines]}
];

Export["/home/claude/Documents/lexicalfrequency.txt", StringRiffle[out, "\n"], "Text"];
Print["Done. " <> ToString[kept] <> " dictionary words kept."];
