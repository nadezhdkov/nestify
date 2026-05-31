"""
nestifypy.loom.providers
-------------------------
Configuration providers for the Loom runtime.

A Provider is responsible for loading and supplying ModuleNode ASTs
to the Loom runtime. Providers can source configuration from:
    - .loom files on disk
    - System environment variables
    - Any future source (JSON, YAML, Vault, Redis, etc.)

All providers implement the Provider protocol:
    provider.load() -> list[ModuleNode]
"""

from __future__ import annotations

import glob
import os
from abc import ABC, abstractmethod
from typing import Optional

from nestifypy.loom.ast_nodes import (
    LiteralNode,
    ModuleNode,
    PropertyNode,
    ScopeNode,
)
from nestifypy.loom.exceptions import LoomImportError


# ─────────────────────────────────────────────────────────────────────────────
#  Abstract base
# ─────────────────────────────────────────────────────────────────────────────

class Provider(ABC):
    """Abstract base for all Loom configuration providers."""

    @abstractmethod
    def load(self) -> list[ModuleNode]:
        """Load and return a list of ModuleNode ASTs."""
        ...

    @property
    def name(self) -> str:
        return self.__class__.__name__


# ─────────────────────────────────────────────────────────────────────────────
#  FileProvider
# ─────────────────────────────────────────────────────────────────────────────

