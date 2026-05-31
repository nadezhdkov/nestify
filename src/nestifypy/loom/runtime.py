"""
nestifypy.loom.runtime
-----------------------
LoomRuntime — the central runtime object for the .loom configuration system.

Provides:
    - Provider registration (file, env, custom)
    - Module loading and merging (last-write-wins)
    - Attribute-style lazy access: env.db.main.host
    - Profile-aware loading
    - Watcher registration: @env.watch("db.main.host")
    - Schema binding integration

Usage::

    from nestifypy.loom import Loom, env

    Loom.load("app.loom")
    Loom.load("database.loom", profile="prod")

    host = env.db.main.host          # LoomValue
    port = env.db.main.port.int      # 5432
    cfg  = env.db.main               # ScopeObject
"""

from __future__ import annotations

import os
import threading
from typing import Any, Callable, Optional

from nestifypy.loom.exceptions import LoomResolutionError, LoomAmbiguityError, LoomScopeConflictError
from nestifypy.loom.providers import FileProvider, Provider, SystemEnvProvider
from nestifypy.loom.resolver import Resolver
from nestifypy.loom.scope import LoomValue, ScopeObject


# ─────────────────────────────────────────────────────────────────────────────
#  EnvProxy — the lazy attribute-chain proxy
# ─────────────────────────────────────────────────────────────────────────────

class _EnvProxy:
    """
    Lazy attribute-chain proxy that delegates to the Loom resolver.

    Each attribute access builds up a path:
        env.db          → _EnvProxy(parts=["db"])
        env.db.main     → _EnvProxy(parts=["db", "main"])
        env.db.main.host → resolves via Resolver.resolve(["db", "main", "host"])

    Resolution is deferred until a leaf value is accessed.
    """

    def __init__(self, runtime: "LoomRuntime", parts: list[str]) -> None:
        # Use object.__setattr__ to avoid triggering our __setattr__
        object.__setattr__(self, "_runtime", runtime)
        object.__setattr__(self, "_parts", parts)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        runtime = object.__getattribute__(self, "_runtime")
        parts = object.__getattribute__(self, "_parts")
        new_parts = parts + [name]
        # Try to resolve immediately
        try:
            result = runtime._resolver.resolve(new_parts)
            if isinstance(result, ScopeObject):
                return _ScopeProxy(runtime, new_parts, result)
            return result
        except (LoomAmbiguityError, LoomScopeConflictError):
            raise
        except LoomResolutionError:
            # Only accumulate path if starting from root or a known module prefix
            known_modules = runtime._resolver.all_module_names()
            if not parts or parts[0] in known_modules:
                return _EnvProxy(runtime, new_parts)
            raise LoomResolutionError(
                f"Cannot resolve path \'{'.'.join(new_parts)}\'",
                hint=f"No property or scope found. Loaded modules: {known_modules}",
            )
        except Exception:
            raise

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(
            "The Loom env object is read-only. "
            "Use OverrideProvider or modify your .loom files."
        )

    def __repr__(self) -> str:
        parts = object.__getattribute__(self, "_parts")
        return f"<LoomPath: {'.'.join(parts) or 'env'}>"


class _ScopeProxy:
    """
    Proxy wrapping a ScopeObject that still supports deeper chaining.

    Behaves like a ScopeObject (delegating keys/values/items/path/module)
    but also supports further attribute access for sub-scopes.
    """

    def __init__(self, runtime: "LoomRuntime", parts: list[str], scope: ScopeObject) -> None:
        object.__setattr__(self, "_runtime", runtime)
        object.__setattr__(self, "_parts", parts)
        object.__setattr__(self, "_scope", scope)

    def __getattr__(self, name: str) -> Any:
        scope = object.__getattribute__(self, "_scope")
        runtime = object.__getattribute__(self, "_runtime")
        parts = object.__getattribute__(self, "_parts")

        # Delegate ScopeObject protocol methods
        if name in ("keys", "values", "items", "get", "path", "module", "parent"):
            return getattr(scope, name)

        # Try property on the scope
        props = object.__getattribute__(scope, "_props")
        if name in props:
            val = props[name]
            if isinstance(val, ScopeObject):
                return _ScopeProxy(runtime, parts + [name], val)
            # Auto-wrap nested dicts as ScopeObject for attribute access
            if isinstance(val, dict):
                module_name = object.__getattribute__(scope, "_module")
                scope_path = object.__getattribute__(scope, "_path")
                sub_scope = ScopeObject(
                    path=f"{scope_path}.{name}",
                    module=module_name,
                    properties=val,
                    parent=scope,
                )
                return _ScopeProxy(runtime, parts + [name], sub_scope)
            full_path = ".".join(parts + [name])
            return LoomValue(val, full_path, scope.module)

        # Fall through to deeper resolution
        new_parts = parts + [name]
        try:
            result = runtime._resolver.resolve(new_parts)
            if isinstance(result, ScopeObject):
                return _ScopeProxy(runtime, new_parts, result)
            return result
        except LoomResolutionError as e:
            raise LoomResolutionError(
                f"Property '{name}' not found in scope '{scope.path}'",
                hint=f"Available: {', '.join(scope.keys())}",
            ) from e

    def __contains__(self, key: str) -> bool:
        scope = object.__getattribute__(self, "_scope")
        return key in scope

    def __len__(self) -> int:
        scope = object.__getattribute__(self, "_scope")
        return len(scope)

    def __iter__(self):
        scope = object.__getattribute__(self, "_scope")
        return iter(scope)

    def __repr__(self) -> str:
        scope = object.__getattribute__(self, "_scope")
        return repr(scope)


