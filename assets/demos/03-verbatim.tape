Output assets/demos/03-verbatim.gif

Require castle

Set FontFamily "JetBrains Mono"
Set FontSize 12
Set Width 900
Set Height 420
Set Theme "Catppuccin Mocha"
Set TypingSpeed 50ms
Set Padding 20

Type "# Mine the Cognitive Castle repo into a palace"
Enter
Sleep 1s

Type "castle mine ~/cognitive-castle --wing castle"
Enter
Sleep 6s

Type "# Search for a real architecture decision"
Enter
Sleep 1s

Type 'castle search "why did we remove ChromaDB"'
Enter
Sleep 5s

Type "# That's the exact text. No summarization."
Sleep 3s
