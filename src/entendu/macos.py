"""Small helpers so the command works from a macOS Shortcut, without a terminal."""
from __future__ import annotations

import subprocess
import sys


def _osascript(script: str) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return r.stdout.strip()


def _q(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def choose(labels: list[str], prompt: str) -> int | None:
    """Pick one item: a numbered list in the terminal, a dialog when launched from a Shortcut."""
    if sys.stdin and sys.stdin.isatty():
        for i, label in enumerate(labels, start=1):
            print(f"  {i}. {label}")
        answer = input(f"{prompt} [1-{len(labels)}, invio per annullare] ").strip()
        return int(answer) - 1 if answer.isdigit() and 1 <= int(answer) <= len(labels) else None
    if sys.platform == "darwin":
        picked = _osascript(f"choose from list {{{', '.join(_q(l) for l in labels)}}} with prompt {_q(prompt)}")
        return labels.index(picked) if picked in labels else None
    return 0  # non interactive and not on a Mac: take the most recent


def notify(message: str, title: str = "Entendu") -> None:
    if sys.platform == "darwin":
        _osascript(f"display notification {_q(message)} with title {_q(title)}")
    else:
        print(message)


def open_file(path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)])
