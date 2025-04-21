# TagWriting

**TagWriting**は、ただタグで囲むだけ。

AIと人間のあいだを、テキストファイルでもっとシームレスに繋ぐツールです。

---

## ✨ 概要

`<prompt>`タグで囲んだ部分に、LLM（大規模言語モデル）による処理を加えます。**ディレクトリを監視して**、その中のテキストファイルやMarkdownファイルが**保存されたタイミングで自動的に変換**されます。

```markdown
わたしはTagWritingです。
<prompt>TagWritingの良いところを一行で説明する</prompt>
```

↓

```markdown
わたしはTagWritingです。
テキストをタグで囲むだけで素早い文章の生成が可能になります。
```

---

## 🛠️ 使い方

1. `.md`などのファイルを編集し、プロンプトをタグで囲む  
2. 保存すると、その部分がLLMによって変換される  
3. 結果はファイルに直接反映される

---

## 🔁 ユースケース：Promptの連鎖処理（Prompt Chain）

TagWritingでは、プロンプトを複数並べるだけで**段階的な生成処理**ができます。

```markdown
わたしはTagWritingです。
<prompt>なぜこのプロダクトを作ったか</prompt>
<prompt>TagWritingの良いところを一行で説明する</prompt>
```

保存後：

```markdown
わたしはTagWritingです。
テキスト生成AIを文章を作成するときに、上手い方法がないか探していたときに思いつきました。
<prompt>TagWritingの良いところを一行で説明する</prompt>
```


結果：

```markdown
わたしはTagWritingです。
テキスト生成AIを文章を作成するときに、上手い方法がないか探していたときに思いつきました。
TagWritingの良いところは、シームレスな文章との連携です。
```

---

## 💡 なぜTagWritingなのか？

### ✅ テキスト編集とのシームレスさ
テキスト内で直接プロンプトをタグで囲むだけ。LLMの操作にわざわざ手を止める必要はありません。**思考の流れを中断せずにAIの力を借りられます。**

### ✅ 可読性の高さ
タグを明示的に書くことで、**どの部分をAIに任せたいか**がはっきり見える。ドキュメントの履歴や編集も明快になります。

### ✅ 柔軟性と互換性
TagWritingは更新のあったテキストファイルを直接書き換えるだけ。つまり、**どんなエディタでも、どんな形式でも理論上対応可能**。エディタがファイルの再読込に対応していれば、それだけで連携完了。プラグインの必要なし。Visual Studio Core, Vim, emacs, etc、好きなものをお使いください。

---

## 🚀 インストール方法（Python）

1. 必要な依存パッケージをインストール

```sh
pip install .
```

2. コマンドラインツールとして使う

```sh
tagwriting <ディレクトリ名>
```

---

## ⚙️ .envファイルの使い方

フォルダ直下に `.env` ファイルを作成し、APIキーやモデル名などを記載してください。

例:

```env
API_KEY=sk-xxxxxxx
MODEL=gpt-3.5-turbo
BASE_URL=https://api.openai.com/v1
```

- `.env` は `tagwriting` コマンドを実行したディレクトリのものが自動的に読み込まれます。
- 複数プロジェクトで使い分けたい場合は、各ディレクトリごとに `.env` を用意してください。
- OpenAPI互換なら、とりあえず使えます(Grok、Deepseekなど)
---

## ⚙️ システム構成

### `tagwriting <directory>`

指定した**ディレクトリ**を監視し、保存されたファイルの`<prompt>`タグを探索・処理します。

- LLMや外部APIへのリクエストは非同期で発行
- エラーや作業状況はCLIにリアルタイム出力
- 更新はファイルに直接反映（再保存で再処理）

---

## 🧪 開発について

TagWritingは現在、試験的に開発中です。  
コードの設計方針は以下の通り：

- シンプル：基本はタグ検出 → コンテキスト送信 → 結果で置換
- ステートレス：ファイルベースで完結、環境依存最小
- 最小インタフェース：UIに依存せず、あらゆるツールと併用可能

---

# 詳細

## 挙動の仕様

Tagwritingの内部で、以下の流れで動作します。

1. ディレクトリの監視
2. ディレクトリ内のファイルの変更を検知
3. ファイルを読み込む
4. イベントの発火
5. テンプレートタグの検出(`example: <summary></summary>`)
6. テンプレートタグをプロンプトタグに変換(`example: <prompt>文章の全体を要約して</prompt>`)
7. プロンプトの検出(`example: <prompt>文章の全体を要約して</prompt>`)
8. プロンプトの変換部分をマーキング(`example: @@processing@@`)
9. コンテキストとプロンプトにあるincludeタグの外部ファイルの置換(`example: <include>foobar.md</include>`)
10. Wikipediaなどの外部リソースの取得し、コンテキストに反映。
11. 結果をファイルに書き込む(`example: Tagwritingは素晴らしいプロダクトです`)
12. ディレクトリの監視を再開

