"""
nestifypy.input.core — InputBuilder and the top-level ask() factory.

The public surface is just one name::

    from nestifypy.input import ask

    age = ask("Your age?").int
"""

from __future__ import annotations

import getpass
import os
import sys
import threading
from typing import Any, Callable, Iterable

from nestifypy.input.exceptions import (
    InputCancelledError,
    InputTimeoutError,
    InputValidationError,
)
from nestifypy.input.types import InputResult
from nestifypy.input.validators import ValidatorFn

# ── ANSI colour helpers (degrade gracefully on non-TTY) ─────────────────────

def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_USE_COLOR = _supports_color()

_RESET  = "\033[0m"  if _USE_COLOR else ""
_BOLD   = "\033[1m"  if _USE_COLOR else ""
_DIM    = "\033[2m"  if _USE_COLOR else ""
_RED    = "\033[91m" if _USE_COLOR else ""
_YELLOW = "\033[93m" if _USE_COLOR else ""
_CYAN   = "\033[96m" if _USE_COLOR else ""
_GREEN  = "\033[92m" if _USE_COLOR else ""


def _err(msg: str) -> None:
    print(f"  {_RED}✖ {msg}{_RESET}", file=sys.stderr)


def _hint(msg: str) -> None:
    print(f"  {_DIM}{msg}{_RESET}", file=sys.stderr)


# ── InputBuilder ─────────────────────────────────────────────────────────────

