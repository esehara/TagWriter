import fnmatch
import os
import re
import time
import datetime
from pathlib import Path
import yaml
import click
from dotenv import load_dotenv
from openai import OpenAI
from rich.console import Console
from rich import print
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

DEFAULT_PROMPT = """
Your response will replace `@@processing@@` within the context. Please output text consistent with the context's integrity.
Rule:
- Do not include `@@processing@@` in your response.
- Answer the UserPrompt directly, without explanations or commentary.
Rule:
{attrs_rules}
Context:
{prompt_text}
UserPrompt:
{prompt}
"""

VERBOSE = True

class TextManager:
    def __init__(self, filepath, templates):
        """
        filepath: str = "foobar.md"
        templates: list[dict] = [{"tag": "tag_name", "format": "prompt formt"}]
           - example: [{"tag": "summary",  "format": "summarize: {prompt}"}]
        """
        self.filepath = os.path.abspath(filepath)

        if templates is None:
            templates = []
        self.templates = templates

    @classmethod
    def extract_tag_contents(cls, tag_name, text):
        """
        get tag and inner text.
          example: <prompt:funny>内容</prompt>
            -> ("<prompt:funny>内容</prompt>", "内容", ["funny"])
        recursive process:
          example: <prompt>summarize: <prompt> Python language </prompt></prompt>
            -> <prompt>Python language</prompt>
            -> ("<prompt>Python language</prompt>", "Python language", [])
        """
        pattern = fr'<{tag_name}(?::([\w:]+))?>((?:(?!<{tag_name}>).)*?)</{tag_name}>'
        match_tag =  re.search(pattern, text, flags=re.DOTALL)
        if match_tag:
            # match_tag.group(0) -> tag (<process>foobar</process>)
            # match_tag.group(2) -> inner text (foobar)
            attrs = match_tag.group(1).split(':') if match_tag.group(1) else []
            return (match_tag.group(0), match_tag.group(2), attrs) 
        return None

    def _pre_prompt(self):
        """
        Simple replace for tags:
            example: tag = {"tag":"summary", "format":"summarize: {prompt}"}
            "<summary>adabracatabra</summary>" -> "<prompt>summarize: adabracatabra</prompt>"

        First Template Only:
            -> "<summary>adabracatabra</summary> <summary> foobar </summary>"
            -> "<prompt>summarize: adabracatabra</prompt> <summary> foobar </summary>"
        """
        for tag in self.templates["tags"]:
            result = TextManager.extract_tag_contents(tag['tag'], self.text)
            if result is not None:
                tags, prompt, attrs = result
                attrs_text = ":".join(attrs) if attrs else ""
                attrs_text = f":{attrs_text}" if attrs_text != "" else ""
                replace_tags = f"<prompt{attrs_text}>{tag['format']}</prompt>".format(prompt=prompt)
                self.text = self.text.replace(tags, replace_tags)
                self._save_text()
                return

    def _load_text(self):
        with open(self.filepath, 'r', encoding='utf-8') as f:
            self.text = f.read()

    def _save_text(self):
        with open(self.filepath, 'w', encoding='utf-8') as f:
            f.write(self.text)

    @classmethod
    def safe_text(cls, response):
        """
        LLMのresponseに属性付き<prompt>タグも含めない
    
        理由: 再起が止まらくなるから。LLMの回答次第では、爆発的に増加する。
          example: `<prompt>Why did I create this product?</prompt>` 
            -> `<prompt>description of this product and usecase</prompt>`
            -> `<prompt>Product Tagwriting example</prompt>`
            ...
        従って: promptにはpromptが含まれず、確実に停止することを保証する。            
        """
        response = re.sub(r'<prompt(:[\w:]+)?>', '', response)
        response = response.replace('</prompt>', '')
        return response

    @classmethod
    def replace_include_tags(cls, filepath, text):
        """
        <include>filepath.md</include> の形式で記述されたタグを、
        指定ファイルの内容で置換する。
        パスは現在加工しているファイルからの相対パス。
        """
        pattern = r'<include>(.*?)</include>'
        def replacer(match):
            rel_path = match.group(1).strip()
            base_dir = os.path.dirname(filepath)
            abs_path = os.path.abspath(os.path.join(base_dir, rel_path))
            try:
                with open(abs_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                return f"[include error: {e}]"
        return re.sub(pattern, replacer, text, flags=re.DOTALL)

    def _build_attrs_rules(self, attrs):
        rules = ""
        for attr in attrs:
            if attr in self.templates["attrs"]:
                rules += f" - {self.templates['attrs'][attr]}\n"
            else:
                print(f"[red][bold][Warning][/bold] Attribute rule not defined: '{attr}'[/red]")
        return rules

    def extract_prompt_tag(self):
        try:
            self._load_text()
            self._pre_prompt()
            """
            Process:
              -> "<prompt>Do you think this product?</prompt>" 
              -> "@@processing@@" 
              -> "TagWriting is awesome! (this is AI response)"
            """
            result  = TextManager.extract_tag_contents('prompt', self.text)
            #<prompt> tag is not found:
            #  -> stop process
            if result is None:
                return None

            tag, prompt, attrs = result
            prompt_text = self.text.replace(tag, "@@processing@@")
            prompt_text = TextManager.replace_include_tags(self.filepath, prompt_text)
            attrs_rules = self._build_attrs_rules(attrs)
            response = ask_ai(self.templates["prompt"].format(
                prompt=prompt, prompt_text=prompt_text, attrs_rules=attrs_rules))
            response = TextManager.safe_text(response)

            self.text = self.text.replace(tag, f"{response}")
            self._save_text()
            self.append_history(prompt, response)
            return (prompt, response)
        except Exception as e:
            print(f"[red][Error]: {e}")
            return None

    def append_history(self, prompt, result):
        """
        LLMとのやりとり履歴をhistory.file/templatに従って保存する仮実装。
        prompt: プロンプト文字列
        result: LLMの応答
        """
        history_conf = self.templates.get('history', {})

        # ファイル名決定
        base = os.path.splitext(os.path.basename(self.filepath))[0]
        file_tmpl = history_conf.get('file', '{filename}.history.md')
        filename = file_tmpl.replace('{filename}', base)
        filename = os.path.join(os.path.dirname(self.filepath), filename)

        # テンプレート取得
        template = history_conf.get('template', '---\nPrompt: {prompt}\nResult: {result}\nTimestamp: {timestamp}\n---\n')

        # タイムスタンプ
        timestamp = datetime.datetime.now().isoformat()

        # テンプレート埋め込み
        entry = template.format(prompt=prompt, result=result, timestamp=timestamp)

        # 追記
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(entry + '\n')


class ConsoleClient:
    def __init__(self):
        self.console = Console()

    def _build_templates(self, templates):
        """ 
        Default templates param

        prompt: sending to LLM template.
        tags: list of template tags. replace <process> tag.
        ignore: list of files to ignore.
        """
        if templates is None:
            templates = {}

        # if None, set default
        if templates["prompt"] is None:
            templates["prompt"] = DEFAULT_PROMPT           
        if templates["tags"] is None:
            templates["tags"] = []
        if templates["ignore"] is None:
            templates["ignore"] = []
        if templates["attrs"] is None:
            templates["attrs"] = {}
        if templates["target"] is None:
            templates["target"] = []

        # change absolute path for ignore file
        templates["ignore"] = [os.path.abspath(p) for p in templates["ignore"]]
        templates["target"] = [os.path.abspath(p) for p in templates["target"]]

        return templates

    def start(self, dirpath, templates):
        self.console.rule("[bold blue]Tagwriting CLI[/bold blue]")
        self.console.print("[bold magenta]Hello, Tagwriting CLI![/bold magenta] :sparkles:", justify="center")
        
        self.templates = self._build_templates(templates)

        # use absolute path
        dirpath = os.path.abspath(dirpath)

        if not os.path.exists(dirpath):
            self.console.print(f"[red]ディフェクトリが存在しません: {dirpath}[/red]")
            return
        self.dirpath = dirpath
        self.inloop()
        
    def on_change(self, filepath):
        self.console.rule(f"[bold yellow]File changed: {os.path.basename(filepath)}[/bold yellow]")
        text_manager = TextManager(filepath, self.templates)
        result = text_manager.extract_prompt_tag()
        if result is not None:
            prompt, response = result
            self.console.print(f"[bold green]Prompt:[/bold green] {prompt}")
            self.console.print(f"[bold green]Response:[/bold green] {response}")

    def inloop(self):
        self.console.print(f"[green]Start clients... [/green]", justify="center")
        event_handler = FileChangeHandler(self.dirpath, self.on_change, self.templates["ignore"], self.templates["target"])
        observer = Observer()
        observer.schedule(event_handler, path=os.path.dirname(self.dirpath), recursive=True)
        observer.start()
        self.console.print(f"[green]Watching >>> {self.dirpath}[/green]", justify="center")
        self.console.print(f"[blue] exit: Ctrl+C[/blue]", justify="center")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()


class FileChangeHandler(FileSystemEventHandler):
    @classmethod
    def match_patterns(cls, path, patterns):
        """
        任意のファイルリスト(patterns)にpathがマッチするか判定
        - patterns: glob, ディレクトリ、絶対パス対応
        - patternsが空の場合はFalse（is_target/is_ignored側で適宜True/False返す）
        """
        path = os.path.abspath(path)
        for pattern in patterns:
            if pattern.endswith(os.sep) or pattern.endswith('/') or pattern.endswith('\\'):
                dir_pattern = os.path.abspath(pattern.rstrip('/\\'))
                if os.path.commonpath([path, dir_pattern]) == dir_pattern:
                    return True
            elif any(char in pattern for char in '*?[]'):
                if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(os.path.basename(path), pattern):
                    return True
            else:
                file_pattern = os.path.abspath(pattern)
                if path == file_pattern:
                    return True
        return False

    def __init__(self, dirpath, on_change, ignore, target, debounce_interval=2.0):
        super().__init__()
        self.dirpath = os.path.abspath(dirpath)
        self.on_change = on_change
        self._last_called = 0
        self._debounce_interval = debounce_interval
        self._ignore = ignore
        self._target = target

    def _is_debounce(self):
        now = time.time()
        if now - self._last_called > self._debounce_interval:
            self._last_called = now
            return True

    def is_ignored(self, path):
        return self.match_patterns(path, self._ignore)

    def is_target(self, path):
        if not self._target:
            return True
        return self.match_patterns(path, self._target)

    def is_text_file(self, path, blocksize=512):
        try:
            with open(path, 'rb') as f:
                chunk = f.read(blocksize)
            # NULLバイトが含まれていればバイナリファイルとみなす
            if b'\0' in chunk:
                return False
            # ASCII範囲外のバイトが多すぎる場合もバイナリとみなす
            text_characters = bytearray({7,8,9,10,12,13,27} | set(range(0x20, 0x100)))
            nontext = chunk.translate(None, text_characters)
            return float(len(nontext)) / len(chunk) < 0.30 if chunk else False
        except Exception:
            return False

    def on_modified(self, event):
        if self.is_ignored(event.src_path):
            return
        if not self.is_target(event.src_path):
            return
        if not self.is_text_file(event.src_path):
            return
        self.on_change(event.src_path)


def ask_ai(prompt):
    """
    指定したプロンプトを外部のAI APIに送り、応答を返す
    """
    model = os.getenv("MODEL")
    api_key = os.getenv("API_KEY")
    base_url = os.getenv("BASE_URL")
    if not api_key:
        raise RuntimeError("API_KEYが設定されていません。'.env'ファイルまたは環境変数を確認してください。")
    client = OpenAI(api_key=api_key, base_url=base_url)
    if VERBOSE:
        print(f"[yellow]Prompt text: {prompt}[/yellow]")
    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}]
    )
    return completion.choices[0].message.content


@click.command()
@click.argument('dirpath')
@click.option('--templates', 'yaml_path', default=None, help='Template yaml file path')
def main(dirpath, yaml_path):
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=True)
    templates = None
    if yaml_path:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            templates = yaml.safe_load(f)
    client = ConsoleClient()
    client.start(dirpath, templates)


if __name__ == "__main__":
    main()