## Build-in タグの詳細

### promptタグ(`<prompt></prompt>`)

現時点で一番最後に処理されるタグであり、このプロンプトタグのテキストをLLMに生成する命令として渡します。
このさい、使用されるコンテキストは、そのテキスト（後出するincludeタグの展開部分も含めて）全体になります。

例えば、

```markdown
わたしはTagWritingです。
<prompt>なぜこのプロダクトを作ったか</prompt>
```

という場合、

```
  あなたの回答はcontext内の`@@processing@@`と置換されます。コンテキストの整合性に合わせてテキストを出力してください。
  Rule:
   - `@@processing@@`は貴方の解答に含めないでください。
   - 解説や説明を含めず、user promptに直接回答してください。
  context:
  わたしはTagWritingです。
  @@processing@@
  user prompt: 
  なぜこのプロダクトを作ったか
```

といったようなプロンプトとして、LLMに渡されます。

#### 仕様

promptタグで生成されたテキストは、停止可能性を担保するため、そのprompt内で生成された`<prompt></prompt>`タグを置換します。
従って、再帰的に`<prompt></prompt>`タグを囲むよう指示したとしても、そのタグは削除されます。

```markdown
わたしはTagWritingです。
<prompt>それでは`prompt tag`で、「りんご」を囲んだものを出力してください。</prompt>
```

```markdown
わたしはTagWritingです。
りんご
```

このとき、仮に`<prompt>りんご</prompt>`と出力されていたとしても、「りんご」としか出力されません。

### chatタグ(`<chat></chat>`)

`<chat></chat>`タグは、`<prompt></prompt>`タグと同様に、このプロンプトタグのテキストをLLMに生成する命令として渡します。
そのさい、全部の文章全体のコンテキストを使わずに、テキスト内の単体のみのプロンプトとして振舞います。

例えば、

```markdown
わたしはTagWritingです。
<chat>なぜこのプロダクトを作ったか</chat>
どうですか、素晴らしいでしょう！
```

という場合、

```
  あなたの回答はcontext内の`@@processing@@`と置換されます。コンテキストの整合性に合わせてテキストを出力してください。
  Rule:
   - `@@processing@@`は貴方の解答に含めないでください。
   - 解説や説明を含めず、user promptに直接回答してください。
  context:
  @@processing@@
  user prompt: 
  なぜこのプロダクトを作ったか
```

というように、コンテキストを全く使用しません。

#### FAQ: promptとchatの使い分け

例えば、全体のコンテキストを使わずに、一部分のコンテキストだけで十分の場合があります。
このとき、コンテキストで使いたい部分を`<chat></chat>`タグで囲むことで、
疑似的にコンテキストを制限するような使い方ができます。

```markdown
わたしはTagWritingです。
<chat>なぜこのプロダクトを作ったか、次の文章を絡めて回答してください:
どうですか、素晴らしいでしょう！
</chat>
```

`<chat></chat>`で使われた内部テキストはLLMの回答によっては削除されている可能性がありますので、注意が必要です。

この場合の対処法は、このドキュメントの最後の`FAQ`セクションを参照してください。

### includeタグ（`<include>filepath</include>`）

指定したファイルの内容を、LLMのプロンプトに与えるさいに挿入するための特殊タグです。

- 書式： `<include>パス</include>`（例：`<include>foo/bar.txt</include>`）
- パスは「現在加工しているファイル」からの相対パスで解決されます。
- includeタグ部分は、該当ファイルの内容で丸ごと置換されます。
- 複数のincludeタグがある場合もすべて一度に展開されます。
- **現状の仕様**: 入れ子のinclude（include先にさらにincludeがある場合）は展開されません。
- **現状の仕様**: include先にある`<prompt></prompt>`は実行されません。

例えば

```markdown
# 本文
<include>foo.md</include>
<include>bar.md</include>
```

保存時、`foo.md`や`bar.md`の内容がそれぞれ該当部分に挿入されます。また、`include`の挙動は単純な外部ファイルの読み込みと置換なので、プロンプト内の`<include>`は置換されます。

```markdown
# 本文
<chat>
  下の内容を要約して:
  <include>foo.md</include>
</chat>
```

#### FAQ: なぜinclude内の<prompt></prompt>は実行されないのですか？

