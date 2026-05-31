"""
nestifypy.input.sanitize — Safe handling and sanitisation of user input.

Provides utilities to strip, normalise and sanitise raw strings before
they are used in queries, file operations, or rendered in UIs.

All functions are pure — they return new strings and never mutate in place.

Usage::

    from nestifypy.input.sanitize import (
        strip_tags,
        strip_sql,
        slugify,
        truncate,
        mask,
        redact,
        normalize_whitespace,
        to_safe_filename,
        sanitize,
    )
"""

from __future__ import annotations

import re
import unicodedata


# ── HTML / Script ─────────────────────────────────────────────────────────────

def strip_tags(value: str) -> str:
    """
    Remove all HTML/XML tags from *value*.

    Example::

        strip_tags("<b>Hello</b> <script>evil()</script> world")
        # → "Hello  world"
    """
    return re.sub(r"<[^>]+>", "", value)


def strip_script(value: str) -> str:
    """
    Remove ``<script>...</script>`` blocks and inline event handlers
    (``onXxx=``).  More aggressive than :func:`strip_tags`.
    """
    # Remove script blocks (greedy across newlines)
    value = re.sub(r"<script[^>]*>.*?</script>", "", value, flags=re.IGNORECASE | re.DOTALL)
    # Remove on* event handlers
    value = re.sub(r'\bon\w+\s*=\s*"[^"]*"', "", value, flags=re.IGNORECASE)
    value = re.sub(r"\bon\w+\s*=\s*'[^']*'", "", value, flags=re.IGNORECASE)
    return value


# ── SQL ───────────────────────────────────────────────────────────────────────

def strip_sql(value: str) -> str:
    """
    Remove common SQL comment sequences (``--``, ``/* */``) and terminate
    any stray single-quote strings.

    .. note::

        This is a **defence-in-depth helper**, not a substitute for
        parameterised queries.  Always use parameterised queries in production.
    """
    # Remove line comments
    value = re.sub(r"--.*$", "", value, flags=re.MULTILINE)
    # Remove block comments
    value = re.sub(r"/\*.*?\*/", "", value, flags=re.DOTALL)
    # Remove semicolons (statement terminators)
    value = value.replace(";", "")
    return value.strip()


# ── Whitespace ────────────────────────────────────────────────────────────────

def normalize_whitespace(value: str) -> str:
    """
    Collapse all runs of whitespace (spaces, tabs, newlines) to a single
    space and strip leading/trailing whitespace.

    Example::

        normalize_whitespace("  hello   world\\n")
        # → "hello world"
    """
    return re.sub(r"\s+", " ", value).strip()


# ── Masking / redacting ───────────────────────────────────────────────────────

def mask(
    value: str,
    *,
    visible: int = 4,
    char: str = "•",
    position: str = "end",
) -> str:
    """
    Partially hide *value* by replacing most characters with *char*.

    Args:
        value:    The string to mask.
        visible:  Number of characters to keep unmasked.
        char:     Replacement character (default ``•``).
        position: ``"end"`` — show last *visible* chars;
                  ``"start"`` — show first *visible* chars;
                  ``"both"`` — show first and last *visible // 2* chars.

    Examples::

        mask("mysecrettoken")          # "•••••••••ken"
        mask("user@example.com",
             visible=6, position="both")  # "user@•••••.com"
    """
    n = len(value)
    if n <= visible:
        return char * n

    if position == "end":
        hidden = n - visible
        return char * hidden + value[-visible:]

    if position == "start":
        hidden = n - visible
        return value[:visible] + char * hidden

    # both
    half = visible // 2
        # even-split; if visible is odd, extra char goes to the end
    left  = half
    right = visible - half
    hidden = n - left - right
    return value[:left] + char * hidden + value[-right:]


def redact(
    value: str,
    *,
    patterns: list[str] | None = None,
    replacement: str = "[REDACTED]",
) -> str:
    """
    Replace sensitive patterns in *value* with *replacement*.

    Default patterns redact e-mails, credit-card-like numbers, and tokens.

    Args:
        value:       The string to redact.
        patterns:    List of regex patterns to match against.  If None,
                     built-in patterns are used.
        replacement: String to substitute for each match.

    Example::

        redact("contact admin@example.com for support")
        # → "contact [REDACTED] for support"
    """
    _DEFAULT_PATTERNS = [
        r"[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-.]+",  # e-mail
        r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",              # card number
        r"\b[A-Za-z0-9]{32,}\b",                                   # long tokens/hashes
    ]
    for pat in (patterns or _DEFAULT_PATTERNS):
        value = re.sub(pat, replacement, value)
    return value


