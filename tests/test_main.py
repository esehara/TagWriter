import pytest
from tagwriting.main import TextManager

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
