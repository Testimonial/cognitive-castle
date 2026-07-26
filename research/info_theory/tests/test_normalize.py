from pipeline.normalize import strip_code_blocks, truncate_to_tokens, normalize


def test_strip_code_blocks_removes_fenced_code():
    text = "before\n```python\ndef foo(): pass\n```\nafter"
    assert strip_code_blocks(text) == "before\n\nafter"


def test_strip_code_blocks_handles_no_fences():
    text = "plain prose without code"
    assert strip_code_blocks(text) == "plain prose without code"


def test_strip_code_blocks_handles_multiple_fences():
    text = "x ```a``` y ```b``` z"
    out = strip_code_blocks(text)
    assert "```" not in out
    assert "a" not in out and "b" not in out
    assert "x" in out and "y" in out and "z" in out


def test_truncate_to_tokens_short_text_unchanged():
    short = "five words here is short"
    assert truncate_to_tokens(short, max_tokens=100) == short


def test_truncate_to_tokens_long_text_truncated():
    long = " ".join(["word"] * 5000)
    result = truncate_to_tokens(long, max_tokens=100)
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    assert len(enc.encode(result)) <= 100


def test_normalize_strips_then_truncates():
    text = "prose ```code block``` more prose " + " ".join(["w"] * 3000)
    out = normalize(text, max_tokens=50)
    assert "```" not in out
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    assert len(enc.encode(out)) <= 50


def test_normalize_handles_empty():
    assert normalize("") == ""
    assert normalize("```only code```") == ""
