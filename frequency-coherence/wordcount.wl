text = Import["/home/claude/Documents/rawcorpus.txt", "Text"];
words = ToLowerCase /@ StringSplit[text, Except[LetterCharacter | DigitCharacter | "'"]..];
total = Length[words];
counts = ReverseSort[Counts[words]];
lines = KeyValueMap[
  StringJoin["\"", #1, "\" \"", ToString[#2], "\""] &,
  counts
];
result = StringJoin[
  "\"*\" \"" <> ToString[total] <> "\"\n",
  StringRiffle[lines, "\n"]
];
Export["/home/claude/Documents/frequency.txt", result, "Text"];
Print["Done. " <> ToString[Length[counts]] <> " unique words, " <> ToString[total] <> " total."];
