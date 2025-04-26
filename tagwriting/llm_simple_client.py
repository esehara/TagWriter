import os
import requests
from rich import print
from pathlib import Path
from dotenv import load_dotenv
from tagwriting.html_client import HTMLClient
from tagwriting.utils import verbose_print

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

    def build_payload(self, system_prompt, user_prompt) -> dict:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": user_prompt}
            ],
            "timeout": 100
        }

    def build_url(self, endpoint) -> str:
        # merge base url and endpoint
        if not self.base_url.endswith('/'):
            self.base_url += '/'
        return self.base_url + endpoint
    
    def ask_ai(self, system_prompt, user_prompt):
        if not self.api_key:
            raise RuntimeError(f"API_KEY not found in {self.filepath}. ")
        try:
            print(f"[green][Process] Post request to {self.build_url('/chat/completions')}[/green]")
            payload = self.build_payload(system_prompt, user_prompt)
            verbose_print(f"[white][Info] Request: {payload}[/white]")
            completion = requests.post(
                self.build_url("chat/completions"), headers=self.build_headers(), json=payload)
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
