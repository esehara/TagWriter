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
from rich.console import Console
from rich import print
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from bs4 import BeautifulSoup
import importlib.metadata

DEFAULT_PROMPT = """
Your response will replace `@@processing@@` within the context. 
Please output text consistent with the context's integrity.

Rule:
- Do not include `@@processing@@` in your response.
- Answer the UserPrompt directly, without explanations or commentary.
{attrs_rules}

Wikipedia Resources:
{wikipedia_resources}

Context:
{context}

User prompt:
{prompt}
"""

DEFAULT_HISTORY_TEMPLATE = """
---
Prompt: {prompt}
Result: {result}
Timestamp: {timestamp}

"""


varbose_print = False
def verbose_print(msg):
    global varbose_print
    if varbose_print:
        rich.print(msg)


class TextManager:
    def __init__(self, filepath, templates, history):
        """
        filepath: str = "foobar.md"
        templates: list[dict] = [{"tag": "tag_name", "format": "prompt formt"}]
           - example: [{"tag": "summary",  "format": "summarize: {prompt}"}]
        history:
           - example: {"previous_prompt": "", "previous_response": ""}
        """
        self.filepath = os.path.abspath(filepath)
        self.history = history
        if templates is None:
            templates = []
        self.templates = templates
        self.url_catch = {}


    @classmethod
    def attar_and_llm(cls, attrs_and_llm):
        """
        example:
          - "(gpt):funny:detail" -> (gpt, ["funny", "detail"])
          - "(gpt)" -> (gpt, [])
          - "funny:detail" -> (None, ["funny", "detail"])
        """
        if attrs_and_llm is None:
            return [], None
        # llm name = "(gpt)" -> gpt
        llm_name = re.search(r'\([\w]+\)', attrs_and_llm)
        if llm_name:
            attrs_and_llm = attrs_and_llm.replace(f'{llm_name.group(0)}', '')
            llm_name = llm_name.group(0).replace('(', '').replace(')', '')
        attrs = attrs_and_llm.split(':') if attrs_and_llm else []
        attrs = list(filter(None, attrs))
        return attrs, llm_name

    @classmethod
    def extract_tag_contents(cls, tag_name, text):
        """
        get tag and inner text.
          example: <prompt(gpt):funny>内容</prompt>
            -> ("<prompt:funny>内容</prompt>", "内容", ["funny"], "gpt")

        [TODO] recursive process:
          example: <prompt>summarize: <prompt> Python language </prompt></prompt>
            -> <prompt>Python language</prompt>
            -> ("<prompt>Python language</prompt>", "Python language", [])
        """

        # match list: 
        #   -> <prompt>foobar</prompt>
        #   -> <prompt:funny>foobar</prompt>
        #   -> <prompt(gpt):funny>foobar</prompt>
        #   -> <prompt(gpt)>foobar</prompt>
        pattern = f'<{tag_name}([^>]*?)>(.*?)</{tag_name}>'
        match_tag =  re.search(pattern, text, flags=re.DOTALL)
        if match_tag:
            attrs, llm_name = TextManager.attar_and_llm(match_tag.group(1))
            return (match_tag.group(0), match_tag.group(2), attrs, llm_name) 
        return None

    @classmethod
    def convert_custom_tag(cls, tag, prompt, attrs, llm_name):
        """
        Convert custom tag to safe tag:
        
        tag: dict = {"tag": "tag_name", "format": "prompt formt", "change": "prompt"}
        prompt: str = "prompt text"
        attrs: list = ["attr1", "attr2"]
        llm_name: str = "gpt"

        return:
          <prompt(gpt):attr1:attr2>prompt text</prompt>
        """        
        attrs_text = ":".join(attrs) if attrs else ""
        attrs_text = f":{attrs_text}" if attrs_text != "" else ""
        llm_name = f"({llm_name.lower()})" if llm_name is not None else ""
        # tagをsafeにする
        # tag['change']が設定されていない場合、または
        # tag['change']が"prompt"または"chat"でない場合は、"prompt"にする
        # 言い換えると、tag['change']は他のtagには変換できない
        # 
        # reason:
        #   -> tagはpromptまたはchatにしないと循環参照が起きる可能性があるため
        if "change" not in tag:
            tag["change"] = "prompt" 
        elif tag["change"] != "prompt" and tag["change"] != "chat":
            print(f"[warning] Invalid tag change: {tag['change']}")
            tag["change"] = "prompt" 
        return f"<{tag['change']}{llm_name}{attrs_text}>{prompt}</{tag['change']}>"

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
                tags, prompt, attrs, llm_name = result
                replace_tags = TextManager.convert_custom_tag(tag, prompt, attrs, llm_name)
                self.text = self.text.replace(tags, replace_tags)
                self._save_text()
                return

    def _load_text(self):
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                self.text = f.read()
        except Exception as e:
            print(f"[red][Error]: {e}")
            self.text = None

    def _save_text(self):
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                f.write(self.text)
        except Exception as e:
            print(f"[red][Error]: {e}") 

    @classmethod
    def safe_text(cls, response, tag):
        """
        LLMのresponseに属性付き<prompt>タグも含めない
    
        理由: 再起が止まらくなるから。LLMの回答次第では、爆発的に増加する。
          example: `<prompt>Why did I create this product?</prompt>` 
            -> `<prompt>description of this product and usecase</prompt>`
            -> `<prompt>Product Tagwriting example</prompt>`
            ...
        従って: promptにはpromptが含まれず、確実に停止することを保証する。            
        """
        response = re.sub(rf'<{tag}(:[\w:]+)?>', '', response)
        response = response.replace(f'</{tag}>', '')
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
        pattern = r'<url>(.*?)</url>'
        def replacer(match):
            url = match.group(1).strip()
            if url in self.url_catch:
                return self.url_catch[url]
            else:
                print(f"[green][Process] Fetching URL: {url}")
                response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                verbose_print(f"[green][Result] URL Response: {response}[/green]")
                response.encoding = response.apparent_encoding
                if response.status_code == 200:
                    # HTML -> BeautifulSoup -> Text
                    verbose_print(f"[green][Process] Converting HTML to Text[/green]")
                    html_text = HTMLClient.html_to_text(response.text)
                    self.url_catch[url] = html_text
                    return html_text
                else:
                    print(f"[url error: status_code={response.status_code}]")
                    return ""
        try:
            return re.sub(pattern, replacer, text, flags=re.DOTALL)
        except Exception as e:
            print(f"[url error: {e}]")
            return text

    @classmethod
    def prepend_wikipedia_sources(cls, wikipedia_sources):
        """
        wikipedia_sources: Set[Tuple[str, str or None]]
          -> return: str
        Wikipediaのタグもここで消去する。
        """
        if not wikipedia_sources:
            return ""

        wikipedia_resources = ""
        for title, extract in wikipedia_sources:
            if extract:
                wikipedia_resources += f"## {title}\n\n{extract}\n\n"
        return wikipedia_resources

    def fetch_wikipedia_tags(self, text):
        """
        <wikipedia>記事タイトル</wikipedia> の形式で記述されたタグを全て検出し、
        Wikipedia APIから取得した記事本文と組み合わせたsetを返す。

        Returns:
            Set[Tuple[str, str or None]]: (タイトル, 記事本文 or None) のセット
        """
        print("[green][Process] Fetching Wikipedia tags...[/green]")
        pattern = r'<wikipedia>(.*?)</wikipedia>'
        titles = set(title.strip() for title in re.findall(pattern, text, flags=re.DOTALL))
        results = set()
        for title in titles:
            cache_key = f"wikipedia:{title}"
            if cache_key in self.url_catch:
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

    @classmethod
    def build_attrs_rules(cls, attrs, templates) -> str:
        """
        Build rules for attributes.

        example:
          Yaml settings:
          ```
          attrs:
            bullet: 
              - "bullet style"
              - "Markdown style"
          ```   
          attrs type: List[str] or str
          
          to Prompt:
          ```
          Rules:
          - bullet style
          - Markdown style
          ({{attrs_rules}})
          ```
        """
        rules = ""
        for attr in attrs:
            if attr in templates["attrs"]:
                # list or str
                # listのときは、ルールをリスト化し、
                # strのときは、そのままルールとして追加する
                if isinstance(templates["attrs"][attr], list):
                    for rule in templates["attrs"][attr]:
                        rules += f" - {rule}\n"
                elif isinstance(templates["attrs"][attr], str):
                    rules += f" - {templates['attrs'][attr]}\n"
                else:
                    print(f"[red][bold][Warning][/bold] Invalid attribute rule type: '{attr}'[/red]")
                    print(f"[red][bold][Warning][/bold] Attribute rule type must be list or str[/red]")
            else:
                print(f"[red][bold][Warning][/bold] Attribute rule not defined: '{attr}'[/red]")
        return rules        

    def _build_attrs_rules(self, attrs) -> str:
        return TextManager.build_attrs_rules(attrs, self.templates)

    def _build_wikipedia_resources(self, context, prompt) -> str:
        wikipedia_tags = self.fetch_wikipedia_tags(context)
        wikipedia_tags = wikipedia_tags | self.fetch_wikipedia_tags(prompt)
        # Wikipedia記事の取得結果を反映
        return TextManager.prepend_wikipedia_sources(wikipedia_tags)

    def extract_prompt_tag(self):
        self._load_text()

        # loadが失敗した場合:
        #   self.text = None -> 処理を止める
        if self.text is None:
            return None

        # backup_text:
        #   -> <prompt> or <chat>タグを置換する前のself.text
        #   LLMとの接続が切断されたときに元のテキストに戻すために使用
        backup_text = self.text
        try:
            # simple_merge
            # もし読み込んだファイルに@@processing@@があった場合、前回の結果を挟み込む
            if self.templates['config'].get('simple_merge', False):
                if "@@processing@@" in self.text:
                    print("[green][bold][Processs][/bold] find `@@processing@@`. Simple merge. [/green]")
                    print(f"[green][bold][Processs][/bold] >> {self.history['previous_response']}[/green]")
                    self.text = self.text.replace("@@processing@@", f"{self.history['previous_response']}")
                    self._save_text()
                    return None
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

            tag, prompt, attrs, llm_name = result

            # Safety Undo Check
            # -> config.yamlのconfig.duplicate_promptを参照
            # -> 以前と同じPromptが入ってきた場合、実行を止める
            if self.templates["config"].get('duplicate_prompt', False):
                if prompt == self.history["previous_prompt"]:
                    print("[green][bold][Processs][/bold] Duplicate prompt detected. Skipping.[/green]")
                    print(f"[green][bold][Processs][/bold] Previous prompt: {self.history['previous_prompt']}[/green]")
                    return None

            # ---- Context ----
            # <prompt> or <chat>によってコンテキスト戦略を変える。
            # <prompt>タグの場合は、
            #   -> self.textをコンテキストとして使用する
            # <chat>タグの場合は、
            #   -> コンテキストをなくす("@@processing@@")だけにする

            self.text = self.text.replace(tag, "@@processing@@", 1)
            self._save_text()

            if result_kind == 'prompt':
                # 同じ<prompt>hoge</prompt>というタグが出てくる可能性があるので、
                # 1回だけ置換する
                context = self.text.replace(tag, "@@processing@@", 1)
            else:
                # <chat>タグの場合は、全てのコンテキストを除去する
                #   -> @@processing@@をそのまま使用
                context = "@@processing@@"
            
            # ---- Include ----
            context = TextManager.replace_include_tags(self.filepath, context)
            # Includeエラーが起きたときは一回ストップする
            if context is None:
                return None
            # Promptの内部にあるincludeタグも置換する
            prompt = TextManager.replace_include_tags(self.filepath, prompt)
            if prompt is None:
                return None

            attrs_rules = self._build_attrs_rules(attrs)
 
            # ---- URL ----
            
            print(f"[green][Process] fetch URL data ... [/green]")

            prompt = self.replace_url_tags(prompt)
            context = self.replace_url_tags(context)

            print(f"[green][Process] URL Tags Replaced[/green]")
            # ---- Wikipedia ----
            wikipedia_resources = self._build_wikipedia_resources(context, prompt)

            # ---- LLM ----
            llm_client = LLMSimpleClient(llm_name)
            response = llm_client.ask_ai(self.templates["prompt"].format(
                prompt=prompt, context=context, attrs_rules=attrs_rules, wikipedia_resources=wikipedia_resources))

            # responseがNoneのときは、中断
            if response is None:
                self.text = backup_text
                self._save_text()
                return None

            # prompt or chat tagがレスポンスに入っていた時に、
            # その部分を削除する
            response = TextManager.safe_text(response, 'prompt')
            response = TextManager.safe_text(response, 'chat')
            response = response.replace("@@processing@@", "", 1)
            
            # ObsidianのようなHard save - loadするeditor向け対応
            self._load_text()
            self.text = self.text.replace("@@processing@@", f"{response}", 1)
            self._save_text()
            self.append_history(prompt, response)
            return (prompt, response)
        except AttributeError as e:
            # エラーが発生した場合:
            #  -> backup_textに差し戻す処理を挟む
            self.text = backup_text
            self._save_text()

            # backtrace output
            print(f"[red][Error]: {e}")
            e.__traceback__.print_exc()
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
        filename = file_tmpl.format(filename=base)
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
        self.history = {
            "previous_prompt": "",
            "previous_response": ""
        }

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

    @classmethod
    def build_templates(cls, templates):
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
        templates["default_template_target"] = False
        if "target" not in templates:
            templates["target"] = ["*.txt", "*.md", "*.markdown"]
            templates["default_template_target"] = True
        if "hook" not in templates:
            templates["hook"] = {}

        # change absolute path for ignore file
        templates["ignore"] = [os.path.abspath(p) for p in templates["ignore"]]
        templates["target"] = [os.path.abspath(p) for p in templates["target"]]

        # default config
        if "config" not in templates:
            templates["config"] = {}

        # config notes:
        #   duplicate_prompt: duplicate prompt check
        #     -> default: False
        if "duplicate_prompt" not in templates["config"]:
            templates["config"]["duplicate_prompt"] = False
        #   simple_merge: if `@@processing@@` is in files, replace previous response
        #     -> default: True
        if "simple_merge" not in templates["config"]:
            templates["config"]["simple_merge"] = True
        #   hot_reload_yaml: if selfpath is not None, hot reload yaml file.
        #     -> default: False
        if "hot_reload_yaml" not in templates["config"]:
            templates["config"]["hot_reload_yaml"] = False
        #   verbose_print: verbose print
        #     -> default: False
        if "verbose_print" not in templates["config"]:
            templates["config"]["verbose_print"] = False

        # selfpath:
        #   -> for hot reload yaml file.
        templates["selfpath"] = None
        return templates

    def start(self, watch_path, yaml_path):
        """
        Start the Tagwriting CLI path.

        Args:
            watch_path (str): Directory or file path to watch
            yaml_path (str): Template yaml file path

        Process:
            0. Initialize
              -> Absolute path conversion
              -> Check watch path (directory or file)
            1. Welcome message: "Hello, Tagwriting CLI!"
            2. Load templates from yaml file
              -> Failed to load templates 
                -> Abort!             
            3. Start main loop
        """
 
        # 0. Initialize
        watch_path = os.path.abspath(watch_path)
        if not os.path.exists(watch_path):
            self.console.print(f"[red]Directory or file does not exist: {watch_path}[/red]")
            return
        self.watch_path_is_dir = os.path.isdir(watch_path)
        self.watch_path = watch_path
        self.dirpath = os.path.dirname(watch_path)

        # 1. Welcome message
        self.console.rule("[bold blue]Tagwriting CLI[/bold blue]")
        self.console.print(f"[bold magenta]Hello, Tagwriting CLI![/bold magenta] :sparkles:", justify="center")
        version = importlib.metadata.version("tagwriting")
        self.console.print(f"[yellow]Version: {version}[/yellow]", justify="center")

        try:
            # 2. Load templates from yaml file
            self.load_templates(yaml_path)
        # Not found yaml file
        except FileNotFoundError:
            self.console.print(f"[red]Failed to load templates: [/red]")
            self.console.print(f"[red] -> Yaml file does not exist: {yaml_path}[/red]")
            return
        # Invalid yaml file
        except yaml.YAMLError:
            self.console.print(f"[red]Failed to load templates: [/red]")
            self.console.print(f"[red] -> Invalid yaml file: {yaml_path}[/red]")
            return

        # 2.1 verbose print setting
        #
        # [FIXME] 
        #   "global variable change" is dirty method. 
        global varbose_print
        varbose_print = self.templates["config"]["verbose_print"]

        # 3. Start main loop
        self.inloop()

    def load_templates(self, yaml_path):
        """
        Load templates from yaml file.

        Process:
          if self.watch_path_is_dir is False, override target param.
          but self.templates["default_template_target"] is False, warning message.

        Args:
            yaml_path (str): Path to yaml file

        Note:
            Error handling => parent method.
        """
        templates = None
        if yaml_path:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                templates = yaml.safe_load(f)
        self.templates = ConsoleClient.build_templates(templates)
        if self.watch_path_is_dir is False:
            self.templates["target"] = [self.watch_path]
            if not self.templates["default_template_target"]:
                self.console.print(f"[yellow]Warning - Override target param: {self.watch_path}[/yellow]", justify="center")
        self.templates["selfpath"] = yaml_path

    def on_change(self, filepath):
        """
        Handle file change event.

        Args:
            filepath (str): Path to the changed file
    
        Process:
          1. Check if the changed file is the template file
          2. Templates["config"]["hot_reload_yaml"] is True?
            -> If the changed file is the template file, reload the templates
          3. If the changed file is not the template file, process the file
        """
        self.console.rule(f"[bold yellow]File changed: {os.path.basename(filepath)}[/bold yellow]")
        if self.templates["config"]["hot_reload_yaml"] and filepath == self.templates["selfpath"]:
            self.console.print(f"[bold yellow]Hot reload templates from {filepath}[/bold yellow]")
            # 編集中の壊れたファイルを読み込む場合があるので、Exceptionをキャッチしておいて、
            # クライアントが落ちないようにする
            try:
                self.load_templates(self.templates["selfpath"])
            except Exception as e:
                self.console.print(f"[yellow][Warning]Failed to reload templates: {e}[/yellow]")
                self.console.print("[yellow]Continue to watch files...[/yellow]")
        else:            
            text_manager = TextManager(filepath, self.templates, self.history)
            result = text_manager.extract_prompt_tag()
            if result is not None:
                prompt, response = result
                self.console.print(f"[bold green]Prompt:[/bold green] {prompt}")
                self.console.print(f"[bold green]Response:[/bold green] {response}")

                # update history
                self.history["previous_prompt"] = prompt
                self.history["previous_response"] = response

                # "text_generate_end" が存在する場合のみコマンド実行
                if "text_generate_end" in self.templates["hook"]:
                    self.run_shell_command(self.templates["hook"]["text_generate_end"],
                        {"filepath": filepath})

    def _start_client_message(self):
        # show starting message:

        if self.watch_path_is_dir:
            self.console.print(f"[green]Watching >>> {self.dirpath}[/green]", justify="center")
        else:
            self.console.print(f"[green]Watching >>> {self.watch_path}[/green]", justify="center")
        
        self.console.print(f"[blue] exit: Ctrl+C[/blue]", justify="center")
        self.console.print(f"[green]Start clients... [/green]", justify="center")

    def inloop(self):
        """
        1. show starting message
        2. start main loop
          -> Start watch path
          -> Start observer
        """
        self._start_client_message()
        event_handler = FileChangeHandler(self.dirpath, self.on_change, self.templates)
        observer = Observer()
        observer.schedule(event_handler, path=os.path.dirname(self.dirpath), recursive=True)
        observer.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()


