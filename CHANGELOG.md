# CHANGELOG

## 0.3.x

### 0.3.2
 - **[WIP]**Documentの全面的な書き直し
   - READMEにだらっと書いていたのを修正する

### 0.3.1
 - BeautifulSoupを入れたので、URLタグの実装
 - **0.3.1.1** defaultの挙動を修正する
   - 簡単に使えるように、引数をオプションにする
     - defaultはcurrent files(`.`)ディレクトリを監視するようにする
 - **0.3.1.2**  Watch pathの引数がfile path(not directory path)だった場合に単独のファイルを監視するようにする
   - もしWatch pathがYaml filesで定義されている場合、引数で上書きされている旨を伝える
 - **0.3.1.3** yaml fileのHot reloadを行うかどうかをYaml configに書けるようにする
 - **0.3.1.4[WIP]** configに`verbose_print`を追加する
### 0.3.0
- **0.3.0.2**URL Passの接続をちゃんとしたロジックで行う
- **0.3.0.1**Perplexityには独特のフィールド処理があるので、それの対処
- **[WIP]** もう少しInner tagの処理を綺麗にする
- MultiClientの追加
  - 複数のLLMを同時に使用する
  - タグの中に`()`構文を作成する
    - 用例: `<chat(gpt)>こんにちは！</chat>`
    - 仕様: `({params})`の中の文字を読み、そこから`.env.{params}`として利用する。

## 0.2.x

### 0.2.3

- Yamlファイルにconfigを追加
  - duplicate promptの追加
    - 同じプロンプトが入力されたときに、トリガーされないようにする
    - 理由: 自動保存に対応しているエディタでUndoすると同じプロンプトが何度も発行されるため
  - simple_mergeの追加
    - 二回目読み込んだファイルに`@@processing@@`があった場合、前回の結果を挟み込む処理を設ける
    - 理由: エディタの保存のタイミングによってはファイルの変更を読み込む前に書き込んでしまうため、それに対処する
      -  **0.2.3.1 Bug Fix**: 出力`@@processing@@`があった場合、無限ループに陥ってしまうため、削除する。