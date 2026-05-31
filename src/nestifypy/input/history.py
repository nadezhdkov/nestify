"""
nestifypy.input.history — Persistent input history backed by a local file.

Integrates with readline (if available) to give arrow-key recall of past
inputs, just like a shell.  Falls back silently when readline is not available.

Usage::

    from nestifypy.input.history import InputHistory
    from nestifypy.input import ask

    history = InputHistory("~/.myapp/input_history")
    history.install()       # enables readline recall for ALL subsequent ask() calls

    # Or scope to a single session:
    with history.session():
        cmd = ask("Command?").str
        host = ask("Host?").str
"""

from __future__ import annotations

import os
from pathlib import Path


class InputHistory:
    """
    Persistent readline history backed by a plain-text file.

    The history file is created automatically on first use.  Each session
    appends new entries; the file is capped at *max_entries* lines to avoid
    unbounded growth.

    Args:
        path:        Path to the history file.  ``~`` is expanded.
        max_entries: Maximum number of entries to keep in the file.
    """

    def __init__(
        self,
        path: str | Path = "~/.nestifypy_input_history",
        max_entries: int = 500,
    ) -> None:
        self._path        = Path(os.path.expanduser(str(path)))
        self._max_entries = max_entries
        self._readline    = self._try_import_readline()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def install(self) -> None:
        """
        Load history from disk and enable readline recall globally.
        Call once at application startup.
        """
        if not self._readline:
            return
        rl = self._readline
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.touch(exist_ok=True)
        try:
            rl.read_history_file(str(self._path))
        except OSError:
            pass
        rl.set_history_length(self._max_entries)

    def save(self) -> None:
        """Flush current in-memory history to disk."""
        if not self._readline:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._readline.write_history_file(str(self._path))
        except OSError:
            pass

    def clear(self) -> None:
        """Erase all history from memory and from the file."""
        if self._readline:
            self._readline.clear_history()
        try:
            self._path.write_text("")
        except OSError:
            pass

    @property
    def entries(self) -> list[str]:
        """Return all current in-memory history entries (most recent last)."""
        if not self._readline:
            return []
        rl = self._readline
        return [
            rl.get_history_item(i + 1)
            for i in range(rl.get_current_history_length())
        ]

    def session(self) -> "_HistorySession":
        """
        Context manager that installs history on enter and saves on exit::

            with InputHistory("~/.app/history").session():
                name = ask("Name?").str
        """
        return _HistorySession(self)

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    @staticmethod
    def _try_import_readline():
        try:
            import readline
            return readline
        except ImportError:
            return None


class _HistorySession:
    def __init__(self, history: InputHistory) -> None:
        self._history = history

    def __enter__(self) -> InputHistory:
        self._history.install()
        return self._history

    def __exit__(self, *_) -> None:
        self._history.save()