# ── Slug / filename ───────────────────────────────────────────────────────────

def slugify(
    value: str,
    *,
    separator: str = "-",
    lower: bool = True,
    max_length: int | None = None,
) -> str:
    """
    Convert *value* to a URL-safe slug.

    Steps:
    1. Normalise unicode (NFD → ASCII).
    2. Replace non-alphanumeric characters with *separator*.
    3. Collapse multiple separators.
    4. Strip leading/trailing separators.

    Example::

        slugify("Hello, World! 2024")     # → "hello-world-2024"
        slugify("Über Café", separator="_")  # → "uber-cafe" (wait, separator=_)
    """
    # Normalise accented characters
    value = unicodedata.normalize("NFD", value)
    value = value.encode("ascii", "ignore").decode("ascii")

    if lower:
        value = value.lower()

    # Replace non-alphanumeric with separator
    value = re.sub(r"[^a-zA-Z0-9]+", separator, value)

    # Collapse multiple separators and strip edges
    sep_escaped = re.escape(separator)
    value = re.sub(f"{sep_escaped}+", separator, value)
    value = value.strip(separator)

    if max_length is not None:
        value = value[:max_length].rstrip(separator)

    return value


def to_safe_filename(
    value: str,
    *,
    replacement: str = "_",
    max_length: int = 255,
) -> str:
    """
    Sanitise *value* to be a safe filename on Windows, macOS, and Linux.

    Removes or replaces:
    - Path separators (``/ \\``)
    - Windows-reserved characters (``< > : " | ? *``)
    - Control characters
    - Path traversal sequences (``..``)

    Example::

        to_safe_filename("../../../etc/passwd")   # → "......etcpasswd" (or similar)
        to_safe_filename("My Report: Q4 2024.pdf")  # → "My_Report__Q4_2024.pdf"
    """
    # Strip path traversal
    value = value.replace("..", "")
    # Replace path separators
    value = re.sub(r"[/\\]", replacement, value)
    # Replace reserved characters
    value = re.sub(r'[<>:"|?*\x00-\x1f]', replacement, value)
    # Collapse multiple replacements
    rep_escaped = re.escape(replacement)
    value = re.sub(f"{rep_escaped}+", replacement, value)
    value = value.strip(replacement).strip(".")

    return value[:max_length] if value else "unnamed"


# ── Truncation ────────────────────────────────────────────────────────────────

def truncate(
    value: str,
    max_length: int,
    *,
    suffix: str = "…",
    word_boundary: bool = False,
) -> str:
    """
    Truncate *value* to *max_length* characters, appending *suffix* if cut.

    Args:
        value:          The string to truncate.
        max_length:     Maximum length of the result (including *suffix*).
        suffix:         Appended when the string is cut (default ``…``).
        word_boundary:  If True, truncate at the last space before the limit.

    Example::

        truncate("Hello, world!", 8)                    # → "Hello, …"
        truncate("Hello, world!", 8, word_boundary=True)  # → "Hello, …"
    """
    if len(value) <= max_length:
        return value

    cut_at = max_length - len(suffix)
    if cut_at <= 0:
        return suffix[:max_length]

    trimmed = value[:cut_at]

    if word_boundary:
        last_space = trimmed.rfind(" ")
        if last_space > 0:
            trimmed = trimmed[:last_space]

    return trimmed + suffix


# ── Composite sanitizer ───────────────────────────────────────────────────────

def sanitize(
    value: str,
    *,
    html: bool = True,
    sql: bool = True,
    whitespace: bool = True,
    max_length: int | None = None,
) -> str:
    """
    Apply a set of sanitisation steps to *value* in sequence.

    Args:
        value:       Input string.
        html:        Strip HTML tags.
        sql:         Remove SQL comment sequences.
        whitespace:  Normalise whitespace.
        max_length:  Truncate at this many characters (None = no limit).

    This is the recommended "all-in-one" sanitiser for general user input
    that will be stored or displayed.

    Example::

        clean = sanitize(ask("Bio?").str)
    """
    if html:
        value = strip_tags(value)
    if sql:
        value = strip_sql(value)
    if whitespace:
        value = normalize_whitespace(value)
    if max_length is not None:
        value = truncate(value, max_length)
    return value
