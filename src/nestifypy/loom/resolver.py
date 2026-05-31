"""
nestifypy.loom.resolver
------------------------
Smart Resolution engine — implements the 4-level namespace flattening
defined in Loom Spec sections 13.1 and 13.2.

Resolution order per spec:
    1. Fully qualified path        env.database.db.main.host
    2. Module-level flattened      env.database.host   (if unique within module)
    3. Scope-level flattened       env.main.host       (if unique across all modules)
    4. Global flattened            env.port            (if unique globally)

Rules:
    - Resolution stops at the first deterministic match.
    - Ambiguity raises LoomAmbiguityError (no guessing).
    - Default scopes (*) resolve ambiguity within a module.
    - Explicit full paths always bypass flattening logic.
"""

from __future__ import annotations

from typing import Any, Optional

from nestifypy.loom.ast_nodes import ModuleNode
from nestifypy.loom.exceptions import LoomAmbiguityError, LoomScopeConflictError
from nestifypy.loom.scope import LoomValue, ScopeObject


# ─────────────────────────────────────────────────────────────────────────────
#  Internal flat index entry
# ─────────────────────────────────────────────────────────────────────────────

class _Entry:
    """One resolved value in the flat lookup index."""
    __slots__ = ("module_name", "scope_path", "key", "value", "is_default_scope")

    def __init__(
        self,
        module_name: str,
        scope_path: list[str],
        key: str,
        value: Any,
        is_default_scope: bool = False,
    ) -> None:
        self.module_name = module_name
        self.scope_path = scope_path            # e.g. ["db", "main"]
        self.key = key
        self.value = value
        self.is_default_scope = is_default_scope

    @property
    def full_path(self) -> str:
        """module.scope.scope.key"""
        return ".".join([self.module_name] + self.scope_path + [self.key])

    @property
    def scope_str(self) -> str:
        return ".".join(self.scope_path)

    def as_loom_value(self) -> LoomValue:
        return LoomValue(
            self.value,
            path=self.full_path,
            module=self.module_name,
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Resolver
# ─────────────────────────────────────────────────────────────────────────────

class Resolver:
    """
    Builds a flat index from a list of ModuleNode ASTs and resolves
    attribute-style access paths using the 4-level Smart Resolution strategy.
    """

    def __init__(self) -> None:
        # module_name → ScopeObject (built lazily)
        self._modules: dict[str, dict[str, Any]] = {}
        # Flat property index: list of all _Entry objects
        self._index: list[_Entry] = []
        # Scope objects: (module, scope_path_str) → ScopeObject
        self._scopes: dict[tuple[str, str], ScopeObject] = {}
        # Default scope per module: module_name → scope_path_str
        self._default_scopes: dict[str, str] = {}

    # ── ingestion ─────────────────────────────────────────────────────────────

    def load_module(self, module: ModuleNode) -> None:
        """
        Ingest a parsed ModuleNode into the resolver index.
        Can be called multiple times (last-write-wins per spec §22).
        """
        name = module.name
        if name not in self._modules:
            self._modules[name] = {}

        # Validate and register default scopes
        for scope in module.scopes:
            if scope.is_default:
                scope_str = scope.full_path
                # Only the first level of the path determines hierarchy
                level_key = f"{name}.{scope.path[0]}"
                if level_key in self._default_scopes and self._default_scopes[level_key] != scope_str:
                    raise LoomScopeConflictError(
                        f"Multiple default scopes at level '{scope.path[0]}' "
                        f"in module '{name}': '{self._default_scopes[level_key]}' "
                        f"and '{scope_str}'",
                        hint="Only one scope per hierarchy level may be marked as default (*)",
                    )
                self._default_scopes[level_key] = scope_str

        # Build property index and scope objects
        for scope in module.scopes:
            scope_str = scope.full_path
            props: dict[str, Any] = {}

            for prop in scope.properties:
                val = self._extract_value(prop.value)
                props[prop.key] = val

                # Add to flat index — recursively flatten nested dicts
                self._index_value(
                    module_name=name,
                    scope_path=scope.path,
                    key=prop.key,
                    value=val,
                    is_default=scope.is_default,
                )

            # Build ScopeObject
            scope_obj = ScopeObject(
                path=scope_str,
                module=name,
                properties=props,
                is_default=scope.is_default,
            )
            self._scopes[(name, scope_str)] = scope_obj
            self._modules[name][scope_str] = scope_obj

    def _extract_value(self, node: Any) -> Any:
        """Convert an AST value node to a raw Python value."""
        from nestifypy.loom.ast_nodes import ListNode, LiteralNode, MapNode
        if isinstance(node, LiteralNode):
            return node.value
        if isinstance(node, ListNode):
            return [item.value for item in node.items]
        if isinstance(node, MapNode):
            # Convert MapNode to a nested dict (preserves hierarchy)
            result: dict[str, Any] = {}
            for prop in node.properties:
                result[prop.key] = self._extract_value(prop.value)
            return result
        return node

    def _index_value(
        self,
        module_name: str,
        scope_path: list[str],
        key: str,
        value: Any,
        is_default: bool,
    ) -> None:
        """
        Add a value to the flat index, recursively flattening nested dicts.

        For a nested value like pool: { max: 10 } inside scope @database,
        this produces entries:
            - key="pool", value={max: 10}  (the dict itself, for scope-level access)
            - key="pool.max", value=10     (leaf, for deep flattened access)
        """
        # Always index the value itself (even if it's a dict)
        self._index.append(_Entry(
            module_name=module_name,
            scope_path=scope_path,
            key=key,
            value=value,
            is_default_scope=is_default,
        ))

        # Recursively flatten nested dicts
        if isinstance(value, dict):
            for sub_key, sub_val in value.items():
                self._index_value(
                    module_name=module_name,
                    scope_path=scope_path,
                    key=f"{key}.{sub_key}",
                    value=sub_val,
                    is_default=is_default,
                )

    # ── resolution ────────────────────────────────────────────────────────────

    def resolve(self, path_parts: list[str]) -> Any:
        """
        Resolve a list of path segments to a value or ScopeObject.

        Tries each resolution strategy in order per spec §13.1:
            1. Fully qualified
            2. Module-level flattened
            3. Scope-level flattened
            4. Global flattened

        Returns a LoomValue or ScopeObject.
        Raises LoomResolutionError or LoomAmbiguityError.
        """
        if not path_parts:
            from nestifypy.loom.exceptions import LoomResolutionError
            raise LoomResolutionError("Empty path")

        # ── Strategy 1: Fully qualified ──────────────────────────────────────
        result = self._try_fully_qualified(path_parts)
        if result is not None:
            return self._wrap_resolved(result)

        # ── Strategy 2: Module-level flattened ──────────────────────────────
        result = self._try_module_flattened(path_parts)
        if result is not None:
            return self._wrap_resolved(result)

        # ── Strategy 3: Scope-level flattened ───────────────────────────────
        result = self._try_scope_flattened(path_parts)
        if result is not None:
            return self._wrap_resolved(result)

        # ── Strategy 4: Global flattened ────────────────────────────────────
        result = self._try_global_flattened(path_parts)
        if result is not None:
            return self._wrap_resolved(result)

        # Nothing found
        from nestifypy.loom.exceptions import LoomResolutionError
        dotted = ".".join(path_parts)
        raise LoomResolutionError(
            f"Cannot resolve path '{dotted}'",
            hint=(
                f"No property or scope named '{dotted}' was found in any loaded module. "
                "Check your .loom files or use BoltInspector to list available paths."
            ),
        )

    def _wrap_resolved(self, result: Any) -> Any:
        from nestifypy.loom.scope import LoomValue, ScopeObject
        if isinstance(result, LoomValue) and isinstance(result.value, dict):
            return ScopeObject(
                path=result.path,
                module=result.module,
                properties=result.value,
            )
        if isinstance(result, ScopeObject):
            return result
        if isinstance(result, dict):
            return ScopeObject(
                path="",
                module="",
                properties=result,
            )
        return result

    # ── Strategy 1: module.scope_path.key ────────────────────────────────────

    def _try_fully_qualified(self, parts: list[str]) -> Optional[Any]:
        """
        Try to match parts as: module_name [scope_segments...] key.
        Also handles scope-only access (no key): module.scope_path.
        """
        if not parts:
            return None

        module_name = parts[0]
        if module_name not in self._modules:
            return None

        rest = parts[1:]
        if not rest:
            # Just module name — return a pseudo-scope of all scopes in this module?
            # Spec doesn't define this clearly; return None and fall through
            return None

        # Try longest scope match + property key
        # e.g. parts = ["database", "db", "main", "host"]
        # Try scope = "db.main", key = "host"
        for split in range(len(rest), 0, -1):
            scope_path_str = ".".join(rest[:split])
            remaining = rest[split:]

            if (module_name, scope_path_str) in self._scopes:
                scope_obj = self._scopes[(module_name, scope_path_str)]

                if not remaining:
                    # Accessing the scope itself → return ScopeObject
                    return scope_obj

                if len(remaining) == 1:
                    key = remaining[0]
                    if key in scope_obj:
                        val = object.__getattribute__(scope_obj, "_props")[key]
                        if isinstance(val, ScopeObject):
                            return val
                        return LoomValue(val, ".".join(parts), module_name)

        return None

    # ── Strategy 2: module.key (flattened within module) ─────────────────────

    def _try_module_flattened(self, parts: list[str]) -> Optional[Any]:
        """
        parts = ["database", "host"]
        Searches all entries in module "database" for key "host".
        """
        if len(parts) < 2:
            return None

        module_name = parts[0]
        if module_name not in self._modules:
            return None

        # The remaining parts form the key (possibly dotted, but typically single)
        key_parts = parts[1:]
        key = key_parts[-1]
        scope_prefix = ".".join(key_parts[:-1]) if len(key_parts) > 1 else ""

        candidates = [
            e for e in self._index
            if e.module_name == module_name and e.key == key
            and (not scope_prefix or e.scope_str == scope_prefix)
        ]

        if not candidates:
            return None

        if len(candidates) == 1:
            return candidates[0].as_loom_value()

        # Multiple candidates — check for a default scope resolution
        default_candidates = [c for c in candidates if c.is_default_scope]
        if len(default_candidates) == 1:
            return default_candidates[0].as_loom_value()

        # Ambiguous
        paths = [c.full_path for c in candidates]
        raise LoomAmbiguityError(
            f"Ambiguous path '{'.'.join(parts)}' resolves to multiple values",
            got=f"{len(candidates)} candidates: " + ", ".join(paths),
            expected="a unique property",
            hint=(
                f"Use a fully qualified path (e.g. env.{paths[0]}) "
                f"or mark one scope as default with '*' (e.g. @db.main* {{...}})"
            ),
        )

    # ── Strategy 3: scope_segment.key (cross-module scope flattening) ─────────

    def _try_scope_flattened(self, parts: list[str]) -> Optional[Any]:
        """
        parts = ["main", "host"]  →  looks for scope matching "main" across all modules.
        """
        if len(parts) < 2:
            return None

        # The last segment is the key; everything before is scope path
        key = parts[-1]
        scope_query = ".".join(parts[:-1])

        # Find all scopes whose path ends with scope_query
        candidates = []
        for (mod, scope_path_str), scope_obj in self._scopes.items():
            # Check if scope_path_str equals or ends with scope_query
            if scope_path_str == scope_query or scope_path_str.endswith("." + scope_query):
                if key in scope_obj:
                    val = object.__getattribute__(scope_obj, "_props")[key]
                    full_path = f"{mod}.{scope_path_str}.{key}"
                    candidates.append((full_path, mod, val,
                                       object.__getattribute__(scope_obj, "_is_default")))

        if not candidates:
            return None

        if len(candidates) == 1:
            full_path, mod, val, _ = candidates[0]
            return LoomValue(val, full_path, mod)

        # Check default scopes
        defaults = [c for c in candidates if c[3]]
        if len(defaults) == 1:
            full_path, mod, val, _ = defaults[0]
            return LoomValue(val, full_path, mod)

        paths = [c[0] for c in candidates]
        raise LoomAmbiguityError(
            f"Ambiguous scope-flattened path '{'.'.join(parts)}'",
            got=f"{len(candidates)} candidates: " + ", ".join(paths),
            hint=f"Use a fully qualified path or mark a default scope with '*'",
        )

    # ── Strategy 4: key (global flattening) ──────────────────────────────────

    def _try_global_flattened(self, parts: list[str]) -> Optional[Any]:
        """
        parts = ["port"]  →  searches for "port" globally across all modules.
        """
        if len(parts) != 1:
            return None

        key = parts[0]
        candidates = [e for e in self._index if e.key == key]

        if not candidates:
            return None

        if len(candidates) == 1:
            return candidates[0].as_loom_value()

        defaults = [c for c in candidates if c.is_default_scope]
        if len(defaults) == 1:
            return defaults[0].as_loom_value()

        paths = [c.full_path for c in candidates]
        raise LoomAmbiguityError(
            f"Ambiguous global path '{key}' resolves to multiple values",
            got=f"{len(candidates)} candidates: " + ", ".join(paths),
            hint=f"Use a qualified path (e.g. env.{paths[0]})",
        )

    # ── scope access ──────────────────────────────────────────────────────────

    def get_scope(self, module_name: str, scope_path: str) -> Optional[ScopeObject]:
        return self._scopes.get((module_name, scope_path))

    def all_module_names(self) -> list[str]:
        return list(self._modules.keys())

    def all_scopes(self) -> list[ScopeObject]:
        return list(self._scopes.values())

    def all_entries(self) -> list[_Entry]:
        return list(self._index)


__all__ = ["Resolver"]
