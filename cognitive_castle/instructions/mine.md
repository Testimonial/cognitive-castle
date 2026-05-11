# Cognitive Castle Mine

When the user invokes this skill, follow these steps:

## 1. Ask what to mine

Ask the user what they want to mine and where the source data is located.
Clarify:
- Is it a project directory (code, docs, notes)?
- Is it conversation exports (Claude, ChatGPT, Slack)?
- Do they want auto-classification (decisions, milestones, problems)?

## 2. Choose the mining mode

There are three mining modes:

### Project mining

    castle mine <dir>

Mines code files, documentation, and notes from a project directory.

### Conversation mining

    castle mine <dir> --mode convos

Mines conversation exports from Claude, ChatGPT, or Slack into the palace.

### General extraction (auto-classify)

    castle mine <dir> --mode convos --extract general

Auto-classifies mined content into decisions, milestones, and problems.

## 3. Optionally split mega-files first

If the source directory contains very large files, suggest splitting them
before mining:

    castle split <dir> [--dry-run]

Use --dry-run first to preview what will be split without making changes.

## 4. Optionally tag with a wing

If the user wants to organize mined content under a specific wing, add the
--wing flag:

    castle mine <dir> --wing <name>

## 5. Show progress and results

Run the selected mining command and display progress as it executes. After
completion, summarize the results including:
- Number of items mined
- Categories or classifications applied
- Any warnings or skipped files

## 6. Suggest next steps

After mining completes, suggest the user try:
- /castle:search -- search the newly mined content
- /castle:status -- check the current state of their palace
- Mine more data from additional sources
