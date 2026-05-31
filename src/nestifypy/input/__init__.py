"""
nestifypy.input — A modern, type-safe replacement for Python's built-in input().

Usage:
    from nestifypy.input import ask

    name    = ask("Your name?").str
    age     = ask("Your age?").int
    height  = ask("Height in meters?").float
    active  = ask("Active?").bool
    numbers = ask("Numbers (comma-separated)?").list(int)
    choice  = ask("Environment?").choice(["dev", "staging", "prod"])
    secret  = ask("Password?").secret
    path    = ask("File path?").path
    email   = ask("Email?").email
    url     = ask("URL?").url
"""

from nestifypy.input.core import ask, InputBuilder
from nestifypy.input.types import InputResult
from nestifypy.input.validators import Validator
from nestifypy.input.exceptions import (
    InputValidationError,
    InputCancelledError,
    InputTimeoutError,
)

__all__ = [
    "ask",
    "InputBuilder",
    "InputResult",
    "Validator",
    "InputValidationError",
    "InputCancelledError",
    "InputTimeoutError",
]

__version__ = "0.1.0"
