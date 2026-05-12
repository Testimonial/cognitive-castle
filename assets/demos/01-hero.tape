Output assets/demos/01-hero.gif

Require castle

Set FontFamily "JetBrains Mono"
Set FontSize 14
Set Width 1200
Set Height 640
Set Theme "Catppuccin Mocha"
Set TypingSpeed 50ms
Set Padding 20
Set Margin 0
Set Shell "bash"

Type "# Cognitive Castle — local-first AI memory"
Sleep 1.5s
Enter
Sleep 1s

Type "pip install cognitive-castle"
Enter
Sleep 2s

Type "castle init /tmp/castle-demo-src --palace /tmp/castle-demo-palace --yes"
Enter
Sleep 6s

Type "castle mine ~/.claude/projects --mode convos"
Enter
Sleep 4s

Type "castle status"
Enter
Sleep 3s

Type 'castle search "3-stage retrieval pipeline"'
Enter
Sleep 4s

Type "castle wake-up --wing castle"
Enter
Sleep 3s

Type "# No API key. Nothing left your laptop."
Sleep 3s
