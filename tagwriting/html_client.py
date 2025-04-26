import requests
from bs4 import BeautifulSoup
from markdownify import markdownify
from tagwriting.utils import verbose_print  # verbose_printを利用するためimport

class HTMLClient:
    @classmethod
    def get_title(cls, url):
        response = requests.get(url, timeout=10)
        # [TODO] なんか中国語だとバグったのであとで調べる
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup.title.string

    @classmethod
    def html_to_text(cls, html_text, url_strip, simple_text) -> (str, str):
        """
        Args:
            html_text (str): HTML text
        Returns:
            -> (str, str): (HTML inner text, title)
        """
        soup = BeautifulSoup(html_text, 'html.parser')
        target = soup.find('main')
        if simple_text:
            if target:
                return target.get_text(strip=url_strip), soup.title.string
            else:
                return soup.get_text(strip=url_strip), soup.title.string
        else:
            markdown = markdownify(html_text)
            verbose_print(f"[green][Process] HTML to markdown:[/green]")
            verbose_print(f"[white][Info] Markdown: {markdown}[/white]")
            return markdown, soup.title.string
