"""
nestifypy.input.interactive — Rich terminal-interactive prompts.

Provides cursor-driven prompts that work on any ANSI-capable terminal
(macOS, Linux, Windows 10+ with VT enabled). Falls back gracefully to the
plain ask() prompts on non-TTY environments (CI, piped input, etc.).

Public API::

    from nestifypy.input.interactive import (
        select,        # single-choice arrow-key menu
        multiselect,   # multi-choice checkbox menu
        confirm,       # styled yes/no dialog
        table_input,   # collect a list of typed rows
        progress_input # read with a live countdown timer display
    )
"""

from __future__ import annotations

import os
import sys
import shutil
import termios
import tty
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

from nestifypy.input.exceptions import InputCancelledError

T = TypeVar("T")

# ── TTY capability detection ─────────────────────────────────────────────────

def _is_interactive() -> bool:
    """True when stdin and stdout are both connected to a real terminal."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def _terminal_width() -> int:
    return shutil.get_terminal_size((80, 24)).columns


# ── ANSI helpers ─────────────────────────────────────────────────────────────

_RESET      = "\033[0m"
_BOLD       = "\033[1m"
_DIM        = "\033[2m"
_HIDE_CUR   = "\033[?25l"
_SHOW_CUR   = "\033[?25h"
_CLEAR_LINE = "\033[2K\r"
_UP         = "\033[{n}A"

_GREEN  = "\033[92m"
_CYAN   = "\033[96m"
_YELLOW = "\033[93m"
_RED    = "\033[91m"
_BLUE   = "\033[94m"
_WHITE  = "\033[97m"

def _up(n: int) -> str:
    return f"\033[{n}A"

def _move_to_col(n: int) -> str:
    return f"\033[{n}G"

# ── Raw-mode keyboard reader ──────────────────────────────────────────────────

def _read_key() -> str:
    """Read a single keypress (including arrow keys) in raw mode."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            # escape sequence — read up to 2 more bytes
            ch2 = sys.stdin.read(1)
            if ch2 == "[":
                ch3 = sys.stdin.read(1)
                return f"\x1b[{ch3}"
            return ch + ch2
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ── Key constants ─────────────────────────────────────────────────────────────

_KEY_UP    = "\x1b[A"
_KEY_DOWN  = "\x1b[B"
_KEY_RIGHT = "\x1b[C"
_KEY_LEFT  = "\x1b[D"
_KEY_ENTER = "\r"
_KEY_LF    = "\n"
_KEY_SPACE = " "
_KEY_CTRL_C = "\x03"
_KEY_ESC   = "\x1b"
_KEY_A     = "a"


# ── Internal rendering helpers ────────────────────────────────────────────────

def _render_menu(
    prompt: str,
    options: list[str],
    cursor: int,
    selected: set[int] | None,        # None = single-select mode
    page_start: int,
    page_size: int,
    hint: str = "",
) -> int:
    """
    Draw the menu and return the number of lines printed (for erasure).
    """
    lines: list[str] = []

    # Header
    lines.append(f"{_BOLD}{_CYAN}{prompt}{_RESET}")
    if hint:
        lines.append(f"  {_DIM}{hint}{_RESET}")

    visible = options[page_start : page_start + page_size]
    total   = len(options)

    for i, opt in enumerate(visible):
        abs_i   = page_start + i
        active  = abs_i == cursor
        prefix  = f"{_GREEN}❯{_RESET} " if active else "  "

        if selected is not None:
            # multiselect: checkbox
            check = f"{_GREEN}◉{_RESET}" if abs_i in selected else f"{_DIM}◯{_RESET}"
            line  = f"{prefix}{check} {_BOLD if active else ''}{opt}{_RESET if active else ''}"
        else:
            # single-select: highlight current
            line = f"{prefix}{_BOLD if active else ''}{opt}{_RESET if active else ''}"

        lines.append(f"  {line}")

    # Pagination indicator
    if total > page_size:
        shown_end = min(page_start + page_size, total)
        lines.append(
            f"  {_DIM}— {page_start + 1}–{shown_end} of {total} "
            f"(↑↓ navigate, PgUp/PgDn page){_RESET}"
        )

    output = "\n".join(lines)
    sys.stdout.write(output)
    sys.stdout.flush()
    return len(lines)


def _erase_lines(n: int) -> None:
    """Move cursor up n lines and clear each one."""
    for _ in range(n):
        sys.stdout.write(f"\033[1A{_CLEAR_LINE}")
    sys.stdout.flush()


# ─────────────────────────────────────────────────────────────────────────────
# Public prompts
# ─────────────────────────────────────────────────────────────────────────────