class FileChangeHandler(FileSystemEventHandler):

    def __init__(self, dirpath, on_change, templates, debounce_interval=0.5):
        super().__init__()
        self.dirpath = os.path.abspath(dirpath)
        self.on_change = on_change
        self._last_called = 0
        self._debounce_interval = debounce_interval
        self._ignore = templates["ignore"]
        self._target = templates["target"]
        self._selfpath = templates["selfpath"]

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
        # 流石に全部のmodifiedを出力するのは冗長なのでコメントアウト
        # print(f"[white][event]File modified: {event.src_path}[/white]")
        if self.is_ignored(event.src_path):
            return
       # event.src_pathがtemplatesファイルでなく、かつ対象ファイルでない
        if not self.is_target(event.src_path) and event.src_path != self._selfpath:
            return
        if not self.is_text_file(event.src_path):
            return
        if not self._is_debounce():
            return
        self.on_change(event.src_path)

class LLMSimpleClient:
    def __init__(self, llm_name = None) -> None:
        if llm_name:
            env_filepath = Path.cwd() / f".env.{llm_name}"
        else:
            env_filepath = Path.cwd() / ".env"
        load_dotenv(dotenv_path=env_filepath, override=True)
        self.api_key = os.getenv("TAGWRITING_API_KEY") or os.getenv("API_KEY")
        self.base_url = os.getenv("TAGWRITING_BASE_URL") or os.getenv("BASE_URL")
        self.model = os.getenv("TAGWRITING_MODEL") or os.getenv("MODEL")
        self.filepath = env_filepath

    def build_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def build_payload(self, prompt) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "timeout": 100
        }

    def build_url(self, endpoint) -> str:
        # merge base url and endpoint
        if not self.base_url.endswith('/'):
            self.base_url += '/'
        return self.base_url + endpoint
    
    def ask_ai(self, prompt):
        if not self.api_key:
            raise RuntimeError(f"API_KEY not found in {self.filepath}. ")
        try:
            print(f"[green][Process] Post request to {self.build_url('/chat/completions')}[/green]")
            completion = requests.post(
                self.build_url("chat/completions"), headers=self.build_headers(), json=self.build_payload(prompt))
            data = completion.json()
            verbose_print(f"[green][Process] Response: {data}[/green]")
            # response['choices'][0]['message']['citations']
            response =  data["choices"][0]["message"]["content"]
            
            # maybe Perplexity AI only
            if  "citations" in data:
                response += "\n\n"
                response += "Sources: \n\n"
                citations = data["citations"]
                for i, citation in enumerate(citations, 1):
                    title = HTMLClient.get_title(citation)
                    response += f"{i}. [{title}]({citation})\n"
            return response
        except requests.exceptions.JSONDecodeError as e:
            print(f"[red][bold][Error][/bold] JSONDecodeError:[/red]")
            print(completion)
            return None

class HTMLClient:
    @classmethod
    def get_title(cls, url):
        response = requests.get(url, timeout=10)
        # [TODO] なんか中国語だとバグったのであとで調べる
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup.title.string

    @classmethod
    def html_to_text(cls, html_text):
        soup = BeautifulSoup(html_text, 'html.parser')
        return soup.get_text()



@click.command()
@click.option('--watch', 'watch_path', default=".", help='Directory path or file path to watch')
@click.option('--templates', 'yaml_path', default=None, help='Template yaml file path')#
def main(watch_path, yaml_path):
    # default
    # -> watch_path = "."
    # -> yaml_path = None
    #  
    # [TODO]: asterisk file path ("*.md", "*.txt", etc. ) is "multiple files"
    #  example: "*.md" -> "hoo.md" "bar.md"
    #  and raise "Error: Got unexpected extra arguments". fix this.
    if yaml_path is not None:
        yaml_path = os.path.abspath(yaml_path)
    client = ConsoleClient()
    client.start(watch_path, yaml_path)


if __name__ == "__main__":
    main()
