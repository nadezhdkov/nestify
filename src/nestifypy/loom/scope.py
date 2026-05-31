"""
nestifypy.loom.scope
---------------------
ScopeObject — the runtime representation of a resolved Loom scope.

When you access `env.db.main`, you receive a ScopeObject.
It supports dict-like introspection and attribute-style property access.

Per the spec (section 13.2):
    A path targeting a Scope MUST always return a Scope Object.
    The runtime MUST NOT implicitly unwrap scopes into scalar values.
"""

from __future__ import annotations

from typing import Any, Iterator, Optional


# ─────────────────────────────────────────────────────────────────────────────
#  LoomValue — thin wrapper around a resolved scalar
# ─────────────────────────────────────────────────────────────────────────────

class LoomValue:
    """
    Wraps a resolved primitive value and provides explicit type-cast accessors.

    Example::

        v = env.db.main.port   # returns LoomValue(5432)
        v.int                  # 5432
        v.str                  # "5432"
        v.bool                 # True (truthy cast)
        int(v)                 # 5432
        str(v)                 # "5432"
    """

    def __init__(self, value: Any, path: str = "", module: str = "") -> None:
        self._value = value
        self._path = path
        self._module = module

    # ── type casts ────────────────────────────────────────────────────────────

    @property
    def int(self) -> int:
        """Cast to int."""
        try:
            return int(self._value)
        except (TypeError, ValueError) as e:
            from nestifypy.loom.exceptions import LoomTypeError
            raise LoomTypeError(
                f"Cannot cast {self._value!r} to int",
                hint=f"Path '{self._path}' has value {self._value!r} which is not numeric.",
            ) from e

    @property
    def float(self) -> float:
        """Cast to float."""
        try:
            return float(self._value)
        except (TypeError, ValueError) as e:
            from nestifypy.loom.exceptions import LoomTypeError
            raise LoomTypeError(
                f"Cannot cast {self._value!r} to float",
            ) from e

    @property
    def bool(self) -> bool:
        """Cast to bool."""
        if isinstance(self._value, bool):
            return self._value
        if isinstance(self._value, str):
            return self._value.lower() in ("true", "yes", "on", "1")
        return bool(self._value)

    @property
    def str(self) -> str:
        """Cast to str."""
        return str(self._value) if self._value is not None else ""

    @property
    def list(self) -> list:
        """Return as list (if already a list) or wrap in one."""
        if isinstance(self._value, list):
            return self._value
        return [self._value]

    # ── introspection ─────────────────────────────────────────────────────────

    @property
    def value(self) -> Any:
        """The raw Python value."""
        return self._value

    @property
    def path(self) -> str:
        return self._path

    @property
    def module(self) -> str:
        return self._module

    # ── Python protocols ──────────────────────────────────────────────────────

    def __int__(self)   -> int:   return self.int
    def __float__(self) -> float: return self.float
    def __bool__(self)  -> bool:  return self.bool
    def __str__(self)   -> str:   return self.str
    def __repr__(self)  -> str:   return f"LoomValue({self._value!r})"
    def __eq__(self, other: object) -> bool:
        if isinstance(other, LoomValue):
            return self._value == other._value
        return self._value == other
    def __hash__(self)  -> int:   return hash(self._value)


# ─────────────────────────────────────────────────────────────────────────────
#  ScopeObject
# ─────────────────────────────────────────────────────────────────────────────

from abc import ABCMeta

