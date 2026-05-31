"""
nestifypy.input.validators — Built-in and composable validators for nestifypy.input.

All validators are plain callables: (str) -> str | None.
Return None to indicate success; return a string to indicate a validation error message.

You can compose them with Validator.all(*validators) / Validator.any(*validators).
"""

from __future__ import annotations

import re
import os
from pathlib import Path
from typing import Callable, Iterable

# A validator is a callable that receives the raw string and returns
# None (success) or an error message string.
ValidatorFn = Callable[[str], str | None]


class Validator:
    """
    Namespace of built-in validator factories and combinators.

    Examples::

        ask("Email?").validate(Validator.email).str
        ask("Port?").validate(Validator.range(1, 65535)).int
        ask("File?").validate(Validator.all(Validator.not_empty, Validator.path_exists)).path
    """

    # ------------------------------------------------------------------ #
    # Primitives
    # ------------------------------------------------------------------ #

    @staticmethod
    def not_empty(value: str) -> str | None:
        """Rejects blank / whitespace-only input."""
        if not value.strip():
            return "This field cannot be empty."
        return None

    @staticmethod
    def min_length(n: int) -> ValidatorFn:
        """Rejects strings shorter than *n* characters (after strip)."""
        def _validate(value: str) -> str | None:
            if len(value.strip()) < n:
                return f"Must be at least {n} character(s)."
            return None
        return _validate

    @staticmethod
    def max_length(n: int) -> ValidatorFn:
        """Rejects strings longer than *n* characters."""
        def _validate(value: str) -> str | None:
            if len(value) > n:
                return f"Must be at most {n} character(s)."
            return None
        return _validate

    @staticmethod
    def length(min_len: int = 0, max_len: int = 10_000) -> ValidatorFn:
        """Combines min_length and max_length into one validator."""
        return Validator.all(Validator.min_length(min_len), Validator.max_length(max_len))

    # ------------------------------------------------------------------ #
    # Numeric
    # ------------------------------------------------------------------ #

    @staticmethod
    def is_int(value: str) -> str | None:
        """Rejects non-integer strings."""
        try:
            int(value.strip())
        except ValueError:
            return f"{value!r} is not a valid integer."
        return None

    @staticmethod
    def is_float(value: str) -> str | None:
        """Rejects non-numeric strings."""
        try:
            float(value.strip())
        except ValueError:
            return f"{value!r} is not a valid number."
        return None

    @staticmethod
    def range(min_val: float, max_val: float) -> ValidatorFn:
        """Rejects numbers outside [min_val, max_val]."""
        def _validate(value: str) -> str | None:
            try:
                n = float(value.strip())
            except ValueError:
                return f"{value!r} is not a valid number."
            if not (min_val <= n <= max_val):
                return f"Must be between {min_val} and {max_val}."
            return None
        return _validate

    @staticmethod
    def positive(value: str) -> str | None:
        """Rejects non-positive numbers."""
        try:
            if float(value.strip()) <= 0:
                return "Must be a positive number."
        except ValueError:
            return f"{value!r} is not a valid number."
        return None

    # ------------------------------------------------------------------ #
    # Format / Pattern
    # ------------------------------------------------------------------ #

    @staticmethod
    def matches(pattern: str | re.Pattern, message: str = "") -> ValidatorFn:
        """Rejects strings that do not match *pattern*."""
        compiled = re.compile(pattern) if isinstance(pattern, str) else pattern
        def _validate(value: str) -> str | None:
            if not compiled.search(value):
                return message or f"Input does not match expected pattern: {compiled.pattern}"
            return None
        return _validate

    @staticmethod
    def email(value: str) -> str | None:
        """Basic RFC-5322-ish e-mail validator."""
        _EMAIL_RE = re.compile(
            r"^[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-.]+$"
        )
        if not _EMAIL_RE.match(value.strip()):
            return f"{value!r} is not a valid e-mail address."
        return None

    @staticmethod
    def url(value: str) -> str | None:
        """Validates that the string looks like an HTTP/HTTPS URL."""
        _URL_RE = re.compile(
            r"^https?://"
            r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"
            r"localhost|"
            r"\d{1,3}(?:\.\d{1,3}){3})"
            r"(?::\d+)?"
            r"(?:/?|[/?]\S+)$",
            re.IGNORECASE,
        )
        if not _URL_RE.match(value.strip()):
            return f"{value!r} is not a valid URL."
        return None

    @staticmethod
    def ip_address(value: str) -> str | None:
        """Validates IPv4 addresses."""
        import socket
        try:
            socket.inet_pton(socket.AF_INET, value.strip())
        except OSError:
            try:
                socket.inet_pton(socket.AF_INET6, value.strip())
            except OSError:
                return f"{value!r} is not a valid IP address."
        return None

    # ------------------------------------------------------------------ #
    # Filesystem
    # ------------------------------------------------------------------ #

    @staticmethod
    def path_exists(value: str) -> str | None:
        """Rejects paths that do not exist on disk."""
        if not Path(value.strip()).exists():
            return f"Path does not exist: {value!r}"
        return None

    @staticmethod
    def is_file(value: str) -> str | None:
        """Rejects paths that are not regular files."""
        if not Path(value.strip()).is_file():
            return f"Not a file: {value!r}"
        return None

    @staticmethod
    def is_dir(value: str) -> str | None:
        """Rejects paths that are not directories."""
        if not Path(value.strip()).is_dir():
            return f"Not a directory: {value!r}"
        return None

    @staticmethod
    def extension(*exts: str) -> ValidatorFn:
        """
        Rejects files whose extension is not in *exts*.

        Example::

            ask("Config file?").validate(Validator.extension(".yml", ".yaml")).path
        """
        normalised = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in exts}

        def _validate(value: str) -> str | None:
            suffix = Path(value.strip()).suffix.lower()
            if suffix not in normalised:
                return f"File must be one of: {', '.join(sorted(normalised))}."
            return None
        return _validate

    # ------------------------------------------------------------------ #
    # Security
    # ------------------------------------------------------------------ #

    @staticmethod
    def no_script_injection(value: str) -> str | None:
        """
        Rejects strings containing common script-injection patterns.
        Intended as a lightweight guard — not a full HTML sanitiser.
        """
        _PATTERNS = [
            r"<\s*script",
            r"javascript\s*:",
            r"on\w+\s*=",
            r"expression\s*\(",
            r"vbscript\s*:",
        ]
        combined = re.compile("|".join(_PATTERNS), re.IGNORECASE)
        if combined.search(value):
            return "Input contains potentially unsafe script content."
        return None

    @staticmethod
    def no_sql_injection(value: str) -> str | None:
        """
        Rejects strings containing common SQL-injection patterns.
        Intended as a lightweight guard — always parameterise your queries.
        """
        _PATTERNS = [
            r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION|TRUNCATE)\b)",
            r"(--|;|/\*|\*/)",
            r"('\s*(OR|AND)\s*'?\d*'?\s*=\s*'?\d*'?)",
        ]
        combined = re.compile("|".join(_PATTERNS), re.IGNORECASE)
        if combined.search(value):
            return "Input contains potentially unsafe SQL content."
        return None

    @staticmethod
    def no_path_traversal(value: str) -> str | None:
        """Rejects path-traversal sequences like `../` or `..\\`."""
        if re.search(r"\.\.[/\\]", value):
            return "Input contains an unsafe path-traversal sequence."
        return None

    @staticmethod
    def safe(value: str) -> str | None:
        """
        Convenience validator that combines no_script_injection,
        no_sql_injection, and no_path_traversal.
        """
        return Validator.all(
            Validator.no_script_injection,
            Validator.no_sql_injection,
            Validator.no_path_traversal,
        )(value)

    # ------------------------------------------------------------------ #
    # Combinators
    # ------------------------------------------------------------------ #

    @staticmethod
    def all(*validators: ValidatorFn) -> ValidatorFn:
        """
        Returns a validator that passes only when ALL *validators* pass.
        Returns the first error message encountered.
        """
        def _validate(value: str) -> str | None:
            for v in validators:
                result = v(value)
                if result is not None:
                    return result
            return None
        return _validate

    @staticmethod
    def any(*validators: ValidatorFn) -> ValidatorFn:
        """
        Returns a validator that passes when AT LEAST ONE of *validators* passes.
        If all fail, returns the last error message.
        """
        def _validate(value: str) -> str | None:
            last_error: str | None = None
            for v in validators:
                result = v(value)
                if result is None:
                    return None
                last_error = result
            return last_error
        return _validate

    @staticmethod
    def custom(fn: Callable[[str], bool], message: str) -> ValidatorFn:
        """
        Wrap any boolean-returning function into a ValidatorFn.

        Example::

            ask("Username?").validate(
                Validator.custom(lambda v: v.isalnum(), "Only alphanumeric characters allowed.")
            ).str
        """
        def _validate(value: str) -> str | None:
            if not fn(value):
                return message
            return None
        return _validate

    @staticmethod
    def one_of(options: Iterable[str], case_sensitive: bool = False) -> ValidatorFn:
        """Rejects values not in *options*."""
        opts = list(options)
        normalised = opts if case_sensitive else [o.lower() for o in opts]

        def _validate(value: str) -> str | None:
            cmp = value.strip() if case_sensitive else value.strip().lower()
            if cmp not in normalised:
                return f"Must be one of: {', '.join(opts)}."
            return None
        return _validate
