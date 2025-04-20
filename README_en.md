# TagWriting

TagWriting is a CLI tool that enables fast and flexible text generation by simply enclosing prompts in tags within your text files. It is designed to be simple, stateless, and editor-agnostic, making it easy to integrate into any workflow.

---

## 🚀 Installation (Python)

1. Install dependencies:

```sh
pip install .
```

2. Use as a command-line tool:

```sh
tagwriting <filename>
```

---

## ⚙️ How to use .env

Create a `.env` file in your working directory and specify your API key, model name, and base URL as follows:

```env
API_KEY=sk-xxxxxxx
MODEL=gpt-3.5-turbo
BASE_URL=https://api.openai.com/v1
```

- The `.env` in the directory where you run the `tagwriting` command will be loaded automatically.
- If you work with multiple projects, prepare a separate `.env` for each directory.
- Any OpenAPI-compatible endpoint can be used (e.g., Grok, Deepseek, etc.).

---

## 🛠️ Usage

1. Edit a `.md` or similar file and enclose your prompt in a tag.
2. Save the file; the tagged section will be replaced by the LLM's output.
3. The result is written directly to the file.

---

## 🔁 Use Case: Prompt Chaining

By placing multiple prompts in sequence, you can achieve stepwise generation processing.

```markdown
I am TagWriting.
<prompt>Why did I create this product?</prompt>
<prompt>Describe the best feature of TagWriting in one sentence.</prompt>
```

---

## Built-in Tags

### prompt tag (`<prompt></prompt>`)

This tag is processed last. The inner text of the prompt tag is sent to the LLM as the user prompt.

### include tag (`<include>filepath</include>`)

A special tag to insert the contents of another file at that location for use in the LLM prompt.

- Format: `<include>path</include>` (e.g., `<include>foo/bar.txt</include>`)
- The path is resolved relative to the file currently being processed.
- The include tag is replaced entirely by the contents of the specified file.
- If there are multiple include tags, all are expanded at once.
- **Current limitation:** Only one level of nested include is expanded; full recursive expansion is not yet supported.
- **Current limitation:** `<prompt></prompt>` tags inside included files are not expanded.

#### Example

```markdown
# Main text
<include>foo.md</include>
<include>bar.md</include>
```

When saved, the contents of `foo.md` and `bar.md` will be inserted at each respective location.

---

## System Behavior

The internal workflow of TagWriting operates as follows:

1. Watches the directory for changes.
2. Detects file changes within the directory.
3. Reads the changed file.
4. Triggers an event for processing.
5. Detects template tags (e.g., `<summary></summary>`).
6. Converts template tags to prompt tags (e.g., `<prompt>Summarize the whole text</prompt>`).
7. Detects prompt tags (e.g., `<prompt>Summarize the whole text</prompt>`).
8. Marks the section to be replaced (e.g., `@@prompt@@`).
9. Sends the prompt to the LLM and writes the result back to the file.
10. Resumes watching the directory for further changes.

---

## YAML Template System

TagWriting supports a YAML-based template system, allowing you to flexibly define custom tags and prompt formats.

### How to Use

1. Create a YAML file for templates (e.g., `sample.yaml`).

```yaml
- tag: summary
  format: Summarize the whole text
- tag: detail
  format: Explain in detail: {prompt}
```

2. Specify the template YAML file with the `--templates` option on the command line.

```sh
tagwriting ./foobar/path --templates sample.yaml
```

### Template Format

- `tag`: The tag name to be converted in Markdown (e.g., `<summary>...</summary>`).
- `format`: The format for the prompt after conversion. `{prompt}` will be replaced by the inner text of the tag.

#### Example

In your Markdown file:

```markdown
<detail>Please explain this story.</detail>
```

Will be converted according to the template:

```markdown
<prompt>Explain in detail: Please explain this story.</prompt>
```

and then processed by the LLM.

---

## Custom Template Tag Example

You can define your own tags in the YAML template file. For example:

```yaml
- tag: highlight
  format: Highlight this: {prompt}
```

This allows you to use `<highlight>Important point</highlight>` in your text, which will be converted to `<prompt>Highlight this: Important point</prompt>`.

---

## More Usage Examples

- You can ignore files or patterns by specifying them in the YAML template under the `ignore` key.
- You can chain prompts for stepwise text generation.
- Works with any editor that reloads files on change.

---

## Design Philosophy & Tips

- **Simplicity:** Tag detection → Send context → Replace with result
- **Stateless:** File-based, minimal environment dependency
- **Minimal Interface:** UI-independent, works with any tool
- **Direct editing:** All changes are written directly to the file, making it compatible with any editor or workflow.
- **Extensible:** Easily add new tags or processing rules via YAML templates.

---

## 🧪 Development

TagWriting is currently under experimental development. The design principles are:

- **Simplicity**: Tag detection → Send context → Replace with result
- **Stateless**: File-based, minimal environment dependency
- **Minimal Interface**: UI-independent, works with any tool

---

## ⚡ Features

- Asynchronous requests to LLMs or external APIs
- Real-time error and status output to CLI
- Results are written directly to files (reprocessed on save)

---

## ⚙️ System Overview

- Watches for file changes and automatically processes tagged prompts
- Supports prompt chaining for advanced workflows
- CLI-first, but can be integrated with any editor or tool

---

## License

MIT
