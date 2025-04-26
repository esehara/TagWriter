import os

DEFAULT_SYSTEM_PROMPT = """
Your response will replace `@@processing@@` within the context. 
Please output text consistent with the context's integrity.

Rule:
- Do not include `@@processing@@` in your response.
- Answer the UserPrompt directly, without explanations or commentary.
{attrs_rules}
"""

DEFAULT_USER_PROMPT = """
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

class ConfigBuilder:
    @classmethod
    def build(cls, templates):
        """ 
        Setting default templates param
        """
        if templates is None:
            templates = {}

        # if None, set default
        # --> Template Settings
        if "system_prompt" not in templates:
            templates["system_prompt"] = DEFAULT_SYSTEM_PROMPT
        if "user_prompt" not in templates:
            templates["user_prompt"] = DEFAULT_USER_PROMPT
        # --> Custom Tag Settings
        if "tags" not in templates:
            templates["tags"] = []
        # --> Watch files
        if "ignore" not in templates:
            templates["ignore"] = []
        templates["default_template_target"] = False
        if "target" not in templates:
            templates["target"] = ["*.txt", "*.md", "*.markdown"]
            templates["default_template_target"] = True
        templates["ignore"] = [os.path.abspath(p) for p in templates["ignore"]]
        templates["target"] = [os.path.abspath(p) for p in templates["target"]]     
        # --> Attributes
        if "attrs" not in templates:
            templates["attrs"] = {}
        # --> History
        if "history" not in templates:
            templates["history"] = {
                "file": "{filename}.history.md", 
                "template": DEFAULT_HISTORY_TEMPLATE}
        if "hook" not in templates:
            templates["hook"] = {}

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
        #   url_source: url resource
        #     -> default: True
        if "url_source" not in templates["config"]:
            templates["config"]["url_source"] = True
        #   url_strip: when html to text, delete whitespace
        #     -> default: False
        if "url_strip" not in templates["config"]:
            templates["config"]["url_strip"] = False

        #   url_simple_text: when html to text, use simple text
        #     -> default: False
        if "url_simple_text" not in templates["config"]:
            templates["config"]["url_simple_text"] = False

        # selfpath:
        #   -> for hot reload yaml file.
        templates["selfpath"] = None

        return templates
