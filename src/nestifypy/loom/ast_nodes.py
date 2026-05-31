"""
nestifypy.loom.ast_nodes
-------------------------
Immutable AST node types produced by the Loom parser.

All nodes carry source location metadata (file, line, column)
to enable precise diagnostic error messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Union


# ─────────────────────────────────────────────────────────────────────────────
#  Source location
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SourceLocation:
    filename: str
    line: int
    column: int

    def __str__(self) -> str:
        return f"{self.filename}:{self.line}:{self.column}"


# ─────────────────────────────────────────────────────────────────────────────
#  Literal value node
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LiteralNode:
    """A primitive scalar value: str, int, float, bool, None."""
    value: Any
    loc: Optional[SourceLocation] = None

    def __repr__(self) -> str:
        return f"LiteralNode({self.value!r})"


# ─────────────────────────────────────────────────────────────────────────────
#  List node
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ListNode:
    """A list of LiteralNode values."""
    items: list[LiteralNode] = field(default_factory=list)
    loc: Optional[SourceLocation] = None

    def __repr__(self) -> str:
        return f"ListNode({self.items!r})"


# ─────────────────────────────────────────────────────────────────────────────
#  Map node (nested object)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MapNode:
    """
    A nested object value: key: { sub_key: value, ... }

    First-class AST value type — treated identically to LiteralNode
    and ListNode as a valid property value. Supports arbitrary nesting.

    Produced by three syntaxes:
        Inline:      pool: { min: 2, max: 10 }
        Multi-line:  pool: {\n  min: 2\n  max: 10\n}
        Indented:    pool:\n    min: 2\n    max: 10
    """
    properties: list["PropertyNode"] = field(default_factory=list)
    loc: Optional[SourceLocation] = None

    def __repr__(self) -> str:
        return f"MapNode(props={len(self.properties)})"


# ─────────────────────────────────────────────────────────────────────────────
#  Property node
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PropertyNode:
    """A key: value pair inside a scope or nested map."""
    key: str
    value: Union[LiteralNode, ListNode, "MapNode"]
    loc: Optional[SourceLocation] = None

    def __repr__(self) -> str:
        return f"PropertyNode({self.key!r}: {self.value!r})"


# ─────────────────────────────────────────────────────────────────────────────
#  Scope node
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ScopeNode:
    """
    A hierarchical namespace block.
    path: ["db", "main"] for @db.main { ... }
    is_default: True if declared with the * suffix (@db.main* { ... })
    """
    path: list[str]
    properties: list[PropertyNode] = field(default_factory=list)
    is_default: bool = False
    loc: Optional[SourceLocation] = None

    @property
    def full_path(self) -> str:
        return ".".join(self.path)

    def __repr__(self) -> str:
        star = "*" if self.is_default else ""
        return f"ScopeNode(@{self.full_path}{star}, props={len(self.properties)})"


# ─────────────────────────────────────────────────────────────────────────────
#  Import node
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ImportNode:
    """An @import("path") directive."""
    path: str
    loc: Optional[SourceLocation] = None

    def __repr__(self) -> str:
        return f"ImportNode({self.path!r})"


# ─────────────────────────────────────────────────────────────────────────────
#  Module node (root)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ModuleNode:
    """
    Root AST node representing a complete .loom file.

    name:    module name from @module("name")
    env:     optional environment from @module("name", env="prod")
    scopes:  all @scope { } blocks
    imports: all @import() directives
    """
    name: str
    env: Optional[str] = None
    scopes: list[ScopeNode] = field(default_factory=list)
    imports: list[ImportNode] = field(default_factory=list)
    filename: Optional[str] = None

    def __repr__(self) -> str:
        env_str = f", env={self.env!r}" if self.env else ""
        return f"ModuleNode({self.name!r}{env_str}, scopes={len(self.scopes)})"


__all__ = [
    "SourceLocation",
    "LiteralNode",
    "ListNode",
    "MapNode",
    "PropertyNode",
    "ScopeNode",
    "ImportNode",
    "ModuleNode",
]
