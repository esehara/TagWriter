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
