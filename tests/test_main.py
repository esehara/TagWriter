import pytest
from tagwriting.main import TextManager, FileChangeHandler
import os

def test_extract_tag_contents_no_attr():
    text = "<prompt>foobar</prompt>"
    result = TextManager.extract_tag_contents("prompt", text)
    assert result == ("<prompt>foobar</prompt>", "foobar", [])

def test_extract_tag_contents_single_attr():
    text = "<prompt:funny>foobar</prompt>"
    result = TextManager.extract_tag_contents("prompt", text)
    assert result == ("<prompt:funny>foobar</prompt>", "foobar", ["funny"])

def test_extract_tag_contents_multi_attr():
    text = "<prompt:funny:detail>foobar</prompt>"
    result = TextManager.extract_tag_contents("prompt", text)
    assert result == ("<prompt:funny:detail>foobar</prompt>", "foobar", ["funny", "detail"])

def test_extract_tag_contents_other_tag():
    text = "<other>foobar</other>"
    result = TextManager.extract_tag_contents("prompt", text)
    assert result is None

def test_extract_tag_contents_not_found():
    text = "no tag here"
    result = TextManager.extract_tag_contents("prompt", text)
    assert result is None

def test_extract_tag_contents_inner_tag():
    text = "<prompt>foo <prompt>bar</prompt> baz</prompt>"
    result = TextManager.extract_tag_contents("prompt", text)
    assert result == ("<prompt>bar</prompt>", "bar", [])

def test_safe_text_plain():
    text = "This is a plain response."
    assert TextManager.safe_text(text) == "This is a plain response."

def test_safe_text_prompt():
    text = "<prompt>foobar</prompt>"
    assert TextManager.safe_text(text) == "foobar"

def test_safe_text_prompt_attr():
    text = "<prompt:funny>foobar</prompt>"
    assert TextManager.safe_text(text) == "foobar"

def test_safe_text_prompt_multi_attr():
    text = "<prompt:funny:detail>foobar</prompt>"
    assert TextManager.safe_text(text) == "foobar"

def test_safe_text_nested():
    text = "foo <prompt:funny>bar <prompt>baz</prompt> qux</prompt> end"
    assert TextManager.safe_text(text) == "foo bar baz qux end"

def test_match_patterns_glob():
    # tests/test_main.py should match '*.py'
    path = os.path.abspath(__file__)
    patterns = ['*.py']
    assert FileChangeHandler.match_patterns(path, patterns)
    assert FileChangeHandler.match_patterns(os.path.basename(path), patterns)

def test_match_patterns_exact():
    path = os.path.abspath(__file__)
    patterns = [path]
    assert FileChangeHandler.match_patterns(path, patterns)

def test_match_patterns_directory():
    # Should match if the pattern is the parent directory
    dir_pattern = os.path.dirname(os.path.abspath(__file__)) + os.sep
    path = os.path.abspath(__file__)
    patterns = [dir_pattern]
    assert FileChangeHandler.match_patterns(path, patterns)

def test_match_patterns_no_match():
    path = os.path.abspath(__file__)
    patterns = ['*.md', 'not_a_file.py', '/tmp/']
    assert not FileChangeHandler.match_patterns(path, patterns)

def test_match_patterns_empty():
    path = os.path.abspath(__file__)
    patterns = []
    assert not FileChangeHandler.match_patterns(path, patterns)

def test_prepend_wikipedia_sources():
    # 1. 通常ケース
    prompt = "これはテストです。"
    sources = [
        ("OpenAI", "OpenAIは人工知能の研究所です。"),
        ("イーロン・マスク", "イーロン・マスクは実業家です。"),
    ]
    result = TextManager.prepend_wikipedia_sources(prompt, sources)
    print(result)
    assert result.startswith("---\n\n# Sources:\n\n")
    assert "OpenAI" in result and "イーロン・マスク" in result
    assert result.endswith(prompt)

    # 2. sourcesが空
    sources = []
    result = TextManager.prepend_wikipedia_sources(prompt, sources)
    assert result == prompt