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
        response = ask_ai(self.templates["prompt"].format(prompt=prompt, prompt_text=prompt_text))

        response = self._safe_text(response)

        self.text = self.text.replace(tag, f"{response}")
        self._save_text()
        return (prompt, response)


class ConsoleClient:
    def __init__(self):
        self.console = Console()

    def start(self, filename, templates):
        self.console.rule("[bold blue]Tagwriting CLI[/bold blue]")
        self.console.print("[bold magenta]Hello, Tagwriting CLI![/bold magenta] :sparkles:", justify="center")
   
        # Default templates param
        if templates is None:
            templates = {
                "prompt": DEFAULT_PROMPT,
                "tags": []
            }
        self.templates = templates

        filepath = os.path.abspath(filename)
        if not os.path.isfile(filepath):
            self.console.print(f"[red]ファイルが存在しません: {filepath}[/red]")
            return
        self.filepath = filepath

        self.text_manager = TextManger(filepath, templates)
        self.inloop()

    def show_file(self):
        self.console.rule(f"[bold yellow]ファイル更新: {os.path.basename(self.filepath)}[/bold yellow]")
        
    def on_change(self):
        self.show_file()
        result = self.text_manager.extract_prompt_tag()
        if result is not None:
            prompt, response = result
            self.console.print(f"[bold green]Prompt:[/bold green] {prompt}")
            self.console.print(f"[bold green]Response:[/bold green] {response}")

    def inloop(self):
        event_handler = FileChangeHandler(self.filepath, self.on_change)

        observer = Observer()
        observer.schedule(event_handler, path=os.path.dirname(self.filepath) or '.', recursive=False)
        observer.start()

        self.console.print(f"[green]{self.filepath} の変更を監視しています。Ctrl+Cで終了します。[/green]", justify="center")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()


class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, filepath, on_change, debounce_interval=2.0):
        super().__init__()
        self.filepath = os.path.abspath(filepath)
        self.on_change = on_change
        self._last_called = 0
        self._debounce_interval = debounce_interval

    def _is_debounce(self):
        now = time.time()
        if now - self._last_called > self._debounce_interval:
            self._last_called = now
            return True

    def on_modified(self, event):
        if os.path.abspath(event.src_path) == self.filepath:
            if self._is_debounce():
                self.on_change()


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
@click.argument('filename')
@click.option('--templates', 'yaml_path', default=None, help='Template yaml file path')
def main(filename, yaml_path):
    templates = None
    if yaml_path:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            templates = yaml.safe_load(f)
    client = ConsoleClient()
    client.start(filename, templates)


if __name__ == "__main__":
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=True)
    main()
