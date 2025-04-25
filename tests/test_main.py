import pytest
from tagwriting.main import TextManager, FileChangeHandler, ConsoleClient
import os

def test_extract_tag_contents_no_attr():
    text = "<prompt>foobar</prompt>"
    result = TextManager.extract_tag_contents("prompt", text)
    assert result == ("<prompt>foobar</prompt>", "foobar", [], None)

def test_extract_tag_contents_single_attr():
    text = "<prompt:funny>foobar</prompt>"
    result = TextManager.extract_tag_contents("prompt", text)
    assert result == ("<prompt:funny>foobar</prompt>", "foobar", ["funny"], None)

def test_extract_tag_contents_multi_attr():
    text = "<prompt:funny:detail>foobar</prompt>"
    result = TextManager.extract_tag_contents("prompt", text)
    assert result == ("<prompt:funny:detail>foobar</prompt>", "foobar", ["funny", "detail"], None)

def test_extract_tag_contents_other_tag():
    text = "<other>foobar</other>"
    result = TextManager.extract_tag_contents("prompt", text)
    assert result is None

def test_extract_tag_contents_not_found():
    text = "no tag here"
    result = TextManager.extract_tag_contents("prompt", text)
    assert result is None

# TODO: この実装が終わったら対応する
# def test_extract_tag_contents_inner_tag():
#     text = "<prompt>foo <prompt>bar</prompt> baz</prompt>"
#     result = TextManager.extract_tag_contents("prompt", text)
#     assert result == ("<prompt>bar</prompt>", "bar", [], None)

def test_extract_tag_contents_llm_name_and_attrs():
    text = "<prompt(gpt):funny:detail>foobar</prompt>"
    result = TextManager.extract_tag_contents("prompt", text)
    assert result == ("<prompt(gpt):funny:detail>foobar</prompt>", "foobar", ["funny", "detail"], "gpt")

def test_extract_tag_contents_llm_name_only():
    text = "<prompt(gpt)>foobar</prompt>"
    result = TextManager.extract_tag_contents("prompt", text)
    assert result == ("<prompt(gpt)>foobar</prompt>", "foobar", [], "gpt")

def test_safe_text_plain():
    text = "This is a plain response."
    assert TextManager.safe_text(text, "prompt") == "This is a plain response."

def test_safe_text_prompt():
    text = "<prompt>foobar</prompt>"
    assert TextManager.safe_text(text, "prompt") == "foobar"

def test_safe_text_prompt_attr():
    text = "<prompt:funny>foobar</prompt>"
    assert TextManager.safe_text(text, "prompt") == "foobar"

def test_safe_text_prompt_multi_attr():
    text = "<prompt:funny:detail>foobar</prompt>"
    assert TextManager.safe_text(text, "prompt") == "foobar"

def test_safe_text_nested():
    text = "foo <prompt:funny>bar <prompt>baz</prompt> qux</prompt> end"
    assert TextManager.safe_text(text, "prompt") == "foo bar baz qux end"

def test_safe_text_chat():
    text = "<chat>hello chat</chat>"
    assert TextManager.safe_text(text, tag="chat") == "hello chat"

    text_multi = "foo <chat:info:meta>bar</chat> baz"
    assert TextManager.safe_text(text_multi, tag="chat") == "foo bar baz"

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
    prompt = """{wikipedia_resources}
    これはテストです。"""
    sources = [
        ("OpenAI", "OpenAIは人工知能の研究所です。"),
        ("イーロン・マスク", "イーロン・マスクは実業家です。"),
    ]
    result = TextManager.prepend_wikipedia_sources(sources)
    assert result.startswith("## OpenAI\n\nOpenAIは人工知能の研究所です。")
    assert "OpenAI" in result and "イーロン・マスク" in result
    assert result.endswith("\n\nイーロン・マスクは実業家です。\n\n")

    # 2. sourcesが空
    sources = []
    result = TextManager.prepend_wikipedia_sources(sources)
    assert result == ""

