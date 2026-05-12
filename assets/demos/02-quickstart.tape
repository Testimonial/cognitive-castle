Output assets/demos/02-quickstart.gif

Require castle

Set FontFamily "JetBrains Mono"
Set FontSize 12
Set Width 900
Set Height 420
Set Theme "Catppuccin Mocha"
Set TypingSpeed 50ms
Set Padding 20

Type "pip install cognitive-castle"
Enter
Sleep 2s

Type "castle init /tmp/castle-demo-src --palace /tmp/castle-demo-palace --yes"
Enter
Sleep 5s

Type 'castle --palace /tmp/castle-demo-palace search "why did we switch to graphql"'
Enter
Sleep 3s

Type 'castle --palace /tmp/castle-demo-palace search "auth flow" --wing castle-demo-src --room general'
Enter
Sleep 3s