def select(
    prompt: str,
    options: Iterable[str],
    *,
    default: int = 0,
    page_size: int = 8,
    hint: str = "↑↓ move  Enter select  Ctrl+C cancel",
) -> str:
    """
    Interactive single-choice menu using arrow keys.

    Falls back to numbered plain-text selection when not on a TTY.

    Args:
        prompt:    Question shown above the menu.
        options:   Iterable of option strings.
        default:   Index of the initially highlighted option (0-based).
        page_size: Maximum number of visible options at once.
        hint:      Keyboard hint shown below the prompt.

    Returns:
        The selected option string.

    Raises:
        InputCancelledError: On Ctrl+C.

    Example::

        env = select("Environment?", ["dev", "staging", "prod"])
    """
    opts = list(options)
    if not opts:
        raise ValueError("select() requires at least one option.")

    if not _is_interactive():
        return _fallback_select(prompt, opts, default)

    cursor     = max(0, min(default, len(opts) - 1))
    page_start = (cursor // page_size) * page_size

    sys.stdout.write(_HIDE_CUR)
    try:
        drawn = 0
        while True:
            if drawn:
                _erase_lines(drawn)
            drawn = _render_menu(prompt, opts, cursor, None, page_start, page_size, hint)
            sys.stdout.write("\n")
            drawn += 1

            key = _read_key()

            if key in (_KEY_CTRL_C, _KEY_ESC):
                sys.stdout.write(f"\n{_DIM}cancelled.{_RESET}\n")
                raise InputCancelledError(prompt)

            if key in (_KEY_ENTER, _KEY_LF):
                _erase_lines(drawn)
                choice = opts[cursor]
                sys.stdout.write(
                    f"{_BOLD}{_CYAN}{prompt}{_RESET} {_DIM}→{_RESET} {_GREEN}{choice}{_RESET}\n"
                )
                return choice

            if key == _KEY_UP and cursor > 0:
                cursor -= 1
                if cursor < page_start:
                    page_start = max(0, page_start - page_size)

            elif key == _KEY_DOWN and cursor < len(opts) - 1:
                cursor += 1
                if cursor >= page_start + page_size:
                    page_start += page_size

            # Page up / Page down (Ctrl+U / Ctrl+D also accepted)
            elif key in ("\x15",):  # Ctrl+U — page up
                page_start = max(0, page_start - page_size)
                cursor = page_start

            elif key in ("\x04",):  # Ctrl+D — page down
                page_start = min(
                    max(0, len(opts) - page_size),
                    page_start + page_size,
                )
                cursor = min(page_start, len(opts) - 1)

    finally:
        sys.stdout.write(_SHOW_CUR)
        sys.stdout.flush()


def multiselect(
    prompt: str,
    options: Iterable[str],
    *,
    defaults: Iterable[int] = (),
    min_selections: int = 0,
    max_selections: int | None = None,
    page_size: int = 8,
    hint: str = "↑↓ move  Space toggle  A all/none  Enter confirm",
) -> list[str]:
    """
    Interactive multi-choice checkbox menu.

    Falls back to comma-separated plain-text selection when not on a TTY.

    Args:
        prompt:          Question shown above the menu.
        options:         Iterable of option strings.
        defaults:        Indices pre-selected on open.
        min_selections:  Minimum number of items that must be chosen.
        max_selections:  Maximum number of items that can be chosen (None = unlimited).
        page_size:       Visible options per page.
        hint:            Keyboard hint shown below the prompt.

    Returns:
        List of selected option strings (in original order).

    Raises:
        InputCancelledError: On Ctrl+C.
        ValueError:          If min_selections is not met on confirm.

    Example::

        features = multiselect(
            "Enable features?",
            ["auth", "websocket", "scheduler", "cache"],
            defaults=[0, 2],
        )
    """
    opts     = list(options)
    selected : set[int] = set(defaults)
    cursor   = 0
    page_start = 0

    if not opts:
        raise ValueError("multiselect() requires at least one option.")

    if not _is_interactive():
        return _fallback_multiselect(prompt, opts, list(defaults))

    sys.stdout.write(_HIDE_CUR)
    try:
        drawn = 0
        while True:
            if drawn:
                _erase_lines(drawn)

            # Build hint with selection count
            count_hint = f"{len(selected)} selected"
            if max_selections:
                count_hint += f" / {max_selections} max"
            full_hint = f"{hint}  [{count_hint}]"

            drawn = _render_menu(
                prompt, opts, cursor, selected, page_start, page_size, full_hint
            )
            sys.stdout.write("\n")
            drawn += 1

            key = _read_key()

            if key in (_KEY_CTRL_C, _KEY_ESC):
                sys.stdout.write(f"\n{_DIM}cancelled.{_RESET}\n")
                raise InputCancelledError(prompt)

            if key in (_KEY_ENTER, _KEY_LF):
                if len(selected) < min_selections:
                    # Show inline error and keep looping
                    sys.stdout.write(
                        f"  {_RED}✖ Select at least {min_selections} item(s).{_RESET}\n"
                    )
                    drawn += 1
                    continue
                _erase_lines(drawn)
                chosen = [opts[i] for i in sorted(selected)]
                label  = ", ".join(chosen) if chosen else f"{_DIM}(none){_RESET}"
                sys.stdout.write(
                    f"{_BOLD}{_CYAN}{prompt}{_RESET} {_DIM}→{_RESET} {_GREEN}{label}{_RESET}\n"
                )
                return chosen

            if key == _KEY_SPACE:
                if cursor in selected:
                    selected.discard(cursor)
                elif max_selections is None or len(selected) < max_selections:
                    selected.add(cursor)

            elif key == _KEY_A:
                # Toggle all — select all if not all selected, else clear
                if len(selected) == len(opts):
                    selected.clear()
                else:
                    selected = set(range(len(opts)))
                    if max_selections is not None:
                        selected = set(list(selected)[:max_selections])

            elif key == _KEY_UP and cursor > 0:
                cursor -= 1
                if cursor < page_start:
                    page_start = max(0, page_start - page_size)

            elif key == _KEY_DOWN and cursor < len(opts) - 1:
                cursor += 1
                if cursor >= page_start + page_size:
                    page_start += page_size

    finally:
        sys.stdout.write(_SHOW_CUR)
        sys.stdout.flush()


def confirm(
    prompt: str,
    *,
    default: bool | None = None,
    style: str = "yn",
) -> bool:
    """
    Styled yes/no confirmation prompt.

    Args:
        prompt:  Question to display.
        default: Pre-selected answer shown in uppercase: True=Y, False=N,
                 None=no default (Enter not accepted without typing).
        style:   ``"yn"`` (yes/no), ``"tf"`` (true/false).

    Returns:
        True for yes/true, False for no/false.

    Raises:
        InputCancelledError: On Ctrl+C.

    Example::

        if confirm("Overwrite existing file?", default=False):
            ...
    """
    yes_words = {"y", "yes", "sim", "s", "true", "t", "1"} if style == "yn" else {"true", "t", "yes", "y", "1"}
    no_words  = {"n", "no",  "não", "nao", "false", "f", "0"}

    if style == "yn":
        options_str = (
            f"{_BOLD}Y{_RESET}/n" if default is True  else
            f"y/{_BOLD}N{_RESET}" if default is False else
            "y/n"
        )
    else:
        options_str = (
            f"{_BOLD}T{_RESET}/f" if default is True  else
            f"t/{_BOLD}F{_RESET}" if default is False else
            "t/f"
        )

    while True:
        try:
            raw = input(
                f"{_BOLD}{_CYAN}{prompt}{_RESET} [{options_str}] "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt) as exc:
            print()
            raise InputCancelledError(prompt) from exc

        if not raw and default is not None:
            return default
        if raw in yes_words:
            return True
        if raw in no_words:
            return False

        print(f"  {_RED}✖ Please enter one of: {', '.join(sorted(yes_words | no_words))}{_RESET}")


def table_input(
    prompt: str,
    columns: list[dict[str, Any]],
    *,
    min_rows: int = 1,
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    """
    Collect a list of typed rows from the user, one field at a time.

    Each column definition is a dict with keys:
        - ``name``      (str)  — column label shown to the user
        - ``key``       (str)  — key used in the returned dict
        - ``type``      (type) — Python type: str, int, float, bool (default: str)
        - ``required``  (bool) — whether the field is mandatory (default: False)
        - ``default``   (Any)  — default value if the user submits empty input
        - ``validator`` (fn)   — optional ValidatorFn for this field

    After each row the user is asked whether to add another row.
    Stops when the user declines or ``max_rows`` is reached.

    Returns:
        List of dicts, one per row entered.

    Example::

        rows = table_input(
            "Add database connections",
            columns=[
                {"name": "Host",   "key": "host",   "type": str, "required": True},
                {"name": "Port",   "key": "port",   "type": int, "default": 5432},
                {"name": "DB name","key": "db",     "type": str, "required": True},
            ],
            min_rows=1,
            max_rows=5,
        )
    """
    from nestifypy.input.core import ask
    from nestifypy.input.validators import Validator

    rows: list[dict[str, Any]] = []
    print(f"\n{_BOLD}{_CYAN}{prompt}{_RESET}")
    print(f"  {_DIM}Enter values for each row. Leave blank to use default.{_RESET}\n")

    while True:
        row_num = len(rows) + 1
        print(f"  {_YELLOW}── Row {row_num} ──{_RESET}")
        row: dict[str, Any] = {}

        for col in columns:
            name      = col.get("name", col.get("key", "field"))
            key       = col.get("key", name.lower())
            col_type  = col.get("type", str)
            required  = col.get("required", False)
            default   = col.get("default")
            validator = col.get("validator")

            builder = ask(f"  {name}")
            if required:
                builder = builder.required()
            if default is not None:
                builder = builder.default(default)
            if validator:
                builder = builder.validate(validator)

            result = builder.retry(3).prompt()

            # Type conversion
            raw = result.str
            if raw == "" and default is not None:
                row[key] = default
            else:
                try:
                    row[key] = col_type(raw) if raw else (default if default is not None else raw)
                except (ValueError, TypeError):
                    print(f"  {_RED}✖ Could not convert {raw!r} to {col_type.__name__}. Using raw string.{_RESET}")
                    row[key] = raw

        rows.append(row)
        print()

        if max_rows and len(rows) >= max_rows:
            print(f"  {_DIM}Maximum {max_rows} rows reached.{_RESET}\n")
            break

        if len(rows) >= min_rows:
            try:
                more = confirm("Add another row?", default=False)
            except InputCancelledError:
                break
            if not more:
                break
        print()

    return rows


def progress_input(
    prompt: str,
    timeout: float,
    *,
    default: str = "",
    message: str = "Auto-continuing",
) -> str:
    """
    Display a countdown alongside the prompt. If the user does not type
    anything within *timeout* seconds, return *default*.

    Only functional on Unix. On Windows, behaves like ``ask(prompt).default(default).str``.

    Args:
        prompt:   Question text.
        timeout:  Seconds to wait.
        default:  Value returned on timeout.
        message:  Text shown next to the countdown ticker.

    Returns:
        User's input string, or *default* on timeout.

    Example::

        answer = progress_input(
            "Continue with defaults?",
            timeout=10,
            default="yes",
            message="Proceeding automatically",
        )
    """
    if sys.platform == "win32" or not _is_interactive():
        from nestifypy.input.core import ask
        return ask(prompt).default(default).str

    import threading
    import select as _select

    result: list[str] = []
    cancelled = threading.Event()

    def _countdown() -> None:
        remaining = timeout
        while remaining > 0 and not cancelled.is_set():
            bar_len  = 20
            filled   = int(bar_len * remaining / timeout)
            bar      = "█" * filled + "░" * (bar_len - filled)
            sys.stdout.write(
                f"\r{_BOLD}{_CYAN}{prompt}{_RESET}  "
                f"{_DIM}[{bar}] {remaining:.0f}s — {message}{_RESET}  "
            )
            sys.stdout.flush()
            import time
            time.sleep(0.25)
            remaining -= 0.25

        if not cancelled.is_set():
            sys.stdout.write(f"\r{_CLEAR_LINE}")
            sys.stdout.flush()

    t = threading.Thread(target=_countdown, daemon=True)
    t.start()

    try:
        fd   = sys.stdin.fileno()
        ready, _, _ = _select.select([sys.stdin], [], [], timeout)
        cancelled.set()
        t.join(timeout=0.5)

        if ready:
            raw = sys.stdin.readline().rstrip("\n")
            sys.stdout.write(f"\r{_CLEAR_LINE}")
            return raw if raw else default
        else:
            sys.stdout.write(
                f"\r{_CLEAR_LINE}{_DIM}{prompt} → {default} (timed out){_RESET}\n"
            )
            return default
    except (EOFError, KeyboardInterrupt) as exc:
        cancelled.set()
        raise InputCancelledError(prompt) from exc


# ── Plain-text fallbacks (non-TTY environments) ───────────────────────────────

def _fallback_select(prompt: str, options: list[str], default: int) -> str:
    print(f"\n{prompt}")
    for i, opt in enumerate(options):
        marker = " (default)" if i == default else ""
        print(f"  {i + 1}. {opt}{marker}")

    from nestifypy.input.core import ask
    from nestifypy.input.validators import Validator

    raw = (
        ask("Enter number")
        .default(str(default + 1))
        .validate(Validator.range(1, len(options)))
        .retry(3)
        .str
    )
    return options[int(raw) - 1]


def _fallback_multiselect(
    prompt: str,
    options: list[str],
    defaults: list[int],
) -> list[str]:
    print(f"\n{prompt}")
    for i, opt in enumerate(options):
        marker = " ✓" if i in defaults else ""
        print(f"  {i + 1}. {opt}{marker}")

    from nestifypy.input.core import ask

    raw_list = (
        ask("Enter numbers separated by commas")
        .default(",".join(str(d + 1) for d in defaults))
        .list(int)
    )
    return [options[n - 1] for n in raw_list if 1 <= n <= len(options)]
