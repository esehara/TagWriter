import click
from rich.console import Console
import readchar
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import time
import os
import re
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
import yaml
import fnmatch

DEFAULT_PROMPT = """
Your response will replace `@@processing@@` within the context. Please output text consistent with the context's integrity.
Rule:
- Do not include `@@processing@@` in your response.
- Answer the UserPrompt directly, without explanations or commentary.
Context:
{prompt_text}
UserPrompt:
{prompt}
"""

class TextManger:
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
          example: <prompt>内容</prompt> → "内容"
        recursive process:
          example: <prompt>summarize: <prompt> Python language </prompt></prompt>
            -> <prompt>Python language</prompt> -> "Python language"
        """
        pattern = fr'<{tag_name}>((?:(?!<{tag_name}>).)*?)</{tag_name}>'
        match_tag =  re.search(pattern, text, flags=re.DOTALL)
        if match_tag:
            # match_tag.group(0) -> tag (<process>foobar</process>)
            # match_tag.group(1) -> inner text (foobar)
            return (match_tag.group(0), match_tag.group(1)) 
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
            result = TextManger.extract_tag_contents(tag['tag'], self.text)
            if result is not None:
                tags, prompt = result
                replace_tags = f"<prompt>{tag['format']}</prompt>".format(prompt=prompt)
                self.text = self.text.replace(tags, replace_tags)
                self._save_text()
                return

    def _load_text(self):
        with open(self.filepath, 'r', encoding='utf-8') as f:
            self.text = f.read()

    def _save_text(self):
        with open(self.filepath, 'w', encoding='utf-8') as f:
            f.write(self.text)

    def _safe_text(self, response):
        """
        LLMのresponseに`<prompt>`タグを含めない
    
        理由: 再起が止まらくなるから。LLMの回答次第では、爆発的に増加する。
          example: `<prompt>Why did I create this product?</prompt>` 
            -> `<prompt>description of this product and usecase</prompt>`
            -> `<prompt>Product Tagwriting example</prompt>`
            ...
        従って: promptにはpromptが含まれず、確実に停止することを保証する。            
        """
        return response.replace("<prompt>", "").replace("</prompt>", "")

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

    def extract_prompt_tag(self):
        self._load_text()
        self._pre_prompt()
        """
        Process:
          -> "<prompt>Why did I create this product?</prompt>" 
          -> "@@processing@@" 
          -> "TagWriting is awesome! (this is AI response)"
        """
        result  = TextManger.extract_tag_contents('prompt', self.text)
        
        #<prompt> tag is not found:
        #  -> stop process
        if result is None:
            return None

        tag, prompt = result
        prompt_text = self.text.replace(tag, "@@processing@@")

        # Prompt 
        prompt_text = TextManger.replace_include_tags(self.filepath, prompt_text)
        response = ask_ai(self.templates["prompt"].format(prompt=prompt, prompt_text=prompt_text))
        response = self._safe_text(response)

        self.text = self.text.replace(tag, f"{response}")
        self._save_text()
        return (prompt, response)


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

        # change absolute path for ignore file
        templates["ignore"] = [os.path.abspath(p) for p in templates["ignore"]]

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
        self.console.rule(f"[bold yellow]ファイル更新: {os.path.basename(filepath)}[/bold yellow]")
        text_manager = TextManger(filepath, self.templates)
        result = text_manager.extract_prompt_tag()
        if result is not None:
            prompt, response = result
            self.console.print(f"[bold green]Prompt:[/bold green] {prompt}")
            self.console.print(f"[bold green]Response:[/bold green] {response}")

    def inloop(self):
        self.console.print(f"[green]Start clients... [/green]", justify="center")
        event_handler = FileChangeHandler(self.dirpath, self.on_change, self.templates["ignore"])
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
    def __init__(self, dirpath, on_change, ignore, debounce_interval=2.0):
        super().__init__()
        self.dirpath = os.path.abspath(dirpath)
        self.on_change = on_change
        self._last_called = 0
        self._debounce_interval = debounce_interval
        self._ignore = ignore

    def _is_debounce(self):
        now = time.time()
        if now - self._last_called > self._debounce_interval:
            self._last_called = now
            return True

    def is_ignored(self, path):
        path = os.path.abspath(path)
        for pattern in self._ignore:
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

    def on_modified(self, event):
        if self.is_ignored(event.src_path):
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
    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}]
    )
    return completion.choices[0].message.content


@click.command()
@click.argument('dirpath')
@click.option('--templates', 'yaml_path', default=None, help='Template yaml file path')
def main(dirpath, yaml_path):
    templates = None
    if yaml_path:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            templates = yaml.safe_load(f)
    client = ConsoleClient()
    client.start(dirpath, templates)


if __name__ == "__main__":
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=True)
    main()