# Register _ScopeProxy as a virtual subclass of ScopeObject so that
# isinstance(env.db.main, ScopeObject) returns True per spec §13.2
ScopeObject.register(_ScopeProxy)  # type: ignore

# ─────────────────────────────────────────────────────────────────────────────
#  LoomRuntime
# ─────────────────────────────────────────────────────────────────────────────

class LoomRuntime:
    """
    Central runtime for the Loom configuration system.

    Manages providers, module loading, and the resolver.
    Exposes the `env` proxy for attribute-style access.

    Usage::

        from nestifypy.loom import Loom, env

        Loom.load("app.loom")
        Loom.register_provider(SystemEnvProvider(prefix="APP_"))

        print(env.db.main.host)
    """

    def __init__(self) -> None:
        self._resolver = Resolver()
        self._providers: list[Provider] = []
        self._watchers: dict[str, list[Callable]] = {}
        self._lock = threading.Lock()
        self._loaded_files: set[str] = set()

    # ── public API ────────────────────────────────────────────────────────────

    def load(
        self,
        path: "str | list[str]",
        profile: Optional[str] = None,
    ) -> "LoomRuntime":
        """
        Load one or more .loom files, with optional profile awareness.

        Profile priority (spec §11):
            1. *.local.loom
            2. *.<profile>.loom
            3. base *.loom

        Returns self for chaining.
        """
        provider = FileProvider(path, profile=profile)
        return self.register_provider(provider)

    def register_provider(self, provider: Provider) -> "LoomRuntime":
        """
        Register a provider and immediately load its modules.

        Multiple calls merge modules (last-write-wins per spec §22).
        """
        with self._lock:
            self._providers.append(provider)
            modules = provider.load()
            for module in modules:
                self._resolver.load_module(module)
        return self

    def load_source(self, source: str, filename: str = "<string>") -> "LoomRuntime":
        """
        Parse and load .loom source text directly (useful for testing).
        """
        from nestifypy.loom.parser import parse
        module = parse(source, filename)
        with self._lock:
            self._resolver.load_module(module)
        return self

    def reload(self) -> "LoomRuntime":
        """
        Reload all registered providers from scratch.
        Useful after file changes when hot-reload is not active.
        """
        with self._lock:
            self._resolver = Resolver()
            for provider in list(self._providers):
                modules = provider.load()
                for module in modules:
                    self._resolver.load_module(module)
        return self

    # ── env proxy ─────────────────────────────────────────────────────────────

    @property
    def env(self) -> _EnvProxy:
        """Return the lazy attribute-access proxy (the `env` object)."""
        return _EnvProxy(self, [])

    # ── watchers (spec §18) ───────────────────────────────────────────────────

    def watch(self, path: str) -> Callable:
        """
        Decorator to register a callback for when a config value changes.

        Usage::

            @Loom.watch("db.main.host")
            def on_host_change(new_value):
                reconnect(new_value)

        Callbacks are invoked by hot-reload integrations or explicit
        ``notify_watchers(path, value)`` calls.
        """
        def decorator(func: Callable) -> Callable:
            with self._lock:
                if path not in self._watchers:
                    self._watchers[path] = []
                self._watchers[path].append(func)
            return func
        return decorator

    def notify_watchers(self, path: str, new_value: Any) -> None:
        """Invoke all watchers registered for a given path."""
        callbacks = self._watchers.get(path, [])
        for cb in callbacks:
            try:
                cb(new_value)
            except Exception as e:
                import warnings
                warnings.warn(f"Loom watcher error for '{path}': {e}")

    # ── schema binding ────────────────────────────────────────────────────────

    @property
    def bind(self):
        """
        Decorator factory to bind a dataclass to a Loom scope.

        Usage::

            @Loom.bind("database", scope="db.main")
            @dataclasses.dataclass
            class DbConfig:
                host: str = "localhost"
                port: int = 5432
        """
        from nestifypy.loom import schema as _schema
        _schema._set_active_runtime(self)
        return _schema.bind

    # ── introspection ─────────────────────────────────────────────────────────

    def modules(self) -> list[str]:
        """Return names of all loaded modules."""
        return self._resolver.all_module_names()

    def explain(self, path: str) -> str:
        """
        Explain how a dotted path was resolved.

        Analogous to the `nestifypy explain` CLI command (spec §24.1).

        Example::

            print(Loom.explain("db.main.host"))
        """
        parts = path.split(".")
        lines = [f"  Resolving: '{path}'"]
        try:
            result = self._resolver.resolve(parts)
            if isinstance(result, LoomValue):
                lines.append(f"  Value    : {result._value!r}")
                lines.append(f"  Full path: {result._path}")
                lines.append(f"  Module   : {result._module}")
            elif isinstance(result, ScopeObject):
                p = object.__getattribute__(result, "_path")
                m = object.__getattribute__(result, "_module")
                lines.append(f"  Type     : ScopeObject")
                lines.append(f"  Path     : {p}")
                lines.append(f"  Module   : {m}")
                lines.append(f"  Keys     : {result.keys()}")
        except Exception as e:
            lines.append(f"  Error    : {e}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        mods = self._resolver.all_module_names()
        return f"LoomRuntime(modules={mods})"


# ─────────────────────────────────────────────────────────────────────────────
#  Module-level singletons
# ─────────────────────────────────────────────────────────────────────────────

#: The default global LoomRuntime instance.
Loom = LoomRuntime()

#: The global env proxy — shortcut for Loom.env.
#: Access as: env.db.main.host
env = Loom.env


def reset() -> None:
    """Reset the global Loom instance (useful in tests)."""
    global Loom, env
    Loom = LoomRuntime()
    env = Loom.env


__all__ = ["LoomRuntime", "Loom", "env", "reset"]
