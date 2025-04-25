# TagWriting

TagWriting is a CLI tool that enables fast and flexible text generation by simply enclosing prompts in tags within your text files. It is designed to be simple, stateless, and editor-agnostic, making it easy to integrate into any workflow.

- [日本語](https://github.com/esehara/TagWriting/blob/main/README_ja.md)

---

## Overview

TagWriting is a tool that connects AI and humans more seamlessly through text files. By monitoring a directory, TagWriting will automatically convert text or Markdown files as soon as they are saved.

```markdown
I am TagWriting.
<prompt>Describe the best feature of TagWriting in one sentence.</prompt>
```

↓

```markdown
I am TagWriting.
You can quickly generate text just by enclosing it in tags.
```

---

## Usage

1. Edit a file such as `.md` and enclose your prompt in tags  
2. When you save, the tagged section is converted by the LLM  
3. The result is written directly to the file

---

## Why TagWriting?

### Seamless with Text Editing
Just enclose prompts directly in your text with tags. No need to stop your workflow to operate the LLM. You can leverage AI without interrupting your train of thought.

### High Readability
By explicitly writing tags, it’s clear which parts you want the AI to handle. Document history and edits are also clear.

### Flexibility & Compatibility
TagWriting directly rewrites updated text files. In theory, it works with any editor and any format. As long as your editor supports file reload, you’re ready to go—no plugins needed. Use Visual Studio Code, Vim, Emacs, etc.—whatever you like.

---

## Installation (Python)

1. Install dependencies:

```sh
pip install .
```

2. Use as a command-line tool:

```sh
tagwriting
```

---

## How to use .env

Create a `.env` file in your project directory and specify your API key, model name, and base URL as follows:

```env
API_KEY=sk-xxxxxxx
MODEL=gpt-3.5-turbo
BASE_URL=https://api.openai.com/v1
```

or 

```
TAGWRITING_API_KEY=sk-xxxxxxx
TAGWRITING_MODEL=gpt-3.5-turbo
TAGWRITING_BASE_URL=https://api.openai.com/v1
```

- The `.env` file in the directory where you run the `tagwriting` command will be loaded automatically.
- If you want to use different settings for multiple projects, prepare a separate `.env` for each directory.
- Any OpenAPI-compatible endpoint can be used (e.g., Grok, Deepseek, etc.).


# Happy Hacking!

More detail? Let's read the Japanese version in GitHub.
(Sorry, I'm Japanese and English is not my native language.)

- [README_ja.md](https://github.com/esehara/TagWriting/blob/main/README_ja.md)