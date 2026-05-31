"""
nestifypy.input.types — InputResult: a rich, typed wrapper around captured input.

InputResult is what you get back from ask(...). It holds the raw string and
exposes every conversion/accessor as a property or method.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Generic, Iterable, TypeVar, overload

from nestifypy.input.exceptions import InputConversionError, InputValidationError

T = TypeVar("T")

# Alias builtins before any shadowing occurs in this module
builtins_list  = list
builtins_tuple = tuple  # type: ignore[assignment]
builtins_set   = set
builtins_str   = str

_TRUTHY = {"1", "true", "yes", "y", "on", "sim", "s"}
_FALSY  = {"0", "false", "no",  "n", "off", "não", "nao"}


class InputResult:
    """
    A rich wrapper around the raw string captured by ``ask()``.

    Type conversions raise :exc:`InputConversionError` (a subclass of
    :exc:`InputValidationError`) when conversion fails, so you can catch
    all input errors with a single ``except InputValidationError``.
    """

    def __init__(self, raw: str, prompt: str = "") -> None:
        self._raw   = raw
        self._prompt = prompt

    # ------------------------------------------------------------------ #
    # Raw / string
    # ------------------------------------------------------------------ #

    @property
    def raw(self) -> str:
        """The unmodified string as entered by the user."""
        return self._raw

    @property
    def str(self) -> str:  # noqa: A003
        """Return the value as a stripped string."""
        return self._raw.strip()

    @property
    def stripped(self) -> str:
        """Alias for :attr:`str`."""
        return self.str

    # ------------------------------------------------------------------ #
    # Numeric
    # ------------------------------------------------------------------ #

    @property
    def int(self) -> int:  # noqa: A003
        """
        Convert to ``int``.

        Raises:
            InputConversionError: If the value cannot be parsed as an integer.
        """
        try:
            return int(self._raw.strip())
        except ValueError:
            raise InputConversionError(self._raw, int, self._prompt)

    @property
    def float(self) -> float:  # noqa: A003
        """
        Convert to ``float``.

        Raises:
            InputConversionError: If the value cannot be parsed as a float.
        """
        try:
            return float(self._raw.strip())
        except ValueError:
            raise InputConversionError(self._raw, float, self._prompt)

    @property
    def number(self) -> int | float:
        """
        Return an ``int`` if the value has no fractional part, else a ``float``.
        """
        f = self.float
        return int(f) if f == int(f) else f

    @property
    def positive_int(self) -> int:
        """``int`` that must be > 0."""
        n = self.int
        if n <= 0:
            raise InputValidationError(
                f"Expected a positive integer, got {n}.", self._raw, self._prompt
            )
        return n

    @property
    def non_negative_int(self) -> int:
        """``int`` that must be >= 0."""
        n = self.int
        if n < 0:
            raise InputValidationError(
                f"Expected a non-negative integer, got {n}.", self._raw, self._prompt
            )
        return n

    # ------------------------------------------------------------------ #
    # Boolean
    # ------------------------------------------------------------------ #

    @property
    def bool(self) -> bool:  # noqa: A003
        """
        Interpret the value as a boolean.

        Truthy  : ``1 true yes y on sim s``
        Falsy   : ``0 false no n off não nao``

        Raises:
            InputConversionError: For any other value.
        """
        lower = self._raw.strip().lower()
        if lower in _TRUTHY:
            return True
        if lower in _FALSY:
            return False
        raise InputConversionError(self._raw, bool, self._prompt)

    # ------------------------------------------------------------------ #
    # Collections
    # ------------------------------------------------------------------ #

    def list(  # noqa: A003
        self,
        item_type: Callable[[str], T] = builtins_str,  # type: ignore[assignment]
        separator: str = ",",
    ) -> "builtins_list[T]":
        """
        Split on *separator* and cast each element with *item_type*.

        Example::

            numbers = ask("Numbers?").list(int)   # "1, 2, 3"  → [1, 2, 3]
            tags    = ask("Tags?").list()          # "a, b, c"  → ["a", "b", "c"]
        """
        parts = [p.strip() for p in self._raw.split(separator) if p.strip()]
        result: "builtins_list[T]" = []
        for part in parts:
            try:
                result.append(item_type(part))
            except (ValueError, TypeError):
                raise InputConversionError(part, item_type if isinstance(item_type, type) else type(item_type), self._prompt)  # type: ignore[arg-type]
        return result

    def set(  # noqa: A003
        self,
        item_type: Callable[[str], T] = builtins_str,  # type: ignore[assignment]
        separator: str = ",",
    ) -> "builtins_set[T]":
        """Like :meth:`list` but returns a ``set`` (duplicates removed)."""
        return builtins_set(self.list(item_type, separator))

    def tuple(  # noqa: A003
        self,
        *item_types: Callable[[str], Any],
        separator: str = ",",
    ) -> tuple[Any, ...]:
        """
        Split and cast each element to its matching type in *item_types*.

        Example::

            x, y = ask("x,y?").tuple(float, float)
        """
        parts = [p.strip() for p in self._raw.split(separator) if p.strip()]
        if item_types and len(parts) != len(item_types):
            raise InputValidationError(
                f"Expected {len(item_types)} element(s), got {len(parts)}.",
                self._raw,
                self._prompt,
            )
        types = item_types if item_types else (str,) * len(parts)
        return builtins_tuple(t(p) for t, p in zip(types, parts))  # type: ignore[arg-type]

    @property
    def json(self) -> Any:
        """
        Parse as JSON.

        Raises:
            InputConversionError: If the value is not valid JSON.
        """
        try:
            return json.loads(self._raw.strip())
        except json.JSONDecodeError as exc:
            raise InputConversionError(self._raw, dict, self._prompt) from exc

    # ------------------------------------------------------------------ #
    # Paths
    # ------------------------------------------------------------------ #

    @property
    def path(self) -> Path:
        """Return as a ``pathlib.Path`` (expanded)."""
        return Path(os.path.expandvars(os.path.expanduser(self._raw.strip())))

    @property
    def existing_path(self) -> Path:
        """
        Like :attr:`path` but verifies the path exists.

        Raises:
            InputValidationError: If the path does not exist.
        """
        p = self.path
        if not p.exists():
            raise InputValidationError(
                f"Path does not exist: {p}", self._raw, self._prompt
            )
        return p

    @property
    def file_path(self) -> Path:
        """Like :attr:`existing_path` but also checks it is a regular file."""
        p = self.existing_path
        if not p.is_file():
            raise InputValidationError(
                f"Not a file: {p}", self._raw, self._prompt
            )
        return p

    @property
    def dir_path(self) -> Path:
        """Like :attr:`existing_path` but also checks it is a directory."""
        p = self.existing_path
        if not p.is_dir():
            raise InputValidationError(
                f"Not a directory: {p}", self._raw, self._prompt
            )
        return p

    # ------------------------------------------------------------------ #
    # Network / format
    # ------------------------------------------------------------------ #

    @property
    def email(self) -> str:
        """Validated e-mail string."""
        from nestifypy.input.validators import Validator
        err = Validator.email(self._raw)
        if err:
            raise InputValidationError(err, self._raw, self._prompt)
        return self._raw.strip().lower()

    @property
    def url(self) -> str:
        """Validated URL string."""
        from nestifypy.input.validators import Validator
        err = Validator.url(self._raw)
        if err:
            raise InputValidationError(err, self._raw, self._prompt)
        return self._raw.strip()

    # ------------------------------------------------------------------ #
    # Choice
    # ------------------------------------------------------------------ #

    def choice(
        self,
        options: Iterable[str],
        case_sensitive: bool = False,
    ) -> str:
        """
        Validate that the value is one of *options* and return the matched option
        (normalised to the original casing).

        Example::

            env = ask("Environment?").choice(["dev", "staging", "prod"])
        """
        opts = list(options)
        mapping = (
            {o: o for o in opts}
            if case_sensitive
            else {o.lower(): o for o in opts}
        )
        key = self._raw.strip() if case_sensitive else self._raw.strip().lower()
        if key not in mapping:
            raise InputValidationError(
                f"Must be one of: {', '.join(opts)}.",
                self._raw,
                self._prompt,
            )
        return mapping[key]

    # ------------------------------------------------------------------ #
    # Custom cast
    # ------------------------------------------------------------------ #

    def cast(self, fn: Callable[[str], T]) -> T:
        """
        Apply any callable to the raw string.

        Example::

            from datetime import date
            d = ask("Date (YYYY-MM-DD)?").cast(date.fromisoformat)
        """
        try:
            return fn(self._raw.strip())
        except Exception as exc:
            raise InputConversionError(
                self._raw,
                fn if isinstance(fn, type) else type(fn),  # type: ignore[arg-type]
                self._prompt,
            ) from exc

    # ------------------------------------------------------------------ #
    # Dunder helpers
    # ------------------------------------------------------------------ #

    def __str__(self) -> str:
        return self._raw

    def __repr__(self) -> str:
        return f"InputResult({self._raw!r})"

    def __bool__(self) -> bool:
        return bool(self._raw.strip())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, InputResult):
            return self._raw == other._raw
        if isinstance(other, str):
            return self._raw == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._raw)

