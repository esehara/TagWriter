import fnmatch
import os
import re
import time
import requests
import datetime
import subprocess
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
{context}
UserPrompt:
{prompt}
"""

DEFAULT_HISTORY_TEMPLATE = """
---
Prompt: {prompt}
Result: {result}
Timestamp: {timestamp}

"""

VERBOSE = True

def verbose_print(msg):
    if VERBOSE:
        print(msg)

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
        self.url_catch = {}

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
            with open(abs_path, 'r', encoding='utf-8') as f:
                return f.read()
        try: 
            return re.sub(pattern, replacer, text, flags=re.DOTALL)
        except Exception as e:
            print(f"[include error: {e}]")
            return None

    def replace_url_tags(self, text):
        """
        <url>https://example.com</url> の形式で記述されたタグを、
        指定URLから取得したテキストデータで置換する。

        url tagがerrorを起こした場合:
          - 置換は行わず、元のテキストをそのまま返す
          - エラーはコンソールに出力
        Reason:
          URLはファイルオープンに比べて不確定要素が多すぎるので、
          エラーが起きたとしても処理が続行できるように柔軟性を持たせる。
        
        Catch機能も入れておく:
          - キャッシュで取得済みのURLは再取得せず、キャッシュを返す
        Reason:
          - テキストは何度も短期間で変換されるため、そのたびにURLを取得する必要はない。
          - URL先のテキストは、ローカルテキストの場合に比べて、より頻繁に変換される可能性は低い。
        """
        verbose_print("[debug][Process] Replacing URL tags...")
        pattern = r'<url>(.*?)</url>'
        def replacer(match):
            url = match.group(1).strip()
            verbose_print(f"[debug] URL found: {url}")
            if url in self.url_catch:
                verbose_print(f"[debug] URL cached: {url}")
                return self.url_catch[url]
            else:
                verbose_print(f"[debug] URL not cached: {url}")
                response = requests.get(url, timeout=10)
                response.encoding = response.apparent_encoding
                if response.status_code == 200:
                    # HTMLならタグ除去（簡易）
                    text = response.text
                    if '<html' in text.lower():
                        text = re.sub(r'<[^>]+>', '', text)
                    self.url_catch[url] = text.strip()
                    return text.strip()
                else:
                    print(f"[url error: status_code={response.status_code}]")
                    return ""
        try:
            return re.sub(pattern, replacer, text, flags=re.DOTALL)
        except Exception as e:
            print(f"[url error: {e}]")
            return text

    @classmethod
    def prepend_wikipedia_sources(cls, prompt_text, wikipedia_sources):
        """
        wikipedia_sources: Set[Tuple[str, str or None]]
        
        prompt_textの先頭に、
         ---
         # Sources:
         ## OpenAI
          ...
         ---
        の形で挿入する。
        
        Wikipediaのタグもここで消去する。
        """
        if not wikipedia_sources:
            return prompt_text
        lines = ["---", "# Wikipedia resources:"]
        for title, extract in wikipedia_sources:
            if extract:
                lines.append(f"## {title}\n{extract}")
        header = '\n\n'.join(lines) + '\n\n---\n'
        return header + prompt_text

    def fetch_wikipedia_tags(self, text):
        """
        <wikipedia>記事タイトル</wikipedia> の形式で記述されたタグを全て検出し、
        Wikipedia APIから取得した記事本文と組み合わせたsetを返す。

        Returns:
            Set[Tuple[str, str or None]]: (タイトル, 記事本文 or None) のセット
        """
        verbose_print("[debug][Process] Fetching Wikipedia tags...")
        pattern = r'<wikipedia>(.*?)</wikipedia>'
        titles = set(title.strip() for title in re.findall(pattern, text, flags=re.DOTALL))
        results = set()
        for title in titles:
            cache_key = f"wikipedia:{title}"
            if cache_key in self.url_catch:
                verbose_print(f"[debug] Wikipedia cached: {title}")
                extract = self.url_catch[cache_key]
                results.add((title, extract))
                continue
            try:
                api = "https://ja.wikipedia.org/w/api.php"
                params = {
                    "action": "query",
                    "prop": "extracts",
                    "explaintext": True,
                    "format": "json",
                    "titles": title,
                }
                response = requests.get(api, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    pages = data.get("query", {}).get("pages", {})
                    if not pages:
                        raise Exception("No pages found")
                    page = next(iter(pages.values()))
                    extract = page.get("extract", None)
                    if extract:
                        extract = extract.strip()
                        self.url_catch[cache_key] = extract
                        results.add((title, extract))
                        continue
                    else:
                        continue
                else:
                    continue
            except Exception as e:
                print(f"[wikipedia error: {e}]")
                results.add((title, None))
        return results

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

            # ---- Prompt or Chat ----
            result_kind = None

            result  = TextManager.extract_tag_contents('prompt', self.text)
            if result is not None:
                result_kind = 'prompt'
            else:
                result = TextManager.extract_tag_contents('chat', self.text)
                result_kind = 'chat'            
            # <prompt> or <chat> tag is not found:
            #  -> stop process
            if result is None:
                return None

            tag, prompt, attrs = result
            prompt_text = self.text.replace(tag, "@@processing@@")

            # ---- Include ----
            prompt_text = TextManager.replace_include_tags(self.filepath, prompt_text)
            # Includeエラーが起きたときは一回ストップする
            if prompt_text is None:
                return None
            attrs_rules = self._build_attrs_rules(attrs)

            # ---- URL ----
            prompt_text = self.replace_url_tags(prompt_text)
            # ---- Wikipedia ----
            wikipedia_tags = self.fetch_wikipedia_tags(prompt_text)
            # Wikipedia記事の取得結果を反映
            prompt_text = TextManager.prepend_wikipedia_sources(prompt_text, wikipedia_tags)

            # ---- LLM ----
            if result_kind == 'prompt':
                context = prompt_text
            else:
                # <chat>タグの場合は、全てのコンテキストを除去する
                #   -> @@processing@@をそのまま使用
                context = "@@processing@@"

            response = ask_ai(self.templates["prompt"].format(
                prompt=prompt, context=context, attrs_rules=attrs_rules))

            # responseがNoneのときは、中断
            if response is None:
                return None

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

    def run_shell_command(self, command, params={}):
        """
        任意のシェルコマンドを実行し、結果を表示する
        """
        try:
            result = subprocess.run(command.format(**params), shell=False, capture_output=True, text=True)
            if result.stdout:
                self.console.print(f"[cyan]stdout:[/cyan]\n{result.stdout}")
            if result.stderr:
                self.console.print(f"[red]stderr:[/red]\n{result.stderr}")
            return result.returncode
        except Exception as e:
            self.console.print(f"[red]Command execution failed: {e}[/red]")
            return -1

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
        if "prompt" not in templates:
            templates["prompt"] = DEFAULT_PROMPT           
        if "tags" not in templates:
            templates["tags"] = []
        if "ignore" not in templates:
            templates["ignore"] = []
        if "attrs" not in templates:
            templates["attrs"] = {}
        if "history" not in templates:
            templates["history"] = {
                "file": "{filename}.history.md", 
                "template": DEFAULT_HISTORY_TEMPLATE}
        if "target" not in templates:
            templates["target"] = ["*.txt", "*.md", "*.markdown"]
        if "hook" not in templates:
            templates["hook"] = {}

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

            # "text_generate_end" が存在する場合のみコマンド実行
            if "text_generate_end" in self.templates["hook"]:
                self.run_shell_command(self.templates["hook"]["text_generate_end"],
                    {"filepath": filepath})

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
    verbose_print(f"[yellow]Prompt text: {prompt}[/yellow]")
    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        timeout=20)
    try:
        return completion.choices[0].message.content
    except Exception as e:
        print(f"[red][bold][Error][/bold] AI error: {e}[/red]")
        return None


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