class InputBuilder:
    """
    Fluent builder that configures and executes a prompt.

    Instantiate via :func:`ask`; do not instantiate directly.

    Chain configuration methods, then access a typed property or call a
    typed method to trigger the prompt::

        ask("Age?")
            .required()
            .validate(Validator.range(0, 150))
            .retry(3)
            .int

    If the final accessor is omitted and you want the raw :class:`InputResult`,
    call :meth:`prompt`::

        result = ask("Name?").required().prompt()
        print(result.str)
    """

    def __init__(self, prompt_text: str) -> None:
        self._prompt_text  : str                    = prompt_text
        self._default      : str | None             = None
        self._required     : bool                   = False
        self._secret       : bool                   = False
        self._validators   : list[ValidatorFn]      = []
        self._max_retries  : int                    = 1          # 1 = no retry
        self._timeout_secs : float | None           = None
        self._hint_text    : str | None             = None
        self._strip        : bool                   = True
        self._choices      : list[str] | None       = None
        self._multiline    : bool                   = False
        self._confirm      : bool                   = False      # ask twice

    # ------------------------------------------------------------------ #
    # Configuration API
    # ------------------------------------------------------------------ #

    def default(self, value: Any) -> "InputBuilder":
        """
        Provide a default value shown in brackets after the prompt.
        Returned when the user submits an empty line.

        Example::

            host = ask("Host?").default("localhost").str
        """
        self._default = str(value)
        return self

    def required(self, message: str = "This field is required.") -> "InputBuilder":
        """
        Mark the field as required; empty input will trigger a retry.
        """
        self._required = True
        self._validators.insert(0, lambda v: message if not v.strip() else None)
        return self

    def validate(self, *validators: ValidatorFn) -> "InputBuilder":
        """
        Attach one or more validator functions.

        A validator is ``(str) -> str | None``: return None on success or
        an error message string on failure.

        Example::

            ask("Port?").validate(Validator.range(1, 65535)).int
        """
        self._validators.extend(validators)
        return self

    def retry(self, times: int = 3) -> "InputBuilder":
        """
        Allow the user up to *times* attempts before raising
        :exc:`InputValidationError`.

        Example::

            ask("Age?").validate(Validator.is_int).retry(5).int
        """
        if times < 1:
            raise ValueError("retry(times) must be >= 1.")
        self._max_retries = times
        return self

    def timeout(self, seconds: float) -> "InputBuilder":
        """
        Raise :exc:`InputTimeoutError` if the user does not submit within
        *seconds* seconds.  Only supported on Unix-like systems.

        Example::

            ask("Continue? [y/n]").timeout(10).bool
        """
        self._timeout_secs = seconds
        return self

    def hint(self, text: str) -> "InputBuilder":
        """
        Show a dim hint line below the prompt.

        Example::

            ask("Password?").secret.hint("At least 8 characters.").str
        """
        self._hint_text = text
        return self

    def no_strip(self) -> "InputBuilder":
        """Preserve leading/trailing whitespace in the returned value."""
        self._strip = False
        return self

    def choices(self, options: Iterable[str]) -> "InputBuilder":
        """
        Restrict input to a list of options (displayed as a hint).
        Equivalent to chaining ``.validate(Validator.one_of(options))``.

        Example::

            env = ask("Environment?").choices(["dev", "staging", "prod"]).str
        """
        opts = list(options)
        self._choices = opts
        self._validators.append(
            lambda v: f"Must be one of: {', '.join(opts)}."
            if v.strip().lower() not in {o.lower() for o in opts}
            else None
        )
        return self

    def multiline(self) -> "InputBuilder":
        """
        Collect multiple lines until the user submits a blank line.
        Returns the joined string.

        Example::

            body = ask("Message (blank line to end)?").multiline().str
        """
        self._multiline = True
        return self

    def confirm(self) -> "InputBuilder":
        """
        Ask the user to type the value twice (e.g. for passwords).
        Raises :exc:`InputValidationError` if the two entries differ.
        """
        self._confirm = True
        return self

    # ------------------------------------------------------------------ #
    # Shortcuts that configure + prompt in one step
    # ------------------------------------------------------------------ #

    @property
    def secret(self) -> "InputBuilder":
        """
        Read the value without echoing (uses :func:`getpass.getpass`).

        Example::

            pwd = ask("Password?").secret.str
        """
        self._secret = True
        return self

    # ------------------------------------------------------------------ #
    # Execute — raw result
    # ------------------------------------------------------------------ #

    def prompt(self) -> InputResult:
        """
        Execute the prompt and return the captured :class:`InputResult`.

        This is the terminal method that all typed properties call internally.
        """
        for attempt in range(1, self._max_retries + 1):
            raw = self._read_input()
            if self._strip:
                raw = raw.strip()

            # Apply default
            if not raw and self._default is not None:
                raw = self._default

            # Run validators
            errors = self._run_validators(raw)
            if not errors:
                # Confirmation mode
                if self._confirm:
                    raw2 = self._read_input(override_prompt="Confirm: ")
                    if self._strip:
                        raw2 = raw2.strip()
                    if raw != raw2:
                        _err("Values do not match. Please try again.")
                        continue
                return InputResult(raw, self._prompt_text)

            for err in errors:
                _err(err)

            if attempt < self._max_retries:
                remaining = self._max_retries - attempt
                _hint(f"{'1 attempt' if remaining == 1 else f'{remaining} attempts'} remaining.")
            else:
                raise InputValidationError(
                    errors[0],
                    raw_value=raw,
                    field=self._prompt_text,
                )

        # Should not be reached
        raise InputValidationError("Max retries exceeded.", field=self._prompt_text)

    # ------------------------------------------------------------------ #
    # Typed property shortcuts
    # ------------------------------------------------------------------ #

    @property
    def str(self) -> str:  # noqa: A003
        return self.prompt().str

    @property
    def int(self) -> int:  # noqa: A003
        return self.prompt().int

    @property
    def float(self) -> float:  # noqa: A003
        return self.prompt().float

    @property
    def number(self) -> int | float:
        return self.prompt().number

    @property
    def bool(self) -> bool:  # noqa: A003
        return self.prompt().bool

    @property
    def path(self):
        return self.prompt().path

    @property
    def existing_path(self):
        return self.prompt().existing_path

    @property
    def file_path(self):
        return self.prompt().file_path

    @property
    def dir_path(self):
        return self.prompt().dir_path

    @property
    def email(self) -> str:
        return self.prompt().email

    @property
    def url(self) -> str:
        return self.prompt().url

    @property
    def json(self):
        return self.prompt().json

    def list(self, item_type=str, separator: str = ","):  # noqa: A003
        return self.prompt().list(item_type, separator)

    def set(self, item_type=str, separator: str = ","):  # noqa: A003
        return self.prompt().set(item_type, separator)

    def tuple(self, *item_types, separator: str = ","):  # noqa: A003
        return self.prompt().tuple(*item_types, separator=separator)

    def cast(self, fn):
        return self.prompt().cast(fn)

    def choice(self, options: Iterable[str], case_sensitive: bool = False) -> str:
        return self.prompt().choice(options, case_sensitive)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _build_prompt_string(self, override_prompt: str | None = None) -> str:
        label = override_prompt or self._prompt_text

        parts = [f"{_BOLD}{_CYAN}{label}{_RESET}"]

        if self._choices:
            parts.append(f" {_DIM}[{', '.join(self._choices)}]{_RESET}")
        elif self._default is not None:
            parts.append(f" {_DIM}({self._default}){_RESET}")

        parts.append(" ")
        return "".join(parts)

    def _read_input(self, override_prompt: str | None = None) -> str:
        prompt_str = self._build_prompt_string(override_prompt)

        if self._hint_text and not override_prompt:
            print(f"  {_DIM}↳ {self._hint_text}{_RESET}", file=sys.stderr)

        if self._secret:
            try:
                return getpass.getpass(prompt_str)
            except (EOFError, KeyboardInterrupt) as exc:
                raise InputCancelledError(self._prompt_text) from exc

        if self._multiline:
            return self._read_multiline(prompt_str)

        if self._timeout_secs is not None:
            return self._read_with_timeout(prompt_str)

        try:
            return input(prompt_str)
        except EOFError as exc:
            raise InputCancelledError(self._prompt_text) from exc
        except KeyboardInterrupt as exc:
            print()  # newline after ^C
            raise InputCancelledError(self._prompt_text) from exc

    def _read_multiline(self, prompt_str: str) -> str:
        print(prompt_str)
        lines: list[str] = []
        while True:
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                break
            if not line:
                break
            lines.append(line)
        return "\n".join(lines)

    def _read_with_timeout(self, prompt_str: str) -> str:
        if sys.platform == "win32":
            # Windows fallback — timeout not supported; just read normally.
            import warnings
            warnings.warn(
                "nestifypy.input: timeout() is not supported on Windows; "
                "the prompt will block indefinitely.",
                RuntimeWarning,
                stacklevel=3,
            )
            return input(prompt_str)

        result: list[str] = []
        exc_holder: list[BaseException] = []

        def _reader() -> None:
            try:
                result.append(input(prompt_str))
            except (EOFError, KeyboardInterrupt) as e:
                exc_holder.append(e)

        t = threading.Thread(target=_reader, daemon=True)
        t.start()
        t.join(self._timeout_secs)

        if t.is_alive():
            # Thread still blocking on input() — we cannot kill it cleanly,
            # but we can raise to the caller.
            raise InputTimeoutError(self._timeout_secs, self._prompt_text)  # type: ignore[arg-type]

        if exc_holder:
            raise InputCancelledError(self._prompt_text) from exc_holder[0]

        return result[0] if result else ""

    def _run_validators(self, value: str) -> list[str]:
        errors: list[str] = []
        for v in self._validators:
            result = v(value)
            if result is not None:
                errors.append(result)
        return errors


# ── Public factory ───────────────────────────────────────────────────────────

def ask(prompt: str) -> InputBuilder:
    """
    Create an :class:`InputBuilder` for the given *prompt* text.

    This is the single entry-point for the entire ``nestifypy.input`` package.

    Basic examples::

        name   = ask("Your name?").str
        age    = ask("Your age?").int
        height = ask("Height in meters?").float
        active = ask("Active?").bool
        hosts  = ask("Allowed hosts?").list()

    Advanced examples::

        # Validation + retry
        port = (
            ask("Port number?")
            .validate(Validator.range(1, 65_535))
            .retry(3)
            .int
        )

        # Required field with default
        host = ask("Database host?").required().default("localhost").str

        # Secret input with confirmation
        pwd = ask("Password?").secret.confirm().required().str

        # Restricted choices
        env = ask("Environment?").choices(["dev", "staging", "prod"]).str

        # Custom cast
        from datetime import date
        d = ask("Date (YYYY-MM-DD)?").cast(date.fromisoformat)
    """
    return InputBuilder(prompt)