def test_replace_include_tags(tmp_path):
    # テスト用ファイルを作成
    include_file = tmp_path / "include_testdata.md"
    include_file.write_text("INCLUDED_CONTENT")
    # <include> タグを含むテキスト
    test_text = f"before <include>{include_file.name}</include> after"
    # 絶対パスでファイルを指定
    result = TextManager.replace_include_tags(str(include_file), test_text)
    assert result == f"before INCLUDED_CONTENT after"

    # ファイルが存在しない場合
    missing_text = "before <include>notfound.md</include> after"
    result = TextManager.replace_include_tags(str(include_file), missing_text)
    # エラー時はNoneを返すので、Noneまたは元テキストのままならOK
    assert result is None or result == missing_text

    # 複数の<include>タグ
    multi_file = tmp_path / "multi.md"
    multi_file.write_text("A")
    test_text = f"<include>{multi_file.name}</include> <include>{include_file.name}</include>"
    result = TextManager.replace_include_tags(str(multi_file), test_text)
    assert result == "A INCLUDED_CONTENT"

def test_build_attrs_rules():
    attrs = ["bullet", "style", "unknown"]
    templates = {
        "attrs": {
            "bullet": ["bullet style", "Markdown style"],
            "style": "plain style"
        }
    }
    # unknownはテンプレートにないため警告が出るが、返り値には含まれない
    expected = " - bullet style\n - Markdown style\n - plain style\n"
    result = TextManager.build_attrs_rules(attrs, templates)
    assert result == expected

def test_attar_and_llm_none():
    assert TextManager.attar_and_llm(None) == ([], None)

def test_attar_and_llm_llm_and_attrs():
    # (gpt):funny:detail -> (['funny', 'detail'], '(gpt)')
    assert TextManager.attar_and_llm('(gpt):funny:detail') == (['funny', 'detail'], 'gpt')

def test_attar_only():
    # funny -> (['funny'], None)
    assert TextManager.attar_and_llm('funny') == (['funny'], None)

def test_attar_and_llm_llm_only():
    # (gpt) -> ([], '(gpt)')
    assert TextManager.attar_and_llm('(gpt)') == ([], 'gpt')

def test_attar_and_llm_attrs_only():
    # funny:detail -> (['funny', 'detail'], None)
    assert TextManager.attar_and_llm('funny:detail') == (['funny', 'detail'], None)

def test_attar_and_llm_empty():
    # '' -> ([], None)
    assert TextManager.attar_and_llm('') == ([], None)

def test_convert_custom_tag_no_change():
    tag = {"tag": "custom"}
    prompt = "foo"
    attrs = ["a1", "a2"]
    llm_name = "gpt"
    result = TextManager.convert_custom_tag(tag, prompt, attrs, llm_name)
    assert result == "<prompt(gpt):a1:a2>foo</prompt>"

def test_convert_custom_tag_prompt_change():
    tag = {"tag": "custom", "change": "prompt"}
    prompt = "bar"
    attrs = []
    llm_name = "gpt"
    result = TextManager.convert_custom_tag(tag, prompt, attrs, llm_name)
    assert result == "<prompt(gpt)>bar</prompt>"

def test_convert_custom_tag_chat_change():
    tag = {"tag": "custom", "change": "chat"}
    prompt = "baz"
    attrs = ["x"]
    llm_name = "llama"
    result = TextManager.convert_custom_tag(tag, prompt, attrs, llm_name)
    assert result == "<chat(llama):x>baz</chat>"

def test_convert_custom_tag_invalid_change():
    tag = {"tag": "custom", "change": "invalid"}
    prompt = "zzz"
    attrs = []
    llm_name = None
    result = TextManager.convert_custom_tag(tag, prompt, attrs, llm_name)
    assert result == "<prompt>zzz</prompt>"

def test_convert_custom_tag_no_attrs():
    tag = {"tag": "custom"}
    prompt = "abc"
    attrs = []
    llm_name = "gpt"
    result = TextManager.convert_custom_tag(tag, prompt, attrs, llm_name)
    assert result == "<prompt(gpt)>abc</prompt>"

def test_convert_custom_tag_no_llm():
    tag = {"tag": "custom"}
    prompt = "def"
    attrs = ["a1"]
    llm_name = None
    result = TextManager.convert_custom_tag(tag, prompt, attrs, llm_name)
    assert result == "<prompt:a1>def</prompt>"