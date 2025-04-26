import os
import time
import fnmatch
from watchdog.events import FileSystemEventHandler

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
