"""Printing and logging utilities."""

from datetime import datetime
import sys
from typing import Any, TextIO


class CustomLogger:
    """Simple print-like logger with timestamp and level styling."""

    _LEVEL_COLORS = {
        "DEBUG": "\033[90m",
        "INFO": "\033[36m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
    }
    _RESET = "\033[0m"

    def _log(self, level: str, *args: Any, **kwargs: Any) -> None:
        sep = kwargs.pop("sep", " ")
        end = kwargs.pop("end", "\n")
        file: TextIO = kwargs.pop("file", sys.stdout)
        flush = kwargs.pop("flush", False)

        if kwargs:
            raise TypeError(f"Unexpected keyword arguments: {', '.join(kwargs.keys())}")

        if not args:
            print("", end=end, file=file, flush=flush)
            return

        message = sep.join(str(arg) for arg in args)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        color = self._LEVEL_COLORS.get(level, "")
        prefix = f"{color}[{timestamp}] [{level}]{self._RESET}"

        if message:
            output = "\n".join(f"{prefix} {line}" for line in message.splitlines())
        else:
            output = prefix

        print(output, end=end, file=file, flush=flush)

    def debug(self, *args: Any, **kwargs: Any) -> None:
        self._log("DEBUG", *args, **kwargs)

    def info(self, *args: Any, **kwargs: Any) -> None:
        self._log("INFO", *args, **kwargs)

    def warning(self, *args: Any, **kwargs: Any) -> None:
        self._log("WARNING", *args, **kwargs)

    def error(self, *args: Any, **kwargs: Any) -> None:
        self._log("ERROR", *args, **kwargs)


logger = CustomLogger()


def banner(text: str, max_width: int = 120) -> str:
    """Format text into a fixed-width box-style banner."""
    if max_width < 4:
        raise ValueError("max_width must be at least 4")

    inner_width = max_width - 4

    def wrap_paragraph(paragraph: str) -> list[str]:
        if not paragraph.strip():
            return [""]

        words = paragraph.split()
        lines: list[str] = []
        current = ""

        for word in words:
            if len(word) > inner_width:
                raise ValueError(
                    f"Word '{word}' is too long for banner width {max_width}"
                )

            candidate = f"{current} {word}" if current else word
            if len(candidate) <= inner_width:
                current = candidate
            else:
                lines.append(current)
                current = word

        if current:
            lines.append(current)

        return lines

    content_lines: list[str] = []
    for paragraph in text.splitlines() or [text]:
        content_lines.extend(wrap_paragraph(paragraph))

    if not content_lines:
        content_lines = [""]

    top = f"╔{'═' * (max_width - 2)}╗"
    bottom = f"╚{'═' * (max_width - 2)}╝"
    middle = [f"║ {line.ljust(inner_width)} ║" for line in content_lines]
    return "\n".join([top, *middle, bottom])