処理として、`<include></include>`タグは、`<prompt>`実行後もテキストにタグを保持したまま残り続けます（置換されません）。もしこのinclude先の`<prompt></prompt>`が実行されると仮定した場合、この`prompt`の内容はどこに挟まるのかが不明確です。`include`の上か？下か？もし`include`の先に複数あった場合はどうなるか？

これはあまり綺麗ではないため、現状として`include`先の`<prompt></prompt>`は実行されません。

#### FAQ: include先のincludeは何故展開されないのですか？

安全性を確保するためです。少し考えると、include先のincludeを展開すると考えた場合、単純に循環テキストを作ることが可能なことがわかります。

例えば、`bar.md`を次のように作成します。

```markdown
<include>foo.md</include>
```

このあと`bar.md`を次のように作成します。

```markdown
# 本文
<include>bar.md</include>
```

こうした場合、循環テキストが作られ、停止しなくなります。

この問題の解決として`include`の`depth`を指定することで、どこまでの深さを展開するかを制御するという方法も考えられますが、そもそもの問題として`include`先の`include`を前提とするようなドキュメントの作成は、複雑性と見通しの悪さのために避けるべきなのではないかとも考えられます。従って、このような`depth`の問題については、優先度を低く見積もっています。

#### 仕様

##### Error: includeが失敗したときの挙動

include先のファイルが存在しない場合、または読み込めない場合は、**tagwritingは処理を中断し、エラーを出力します**。これは、`include`先のファイルを前提とした、現テキストファイルだと考えると、そのファイルが存在しないことは致命的な問題であるためです。

### wikipediaタグ（`<wikipedia>キーワード</wikipedia>`）

```markdown
Tagwritingは<wikipedia>人工知能</wikipedia>を利用しています。
```

このように書いたとき、以下のようにテキストの先頭にコンテキストを補給します。

```markdown
---
# Wikipedia resources:
## 人工知能

(記事の内容)
---
Tagwritingは<wikipedia>人工知能</wikipedia>を利用しています。
```

また、これは`chat`タグの内部でも使えるようにしています。

```
<chat>
  <wikipedia>人工知能</wikipedia>を教えて
</chat>
```

#### 仕様
##### Error: wikipedia先が取得できないときの挙動

wikipedia先が取得できない場合は、**tagwritingは処理を続行し、エラーを出力するだけに留まります**。これは、外部のWikipediaの情報を得るのには、ファイルよりも不確定要素が高いためです。

## YAMLテンプレートシステム

TagWritingでは、YAMLファイルによるテンプレートシステムをサポートしています。これにより、独自のタグやプロンプトのフォーマット、無視するファイルなどを柔軟に定義できます。

### sample.yaml の例

```yaml
prompt: |
  あなたの回答はcontext内の`@@processing@@`と置換されます。コンテキストの整合性に合わせてテキストを出力してください。
  Rule:
   - `@@processing@@`は貴方の解答に含めないでください。
   - 解説や説明を含めず、user promptに直接回答してください。
  {attrs_rules}
  context:
  {context}
  user prompt: 
  {prompt}

attrs:
  bullet: "箇条書きで出力する"

history:
  file: "{filename}.history.md"
  template: |
    ---
    Prompt: {prompt}
    Result: {result}
    Timestamp: {timestamp}

target:
  - "*.md"
  - "*.markdown"

ignore:
  - "README.md"
  - "sandbox/test_not_target.md"
  - ".git"

tags:
  - tag: "detail"
    format: "詳細に説明する: {prompt}"
  - tag: "summary"
    format: "文章全体を要約する"
  - tag: "profile"
    format: "人物のプロフィールを生成する。名前以外の各項目は<detail></detail>で囲む: {prompt}"
```

### コマンド例

```sh
tagwriting ./foobar/path --templates sample.yaml
```

### テンプレートの書式

- `prompt`: LLMに送る全体テンプレート。`{prompt}`や`{prompt_text}`が利用可能。
- `target`: 対象ファイルのパターンのリスト。ホワイトリスト形式。デフォルトでは`*.txt`, `*.md`, `*.markdown`です。
- `ignore`: 無視するファイルやパターンのリスト。ブラックリスト形式。
- `attrs`: 属性プロンプトルールの定義。
- `history`: そのファイルのLLMとのやり取りを記録する方式。
- `tags`: 独自タグのリスト。各タグは`tag`と`format`を持ち、`{prompt}`でタグ内テキストを埋め込む。

---

## 🏷️ 属性プロンプトルール（Attribute Prompt Rule）の使い方

