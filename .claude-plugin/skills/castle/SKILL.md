---
name: castle
description: Cognitive Castle — mine projects and conversations into a searchable memory palace. Use when asked about castle, cognitive castle, memory palace, mining memories, searching memories, or palace setup.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Cognitive Castle

A persistent verbatim memory palace for AI — mine projects and conversations, then search them locally with LanceDB. No vector DB to host, no API keys required.

## Prerequisites

Ensure `castle` is installed:

```bash
castle --version
```

If not installed:

```bash
git clone https://github.com/Testimonial/cognitive-castle.git
cd cognitive-castle
pip install -e .
```

## Usage

Cognitive Castle provides dynamic instructions via the CLI. To get instructions for any operation:

```bash
castle instructions <command>
```

Where `<command>` is one of: `help`, `init`, `mine`, `search`, `status`.

Run the appropriate instructions command, then follow the returned instructions step by step.
