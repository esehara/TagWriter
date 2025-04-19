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


class TextManger:
    def __init__(self, filepath):
        self.filepath = os.path.abspath(filepath)

    def extract_tag_contents(self, tag_name):
        """
        指定したタグ名で囲まれた最初の部分のテキストを抽出する。
        例: <prompt>内容</prompt> → "内容"
        """
        pattern = fr'<{tag_name}>(.*?)</{tag_name}>'
        # 全てではない！
        match_tag =  re.search(pattern, self.text, flags=re.DOTALL)
        if match_tag:
            return (match_tag.group(0), match_tag.group(1))
        return None

    def _load_text(self):
        with open(self.filepath, 'r', encoding='utf-8') as f:
            self.text = f.read()

    def _save_text(self):
        with open(self.filepath, 'w', encoding='utf-8') as f:
            f.write(self.text)

    def extract_prompt_tag(self):
        self._load_text()
        result  = self.extract_tag_contents('prompt')
        if result is None:
            return None
        tag, prompt = result
        prompt_text = self.text.replace(tag, "@@processing@@")
# 
        response = ask_ai(f"""
        あなたの回答は`@@processing@@`と置換されます。コンテキストの整合性に合わせてテキストを出力してください。
        Rule:
          - `@@processing@@`は貴方の解答に含めないでください。
          - `<prompt></prompt>`は貴方の解答に含めないでください。
          - 解説や説明を含めず、UserPromptに直接回答してください。
        Context:
        {prompt_text}
        UserPrompt: 
        {prompt}""")

        self.text = self.text.replace(tag, f"{response}")
        self._save_text()
        return (prompt, response)

class ConsoleClient:
    def __init__(self):
        self.console = Console()

    def start(self):
        self.console.rule("[bold blue]Tagwriting CLI[/bold blue]")
        self.console.print("[bold magenta]Hello, Tagwriting CLI![/bold magenta] :sparkles:", justify="center")

    def show_file(self):
        self.console.rule(f"[bold yellow]ファイル更新: {os.path.basename(self.filepath)}[/bold yellow]")
        
    def on_change(self):
        self.show_file()
        result = self.text_manager.extract_prompt_tag()
        if result is not None:
            prompt, response = result
            self.console.print(f"[bold green]Prompt:[/bold green] {prompt}")
            self.console.print(f"[bold green]Response:[/bold green] {response}")

    def inloop(self, filename):
        self.start()
        filepath = os.path.abspath(filename)
        if not os.path.isfile(filepath):
            self.console.print(f"[red]ファイルが存在しません: {filepath}[/red]")
            return
        self.filepath = filepath
        self.text_manager = TextManger(filepath)
        event_handler = FileChangeHandler(filepath, self.on_change)

        observer = Observer()
        observer.schedule(event_handler, path=os.path.dirname(filepath) or '.', recursive=False)
        observer.start()

        self.console.print(f"[green]{filepath} の変更を監視しています。Ctrl+Cで終了します。[/green]", justify="center")
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
    指定したプロンプトをGrok (xAI) APIに送り、応答を返す
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
def main(filename):
    # カレントディレクトリの.envを明示的にロード
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=True)
    client = ConsoleClient()
    client.inloop(filename)


if __name__ == "__main__":
    main()