TagWritingでは、タグの属性（例: `<prompt:funny>...</prompt>` の `funny` 部分）に「属性プロンプトルール」として説明文や指示を付与できます。

### 1. YAMLテンプレートに属性プロンプトルールを定義

`sample.yaml` などのテンプレートで `attrs` セクションを使い、各属性にルール（説明・指示文）を設定します。

```yaml
attrs:
  funny: "面白おかしいトーンで出力する"
  detail: "詳細に説明する"
```

### 2. タグで属性を指定

Markdownやテキスト内で、属性付きタグを使います。

```markdown
<prompt:funny>今日はどんな日？</prompt>
```

### 3. 属性プロンプトルールがプロンプトに反映

指定した属性に対応する説明文（属性プロンプトルール）が、LLMへ送るプロンプトの`Rule`欄に自動で追加されます。

**例:**

```yaml
Rule:
 - 面白おかしいトーンで出力する
 - `@@processing@@`は貴方の解答に含めないでください。
 - 解説や説明を含めず、user promptに直接回答してください。
```

属性を複数指定した場合も、すべての属性プロンプトルールが追加されます。

## 🏷️ カスタムタグ

カスタムタグは、LLMに渡される前に、テンプレートに従い、`<prompt></prompt>`または`<chat></chat>`タグに変換してテキストファイルに保存するという挙動を示します。

```
<dictionary>OpenAI</dictionary>
```

は、次のように変換されます。

```
<chat>意味を調べてください: OpenAI</chat>
```

カスタムタグは、このような`tags`セクションで定義します。

```
tags:
 - tag: "dictionary"
   format: "意味を調べてください: {prompt}"
   change: "chat"
```

また、属性プロンプトルールも継承されます。

```
<dictionary:funny>OpenAI</dictionary>
```

は、次のように変換されます。

```
<chat:funny>意味を調べてください: OpenAI</chat>
```

### 🏷️ タグの種類と指定方法

TagWritingで利用できるタグ（tags）は、現在「prompt」または「chat」のどちらかを選択できます。

- `tags`を明示的に指定しない場合は、デフォルトで「prompt」として扱われます。
- `tags`には「prompt」または「chat」以外を指定することはできません。

**注意:**
- 「prompt」「chat」以外の値を指定した場合や、`tags`を省略した場合は「prompt」として扱われます。

---

# FAQ

## 属性プロンプトルールとカスタムタグの違いについて教えてください

属性プロンプトルールは、プロンプトのルールとして追記されるため、非常に柔軟に使いまわすことができます。その一方で、カスタムタグは他のタグへの変換ですので、柔軟性がない代わりに、より具体的な用途に適しています。例えば、次のような組み合わせが、両者の違いを適切に示すでしょう。

```yaml
attrs:
 - simple: "簡潔に説明する"

tags:
  - tag: "summary"
    format: "文章全体を要約する"
```

```
<summary:simple></summary>
```

このとき「簡潔に説明する」は出力のルールとして、使いまわしが出来ますが、"summary"はより具体的なプロンプトの指示内容になっていますね。念のために、実際にどのようなプロンプトとしてLLMに渡されるかも確認してみましょう。

```
  あなたの回答はcontext内の`@@processing@@`と置換されます。コンテキストの整合性に合わせてテキストを出力してください。
  Rule:
   - `@@processing@@`は貴方の解答に含めないでください。
   - 解説や説明を含めず、user promptに直接回答してください。
   - 簡潔に説明する
  context:
  @@processing@@
  user prompt: 
  文章全体を要約する
```

## LLMレスポンス後の加工を入れる予定はないですか？

あんまり入れる予定はありません。これは任意のトリガーで「何らかの前処理 -> LLM -> 何らかの後処理 」というのを行うのは意外と複雑だからですし、「前処理」と「後処理」が絡み合い、ユーザーが使用するにしても、機能をシンプルに保てず混乱を招く可能性が高いので、現状では優先度を低く考えています。

また同時に、tagwritingの設計思想に基づき、「テキストファイル上でのプロンプトを生成する」という役割に集中するという考え方を反映しています。言い換えると、プロンプトを通じてLLMが生成したテキストの後処理は、このソフトウェアの役割ではなく、ユーザーに任せるという考え方ですし、出来るならLLMの命令を通じてテキストは処理するべきだと考えています。

例えば、このようなLLM後の加工を入れる処理が必要なものして`<chat></chat>`タグで使ったユーザープロンプトを残したいといった用途が考えられますが、この場合は`attrs`で対応するなどを考えてみてください。

```
attrs:
   remain: "ユーザープロンプトを`> `付きで残す"
```