class ScopeObject(metaclass=ABCMeta):
    """
    Runtime representation of a resolved Loom scope.

    Supports:
        scope.host          → LoomValue
        scope["host"]       → LoomValue
        scope.keys()        → list of property names
        scope.values()      → list of LoomValue
        scope.items()       → list of (key, LoomValue)
        scope.path          → "db.main"
        scope.module        → "database"
        scope.parent        → parent ScopeObject or None
        len(scope)          → number of properties
        "host" in scope     → bool
        for k, v in scope   → iterate items

    Per spec 13.2 — a Scope Object is NEVER automatically unwrapped to a scalar.
    """

    def __init__(
        self,
        path: str,
        module: str,
        properties: dict[str, Any],
        parent: Optional["ScopeObject"] = None,
        is_default: bool = False,
    ) -> None:
        # Store in __dict__ directly to avoid triggering our __setattr__ override
        object.__setattr__(self, "_path", path)
        object.__setattr__(self, "_module", module)
        object.__setattr__(self, "_props", properties)     # {key: raw_value}
        object.__setattr__(self, "_parent", parent)
        object.__setattr__(self, "_is_default", is_default)

    # ── spec-required introspection API ───────────────────────────────────────

    @property
    def path(self) -> str:
        """Full dotted path of this scope, e.g. 'db.main'."""
        return object.__getattribute__(self, "_path")

    @property
    def module(self) -> str:
        """Name of the module this scope belongs to."""
        return object.__getattribute__(self, "_module")

    @property
    def parent(self) -> Optional["ScopeObject"]:
        """Parent ScopeObject, or None for top-level scopes."""
        return object.__getattribute__(self, "_parent")

    def keys(self) -> list[str]:
        """Return all property names in this scope."""
        return list(object.__getattribute__(self, "_props").keys())

    def values(self) -> list[LoomValue]:
        """Return all property values as LoomValue instances."""
        props = object.__getattribute__(self, "_props")
        path = object.__getattribute__(self, "_path")
        module = object.__getattribute__(self, "_module")
        return [LoomValue(v, f"{path}.{k}", module) for k, v in props.items()]

    def items(self) -> list[tuple[str, LoomValue]]:
        """Return (key, LoomValue) pairs for all properties."""
        props = object.__getattribute__(self, "_props")
        path = object.__getattribute__(self, "_path")
        module = object.__getattribute__(self, "_module")
        return [(k, LoomValue(v, f"{path}.{k}", module)) for k, v in props.items()]

    def get(self, key: str, default: Any = None) -> Any:
        """Return LoomValue for key, or default if not found."""
        props = object.__getattribute__(self, "_props")
        if key in props:
            path = object.__getattribute__(self, "_path")
            module = object.__getattribute__(self, "_module")
            return LoomValue(props[key], f"{path}.{key}", module)
        return default

    # ── attribute access ──────────────────────────────────────────────────────

    def __getattr__(self, name: str) -> Any:
        """Access a property by name: scope.host → LoomValue, scope.pool → ScopeObject."""
        props = object.__getattribute__(self, "_props")
        path = object.__getattribute__(self, "_path")
        module = object.__getattribute__(self, "_module")

        if name in props:
            val = props[name]
            if isinstance(val, ScopeObject):
                return val
            # Auto-wrap nested dicts as ScopeObject for attribute access
            if isinstance(val, dict):
                sub_scope = ScopeObject(
                    path=f"{path}.{name}",
                    module=module,
                    properties=val,
                    parent=self,
                )
                return sub_scope
            return LoomValue(val, f"{path}.{name}", module)

        from nestifypy.loom.exceptions import LoomResolutionError
        raise LoomResolutionError(
            f"Property '{name}' not found in scope '{path}'",
            hint=f"Available keys: {', '.join(props.keys()) or '(none)'}",
        )

    def __getitem__(self, key: str) -> Any:
        return self.__getattr__(key)

    def __contains__(self, key: str) -> bool:
        return key in object.__getattribute__(self, "_props")

    def __len__(self) -> int:
        return len(object.__getattribute__(self, "_props"))

    def __iter__(self) -> Iterator[tuple[str, LoomValue]]:
        return iter(self.items())

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(
            "ScopeObject is read-only. "
            "Modify the .loom file or use runtime overrides instead."
        )

    def __repr__(self) -> str:
        path = object.__getattribute__(self, "_path")
        props = object.__getattribute__(self, "_props")
        return f"ScopeObject(path={path!r}, keys={list(props.keys())})"


__all__ = ["ScopeObject", "LoomValue"]
