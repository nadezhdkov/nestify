"""
nestifypy.input.form — Declarative multi-field form builder.

Define a form as a dataclass-style class and collect all fields in one call::

    from nestifypy.input.form import Form, field

    class ServerConfig(Form):
        host    = field("Host",     type=str,   default="localhost")
        port    = field("Port",     type=int,   default=8080,  validator=Validator.range(1, 65535))
        debug   = field("Debug?",  type=bool,  default=False)
        db_url  = field("DB URL",  type=str,   required=True, validator=Validator.url)

    config = ServerConfig.collect()
    print(config.host, config.port)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable, ClassVar, TypeVar

from nestifypy.input.validators import ValidatorFn
from nestifypy.input.exceptions import InputCancelledError

T = TypeVar("T")

_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_CYAN   = "\033[96m"
_GREEN  = "\033[92m"
_YELLOW = "\033[93m"


# ── Field descriptor ──────────────────────────────────────────────────────────

_SENTINEL = object()


class FieldDef:
    """
    Metadata for a single form field.  Created by :func:`field`.
    """

    def __init__(
        self,
        prompt: str,
        *,
        type: type = str,  # noqa: A002
        default: Any = _SENTINEL,
        required: bool = False,
        secret: bool = False,
        validator: ValidatorFn | None = None,
        hint: str = "",
        multiline: bool = False,
    ) -> None:
        self.prompt    = prompt
        self.cast_type = type
        self._has_default = default is not _SENTINEL
        self.default   = None if not self._has_default else default
        self.required  = required
        self.secret    = secret
        self.validator = validator
        self.hint      = hint
        self.multiline = multiline

    def collect(self, label: str) -> Any:
        """Prompt the user and return the typed value."""
        from nestifypy.input.core import ask

        builder = ask(self.prompt or label)

        if self._has_default:
            builder = builder.default(str(self.default) if self.default is not None else "")
        if self.required:
            builder = builder.required()
        if self.validator:
            builder = builder.validate(self.validator)
        if self.hint:
            builder = builder.hint(self.hint)
        if self.secret:
            builder = builder.secret
        if self.multiline:
            builder = builder.multiline()

        result = builder.retry(3).prompt()

        raw = result.str
        # Apply type conversion
        if not raw and self._has_default:
            return self.default

        if self.cast_type is bool:
            return result.bool
        if self.cast_type is int:
            return result.int
        if self.cast_type is float:
            return result.float
        if self.cast_type is list:
            return result.list()
        return raw


def field(
    prompt: str,
    *,
    type: type = str,  # noqa: A002
    default: Any = _SENTINEL,
    required: bool = False,
    secret: bool = False,
    validator: ValidatorFn | None = None,
    hint: str = "",
    multiline: bool = False,
) -> Any:
    """
    Declare a form field.

    Args:
        prompt:    The prompt text shown to the user.
        type:      Python type for automatic conversion (str, int, float, bool, list).
        default:   Default value when the user submits an empty line.
        required:  If True, empty input is rejected.
        secret:    If True, input is hidden (password-style).
        validator: A :data:`ValidatorFn` to run against the raw input.
        hint:      Helper text shown below the prompt.
        multiline: If True, collect multiple lines (blank line = end).

    Example::

        class Config(Form):
            host = field("Host", default="localhost")
            port = field("Port", type=int, default=8080, validator=Validator.range(1, 65535))
    """
    return FieldDef(
        prompt,
        type=type,
        default=default,  # _SENTINEL if not provided
        required=required,
        secret=secret,
        validator=validator,
        hint=hint,
        multiline=multiline,
    )


# ── Form metaclass ────────────────────────────────────────────────────────────

class _FormMeta(type):
    """Collect FieldDef class attributes into an ordered registry."""

    def __new__(mcs, name: str, bases: tuple, ns: dict) -> "_FormMeta":
        fields: dict[str, FieldDef] = {}

        # Inherit parent fields first
        for base in bases:
            if hasattr(base, "_fields"):
                fields.update(base._fields)

        # Collect this class's fields
        for attr, value in ns.items():
            if isinstance(value, FieldDef):
                fields[attr] = value

        ns["_fields"] = fields
        return super().__new__(mcs, name, bases, ns)


# ── Form base class ───────────────────────────────────────────────────────────

class Form(metaclass=_FormMeta):
    """
    Base class for declarative input forms.

    Define fields using :func:`field` at class level, then call
    :meth:`collect` to prompt the user for all values and get back
    a populated instance::

        class DBConfig(Form):
            host = field("Host",    default="localhost")
            port = field("Port",    type=int, default=5432)
            name = field("DB name", required=True)

        cfg = DBConfig.collect()
        print(cfg.host, cfg.port, cfg.name)

    The returned object is a simple namespace with attribute access.
    """

    _fields: ClassVar[dict[str, FieldDef]]

    @classmethod
    def collect(
        cls,
        *,
        title: str = "",
        show_summary: bool = True,
    ) -> "Form":
        """
        Prompt the user for each field in declaration order.

        Args:
            title:        Optional heading printed before the first field.
            show_summary: If True, print a summary table after all fields.

        Returns:
            A Form instance with attribute access to each collected value.

        Raises:
            InputCancelledError: If the user cancels any field.
        """
        if title:
            _header = f"\n{_BOLD}{_CYAN}{'─' * 4} {title} {'─' * 4}{_RESET}"
            print(_header)

        instance = cls.__new__(cls)
        values: dict[str, Any] = {}

        for attr, field_def in cls._fields.items():
            values[attr] = field_def.collect(attr)

        # Attach collected values as instance attributes
        for attr, value in values.items():
            object.__setattr__(instance, attr, value)

        if show_summary:
            cls._print_summary(values)

        return instance

    @classmethod
    def _print_summary(cls, values: dict[str, Any]) -> None:
        """Print a formatted summary of collected values."""
        print(f"\n  {_BOLD}Summary{_RESET}")
        print(f"  {'─' * 40}")
        for attr, field_def in cls._fields.items():
            val = values.get(attr, "")
            display = "••••••••" if field_def.secret else repr(val)
            print(f"  {_DIM}{attr:<20}{_RESET} {_GREEN}{display}{_RESET}")
        print(f"  {'─' * 40}\n")

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict of all field values."""
        return {
            attr: getattr(self, attr, None)
            for attr in self._fields
        }

    def __repr__(self) -> str:
        parts = ", ".join(
            f"{k}={getattr(self, k, None)!r}"
            for k in self._fields
        )
        return f"{self.__class__.__name__}({parts})"
