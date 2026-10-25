"""测试用的 astrbot.api 顶层包 stub。"""

from __future__ import annotations


class _Logger:
    def debug(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


logger = _Logger()


class AstrBotConfig(dict):
    pass