class FileProvider(Provider):
    """
    Load configuration from one or more .loom files on disk.

    Supports:
        - Single file:        FileProvider("app.loom")
        - Glob pattern:       FileProvider("./modules/*.loom")
        - Multiple paths:     FileProvider(["app.loom", "db.loom"])
        - Profile loading:    FileProvider("app.loom", profile="prod")

    Profile loading priority (per spec §11):
        1. *.local.loom
        2. *.<profile>.loom
        3. base *.loom

    Imports (@import directives) are resolved recursively, with cycle detection.
    """

    # Class-level cache for discovered files
    # Key: (base_dir, pattern) -> resolved absolute path
    _discovery_cache: dict[tuple[str, str], str] = {}

    def __init__(
        self,
        paths: "str | list[str]",
        profile: Optional[str] = None,
        base_dir: Optional[str] = None,
    ) -> None:
        if isinstance(paths, str):
            paths = [paths]
        self._paths = paths
        self._profile = profile
        self._base_dir = base_dir or os.getcwd()
        self._loaded: set[str] = set()   # cycle detection

    def load(self) -> list[ModuleNode]:
        """Resolve all configured paths and return parsed ModuleNode ASTs."""
        modules: list[ModuleNode] = []
        all_files = self._resolve_paths()

        for filepath in all_files:
            module = self._load_file(filepath)
            if module is not None:
                modules.append(module)
                # Recursively resolve @import directives
                for imp in module.imports:
                    imported = self._resolve_import(imp.path, os.path.dirname(filepath))
                    modules.extend(imported)

        return modules

    def _resolve_paths(self) -> list[str]:
        """Expand glob patterns and apply profile priority ordering."""
        resolved: list[str] = []
        for pattern in self._paths:
            full_pattern = os.path.join(self._base_dir, pattern) if not os.path.isabs(pattern) else pattern
            matched = sorted(glob.glob(full_pattern))
            if not matched and "*" not in pattern:
                # Attempt auto-discovery
                discovered = self._discover_file(pattern)
                if discovered:
                    matched = [discovered]
                else:
                    # Single exact file — will raise on load if missing
                    matched = [full_pattern]
            resolved.extend(matched)

        # Apply profile priority: local > profile > base
        return self._apply_profile_priority(resolved)

    def _discover_file(self, pattern: str) -> Optional[str]:
        cache_key = (self._base_dir, pattern)
        if cache_key in self._discovery_cache:
            return self._discovery_cache[cache_key]

        # 1. Caminho informado explicitamente
        explicit_path = pattern if os.path.isabs(pattern) else os.path.join(self._base_dir, pattern)
        explicit_path = os.path.abspath(explicit_path)

        if os.path.isfile(explicit_path):
            self._discovery_cache[cache_key] = explicit_path
            return explicit_path
        if not explicit_path.endswith(".loom"):
            explicit_loom = explicit_path + ".loom"
            if os.path.isfile(explicit_loom):
                self._discovery_cache[cache_key] = explicit_loom
                return explicit_loom

        # 2. Get target filenames to search for
        filename = os.path.basename(pattern)
        filenames = [filename]
        if not filename.endswith(".loom"):
            filenames.append(filename + ".loom")

        # Let's collect unique directories to search in order
        search_dirs = []

        # Current directory
        search_dirs.append(os.path.abspath(self._base_dir))

        # config/ directory
        search_dirs.append(os.path.abspath(os.path.join(self._base_dir, "config")))

        # Project root detection
        proj_root = self._find_project_root(self._base_dir)
        if proj_root:
            proj_root = os.path.abspath(proj_root)
            if proj_root not in search_dirs:
                search_dirs.append(proj_root)

        # Parent directories
        curr = os.path.abspath(self._base_dir)
        while True:
            parent = os.path.dirname(curr)
            if parent == curr:
                break
            parent = os.path.abspath(parent)
            if parent not in search_dirs:
                search_dirs.append(parent)
            curr = parent

        # Check each directory in order for our filenames
        for s_dir in search_dirs:
            if not os.path.isdir(s_dir):
                continue
            for fname in filenames:
                full_path = os.path.join(s_dir, fname)
                if os.path.isfile(full_path):
                    abs_path = os.path.abspath(full_path)
                    self._discovery_cache[cache_key] = abs_path
                    return abs_path

        # If still not found, perform recursive search
        start_search_dir = proj_root if proj_root else os.path.abspath(self._base_dir)
        matches = []
        for root, dirs, files in os.walk(start_search_dir):
            for fname in filenames:
                if fname in files:
                    full_path = os.path.join(root, fname)
                    matches.append(os.path.abspath(full_path))

        if matches:
            # Deterministic resolution: sort by path depth first (shallower first), then alphabetically
            matches.sort(key=lambda p: (p.count(os.sep), p))
            resolved = matches[0]
            self._discovery_cache[cache_key] = resolved
            return resolved

        return None

    def _find_project_root(self, start_dir: str) -> Optional[str]:
        curr = os.path.abspath(start_dir)
        while True:
            # Look for markers
            if any(os.path.exists(os.path.join(curr, m)) for m in (".git", "pyproject.toml", "setup.py")):
                return curr
            parent = os.path.dirname(curr)
            if parent == curr:
                break
            curr = parent
        return None

    def _apply_profile_priority(self, files: list[str]) -> list[str]:
        """
        For each base file, check if profile-specific variants exist
        and include them in priority order.

        Priority per spec §11:
            1. *.local.loom
            2. *.<profile>.loom
            3. base *.loom
        """
        result: list[str] = []
        seen: set[str] = set()

        for filepath in files:
            base, ext = os.path.splitext(filepath)
            if ext != ".loom":
                continue

            variants = []

            # Check for <base>.local.loom
            local = f"{base}.local.loom"
            if os.path.exists(local) and local not in seen:
                variants.append(local)
                seen.add(local)

            # Check for <base>.<profile>.loom
            if self._profile:
                prof = f"{base}.{self._profile}.loom"
                if os.path.exists(prof) and prof not in seen:
                    variants.append(prof)
                    seen.add(prof)

            # Base file last (lowest priority)
            if filepath not in seen:
                variants.append(filepath)
                seen.add(filepath)

            result.extend(variants)

        return result

    def _load_file(self, filepath: str) -> Optional[ModuleNode]:
        """Parse a single .loom file. Returns None if already loaded (cycle)."""
        abs_path = os.path.abspath(filepath)
        if abs_path in self._loaded:
            return None
        self._loaded.add(abs_path)

        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                source = f.read()
        except FileNotFoundError:
            raise LoomImportError(
                f"File not found: '{abs_path}'",
                hint=f"Check that the file exists and the path is correct.",
            )
        except PermissionError:
            raise LoomImportError(
                f"Permission denied reading '{abs_path}'",
                hint="Check file permissions.",
            )

        from nestifypy.loom.parser import parse
        return parse(source, filename=abs_path)

    def _resolve_import(self, import_path: str, relative_to: str) -> list[ModuleNode]:
        """Recursively resolve an @import directive."""
        if import_path.startswith("./") or import_path.startswith("../"):
            base = os.path.join(relative_to, import_path)
        else:
            base = import_path

        matched = glob.glob(base) or [base]
        modules: list[ModuleNode] = []
        for filepath in sorted(matched):
            module = self._load_file(filepath)
            if module is not None:
                modules.append(module)
                for imp in module.imports:
                    modules.extend(self._resolve_import(imp.path, os.path.dirname(filepath)))

        return modules


# ─────────────────────────────────────────────────────────────────────────────
#  SystemEnvProvider
# ─────────────────────────────────────────────────────────────────────────────

class SystemEnvProvider(Provider):
    """
    Expose system environment variables as a Loom module.

    Variables are loaded into a module named "env" (or a custom name)
    under a single scope "system".

    Example::

        os.environ["DATABASE_HOST"] = "prod.db.example.com"

        provider = SystemEnvProvider(module="env", prefix="DATABASE_")
        # Strips prefix: host → "prod.db.example.com"

        env.env.system.host  # "prod.db.example.com"
        env.host             # "prod.db.example.com" (via global flattening)

    Args:
        module:      Loom module name (default: "env")
        scope:       Scope name for all env vars (default: "system")
        prefix:      Only import variables with this prefix (stripped from key)
        lowercase:   Convert key names to lowercase (default: True)
    """

    def __init__(
        self,
        module: str = "env",
        scope: str = "system",
        prefix: str = "",
        lowercase: bool = True,
    ) -> None:
        self._module_name = module
        self._scope_name = scope
        self._prefix = prefix.upper()
        self._lowercase = lowercase

    def load(self) -> list[ModuleNode]:
        props: list[PropertyNode] = []

        for raw_key, raw_val in os.environ.items():
            if self._prefix and not raw_key.upper().startswith(self._prefix):
                continue

            key = raw_key
            if self._prefix:
                key = key[len(self._prefix):]
            if self._lowercase:
                key = key.lower()

            # Infer type
            value = self._infer(raw_val)
            props.append(PropertyNode(
                key=key,
                value=LiteralNode(value=value),
            ))

        scope = ScopeNode(
            path=[self._scope_name],
            properties=props,
        )
        module = ModuleNode(
            name=self._module_name,
            scopes=[scope],
        )
        return [module]

    @staticmethod
    def _infer(val: str) -> "str | int | float | bool | None":
        """Attempt to infer the type of an env var value."""
        if val.lower() in ("true", "yes", "on"):
            return True
        if val.lower() in ("false", "no", "off"):
            return False
        if val.lower() == "null":
            return None
        try:
            return int(val)
        except ValueError:
            pass
        try:
            return float(val)
        except ValueError:
            pass
        return val


# ─────────────────────────────────────────────────────────────────────────────
#  OverrideProvider
# ─────────────────────────────────────────────────────────────────────────────

class OverrideProvider(Provider):
    """
    In-memory provider for runtime overrides and testing.

    Allows injecting values programmatically with highest priority.

    Usage::

        overrides = OverrideProvider("database")
        overrides.set("db.main", "host", "override.example.com")
        Loom.register_provider(overrides)
    """

    def __init__(self, module_name: str = "overrides") -> None:
        self._module_name = module_name
        self._scopes: dict[str, dict[str, object]] = {}

    def set(self, scope: str, key: str, value: object) -> "OverrideProvider":
        """Set a value. Returns self for chaining."""
        if scope not in self._scopes:
            self._scopes[scope] = {}
        self._scopes[scope][key] = value
        return self

    def load(self) -> list[ModuleNode]:
        scopes: list[ScopeNode] = []
        for scope_path, props in self._scopes.items():
            path_parts = scope_path.split(".")
            prop_nodes = [
                PropertyNode(key=k, value=LiteralNode(value=v))
                for k, v in props.items()
            ]
            scopes.append(ScopeNode(path=path_parts, properties=prop_nodes))

        return [ModuleNode(name=self._module_name, scopes=scopes)]


__all__ = ["Provider", "FileProvider", "SystemEnvProvider", "OverrideProvider"]
