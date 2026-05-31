"""
nestifypy.loom.parser
----------------------
Recursive-descent parser for the .loom configuration language.

Consumes a token stream from the lexer and produces a ModuleNode AST.

Grammar (simplified):
    file         ::= module_decl? (import | scope | NEWLINE)* EOF
    module_decl  ::= DIRECTIVE("@module") LPAREN STRING (COMMA kv_arg)* RPAREN NEWLINE?
    import_decl  ::= DIRECTIVE("@import") LPAREN STRING RPAREN NEWLINE?
    scope        ::= DIRECTIVE LBRACE property* RBRACE
                   | DIRECTIVE LBRACE (property COMMA)+ RBRACE   (inline)
    property     ::= STRING COLON value NEWLINE?
    value        ::= STRING | INTEGER | FLOAT | BOOL | NULL | list_val | map_val | indented_block
    list_val     ::= LBRACKET (value (COMMA value)*)? RBRACKET
    map_val      ::= LBRACE (property (COMMA property)*)? RBRACE
    indented_block ::= NEWLINE INDENT property+ DEDENT   (YAML-style, column-based)
    kv_arg       ::= STRING EQUALS STRING   (in directive arguments)
"""

from __future__ import annotations

from typing import Optional, Union

from nestifypy.loom.ast_nodes import (
    ImportNode,
    LiteralNode,
    ListNode,
    MapNode,
    ModuleNode,
    PropertyNode,
    ScopeNode,
    SourceLocation,
)
from nestifypy.loom.exceptions import LoomSyntaxError
from nestifypy.loom.lexer import TT, Token, tokenize


# ─────────────────────────────────────────────────────────────────────────────
#  Parser
# ─────────────────────────────────────────────────────────────────────────────

class Parser:
    """
    Recursive-descent parser for .loom source text.

    Usage:
        ast = Parser(source, filename="app.loom").parse()
    """

    def __init__(self, source: str, filename: str = "<string>") -> None:
        self._source = source
        self._filename = filename
        self._lines = source.splitlines()
        self._tokens = tokenize(source, filename)
        self._pos = 0
        # Detect mixed tabs/spaces in source
        self._check_indentation_consistency()

    # ── indentation consistency check ────────────────────────────────────────

    def _check_indentation_consistency(self) -> None:
        """Verify no line mixes tabs and spaces in its leading whitespace."""
        for i, line in enumerate(self._lines):
            if not line.strip():
                continue
            leading = line[: len(line) - len(line.lstrip())]
            if "\t" in leading and " " in leading:
                raise LoomSyntaxError(
                    "Mixed tabs and spaces in indentation",
                    filename=self._filename,
                    line=i + 1,
                    column=1,
                    source_lines=self._lines,
                    got="mixed tabs and spaces",
                    expected="consistent indentation (spaces only or tabs only)",
                    hint="Use spaces or tabs consistently — do not mix them.",
                )

    # ── token navigation ─────────────────────────────────────────────────────

    def _peek(self, offset: int = 0) -> Token:
        idx = self._pos + offset
        if idx >= len(self._tokens):
            return self._tokens[-1]  # EOF
        return self._tokens[idx]

    def _advance(self) -> Token:
        tok = self._tokens[self._pos]
        if tok.type != TT.EOF:
            self._pos += 1
        return tok

    def _skip_newlines(self) -> None:
        while self._peek().type == TT.NEWLINE:
            self._advance()

    def _expect(self, tt: TT, hint: str = "") -> Token:
        tok = self._peek()
        if tok.type != tt:
            raise LoomSyntaxError(
                f"Expected {tt.name}",
                filename=self._filename,
                line=tok.line,
                column=tok.column,
                source_lines=self._lines,
                got=repr(tok.raw) if tok.raw else tok.type.name,
                expected=tt.name,
                hint=hint or None,
            )
        return self._advance()

    def _loc(self, tok: Token) -> SourceLocation:
        return SourceLocation(self._filename, tok.line, tok.column)

    def _error(self, message: str, tok: Optional[Token] = None,
                got: str = "", expected: str = "", hint: str = "") -> LoomSyntaxError:
        t = tok or self._peek()
        return LoomSyntaxError(
            message,
            filename=self._filename,
            line=t.line,
            column=t.column,
            source_lines=self._lines,
            got=got or (repr(t.raw) if t.raw else t.type.name),
            expected=expected or None,
            hint=hint or None,
        )

    # ── top-level ─────────────────────────────────────────────────────────────

    def parse(self) -> ModuleNode:
        """Parse the entire source and return a ModuleNode."""
        self._skip_newlines()

        # Optional @module declaration
        module_name = "<anonymous>"
        module_env: Optional[str] = None

        if self._peek().type == TT.DIRECTIVE and self._peek().value == "@module":
            module_name, module_env = self._parse_module_decl()
            self._skip_newlines()

        scopes: list[ScopeNode] = []
        imports: list[ImportNode] = []

        while self._peek().type != TT.EOF:
            self._skip_newlines()
            tok = self._peek()

            if tok.type == TT.EOF:
                break

            if tok.type == TT.DIRECTIVE:
                raw = str(tok.value)

                if raw == "@module":
                    raise self._error(
                        "@module must appear only once at the top of the file",
                        tok, hint="Remove the duplicate @module declaration."
                    )
                elif raw == "@import":
                    imports.append(self._parse_import())
                else:
                    scopes.append(self._parse_scope())
            elif tok.type == TT.NEWLINE:
                self._advance()
            else:
                raise self._error(
                    "Unexpected token at top level",
                    tok,
                    expected="a directive (@module, @import, @scope...) or end of file",
                    hint="Top-level statements must be directives starting with '@'.",
                )

        return ModuleNode(
            name=module_name,
            env=module_env,
            scopes=scopes,
            imports=imports,
            filename=self._filename,
        )

    # ── @module ───────────────────────────────────────────────────────────────

    def _parse_module_decl(self) -> tuple[str, Optional[str]]:
        """Parse @module("name") or @module("name", env="prod")."""
        self._advance()  # consume @module
        self._expect(TT.LPAREN, hint='Module declaration must be followed by parentheses, e.g. @module("app")')
        name_tok = self._expect(TT.STRING, hint='Module name must be a string, e.g. @module("database")')
        name = str(name_tok.value)
        env: Optional[str] = None

        # Optional: , env="prod"
        if self._peek().type == TT.COMMA:
            self._advance()  # consume comma
            key_tok = self._peek()
            if key_tok.type != TT.STRING or str(key_tok.value) != "env":
                raise self._error(
                    'Only "env" is supported as a keyword argument in @module',
                    key_tok,
                    expected='"env"',
                    hint='Example: @module("database", env="prod")',
                )
            self._advance()  # key
            self._expect(TT.COLON, hint='Use colon after argument name: env: "prod"')
            val_tok = self._expect(TT.STRING, hint='Environment must be a string: env: "prod"')
            env = str(val_tok.value)

        self._expect(TT.RPAREN, hint="Close the module declaration with ')'")
        return name, env

    # ── @import ───────────────────────────────────────────────────────────────

    def _parse_import(self) -> ImportNode:
        """Parse @import("path/to/file.loom")."""
        tok = self._advance()  # @import
        loc = self._loc(tok)
        self._expect(TT.LPAREN, hint='@import must be followed by a path in parentheses')
        path_tok = self._expect(TT.STRING, hint='@import expects a file path string')
        self._expect(TT.RPAREN)
        return ImportNode(path=str(path_tok.value), loc=loc)

    # ── @scope ────────────────────────────────────────────────────────────────

    def _parse_scope(self) -> ScopeNode:
        """
        Parse a scope directive and its body.

        Handles:
            @db.main { ... }          block syntax
            @db.main { k: v, k: v }  inline syntax
            @db.main* { ... }         default scope
        """
        dir_tok = self._advance()  # @scope.path or @scope.path*
        loc = self._loc(dir_tok)
        raw = str(dir_tok.value)   # e.g. "@db.main*"

        is_default = raw.endswith("*")
        path_str = raw.lstrip("@").rstrip("*")
        path_parts = path_str.split(".")

        if not all(part for part in path_parts):
            raise self._error(
                f"Invalid scope path: {raw!r}",
                dir_tok,
                hint="Scope paths must be dot-separated identifiers, e.g. @db.main",
            )

        self._skip_newlines()
        self._expect(TT.LBRACE, hint=f"Scope '{raw}' must be followed by a '{{' block")
        self._skip_newlines()

        properties = self._parse_scope_body()

        self._skip_newlines()
        self._expect(TT.RBRACE, hint=f"Close the '{raw}' scope with '}}'")

        return ScopeNode(
            path=path_parts,
            properties=properties,
            is_default=is_default,
            loc=loc,
        )

    def _parse_scope_body(self) -> list[PropertyNode]:
        """Parse all properties inside a { } block (block or inline style)."""
        properties: list[PropertyNode] = []

        while True:
            self._skip_newlines()
            tok = self._peek()

            if tok.type in (TT.RBRACE, TT.EOF):
                break

            if tok.type == TT.STRING:
                prop = self._parse_property()
                properties.append(prop)
                # After a property, accept comma (inline) or newline (block)
                if self._peek().type == TT.COMMA:
                    self._advance()
            else:
                raise self._error(
                    f"Expected a property key inside scope",
                    tok,
                    expected="a property name (e.g. host, port, debug)",
                    hint="Properties use colon notation: key: value",
                )

        return properties

    # ── property ──────────────────────────────────────────────────────────────

    def _parse_property(self) -> PropertyNode:
        """Parse a single `key: value` property, including nested objects."""
        key_tok = self._advance()  # STRING (key name)
        loc = self._loc(key_tok)
        key = str(key_tok.value)

        # Check for '=' (common mistake from .env users)
        if self._peek().type == TT.STRING and str(self._peek().raw) == "=":
            raise self._error(
                f"Property '{key}' uses '=' instead of ':'",
                self._peek(),
                got="'='",
                expected="':'",
                hint=f"Replace with: {key}: <value>",
            )

        self._expect(TT.COLON, hint=f"Property '{key}' must be followed by ':'. Example: {key}: \"value\"")

        # Determine what follows the colon
        next_tok = self._peek()

        if next_tok.type == TT.NEWLINE:
            # Could be YAML-style indented block OR just a newline before next prop
            # Check if the next non-empty token is indented deeper than key_tok
            value = self._try_parse_indented_block(key_tok)
            if value is not None:
                return PropertyNode(key=key, value=value, loc=loc)
            # Not an indented block — error, there's no value
            raise self._error(
                f"Expected a value after '{key}:'",
                next_tok,
                got="end of line",
                expected="a value, '{' for nested object, or indented block",
                hint=f"Provide a value: {key}: \"value\"  or start an indented block.",
            )

        value = self._parse_value()
        return PropertyNode(key=key, value=value, loc=loc)

    # ── value ─────────────────────────────────────────────────────────────────

    def _parse_value(self) -> Union[LiteralNode, ListNode, MapNode]:
        """Parse a scalar value, a list, or a nested map."""
        tok = self._peek()

        if tok.type == TT.LBRACKET:
            return self._parse_list()

        if tok.type == TT.LBRACE:
            return self._parse_map()

        if tok.type in (TT.STRING, TT.INTEGER, TT.FLOAT, TT.BOOL, TT.NULL):
            self._advance()
            return LiteralNode(value=tok.value, loc=self._loc(tok))

        raise self._error(
            "Expected a value",
            tok,
            expected='a string, number, boolean (true/false), null, list, or nested object { }',
            hint='String values must be quoted: key: "value"',
        )

    def _parse_map(self) -> MapNode:
        """
        Parse a nested map: { key: value, key: value }.

        Supports both inline and multi-line forms:
            { min: 2, max: 10 }
            {
                min: 2,
                max: 10
            }
        """
        open_tok = self._advance()  # {
        loc = self._loc(open_tok)
        properties: list[PropertyNode] = []

        self._skip_newlines()
        while self._peek().type != TT.RBRACE:
            if self._peek().type == TT.EOF:
                raise self._error("Unterminated nested object — missing '}'", open_tok,
                                   hint="Close the nested object with '}'")

            if self._peek().type == TT.STRING:
                prop = self._parse_property()
                properties.append(prop)
                # Accept comma separator (optional in multi-line)
                if self._peek().type == TT.COMMA:
                    self._advance()
                self._skip_newlines()
            else:
                raise self._error(
                    "Expected a property key inside nested object",
                    self._peek(),
                    expected="a property name (e.g. min, max)",
                    hint="Properties use colon notation: key: value",
                )

        self._expect(TT.RBRACE, hint="Close the nested object with '}'")
        return MapNode(properties=properties, loc=loc)

    def _try_parse_indented_block(self, key_tok: Token) -> Optional[MapNode]:
        """
        Try to parse a YAML-style indented block after 'key:\\n'.

        Returns a MapNode if the next meaningful token is indented deeper
        than key_tok. Returns None otherwise (caller should handle as error).

        Indentation rules:
        - A block starts when the next property has column > key_tok.column
        - All properties in the same block must have the same column
        - The block ends when a token at column <= key_tok.column appears
        - Inconsistent indentation within a block raises LoomSyntaxError
        """
        # Save position so we can backtrack
        saved_pos = self._pos
        key_col = key_tok.column

        # Consume the NEWLINE(s) after the colon
        while self._peek().type == TT.NEWLINE:
            self._advance()

        next_tok = self._peek()

        # If EOF, RBRACE, DIRECTIVE, or same/lesser indentation → not an indented block
        if next_tok.type in (TT.EOF, TT.RBRACE, TT.DIRECTIVE):
            self._pos = saved_pos
            return None

        if next_tok.type != TT.STRING:
            self._pos = saved_pos
            return None

        # Check indentation: next token must be deeper than the key
        if next_tok.column <= key_col:
            self._pos = saved_pos
            return None

        # We have an indented block! Record the expected indentation level
        block_col = next_tok.column
        loc = self._loc(next_tok)
        properties: list[PropertyNode] = []

        while True:
            self._skip_newlines()
            tok = self._peek()

            # End conditions
            if tok.type in (TT.EOF, TT.RBRACE, TT.DIRECTIVE):
                break

            if tok.type != TT.STRING:
                break

            # Check indentation
            if tok.column < block_col:
                # Returned to parent level or higher → end of block
                break

            if tok.column > block_col:
                # Deeper than expected — this is an error (inconsistent indentation)
                # Unless it's handled by a recursive indented block in _parse_property
                # But at this level, the first property of the block should be at block_col
                raise self._error(
                    "Inconsistent indentation inside block",
                    tok,
                    got=f"column {tok.column}",
                    expected=f"column {block_col} (same as the first property in this block)",
                    hint=f"Align all properties at the same indentation level.",
                )

            # tok.column == block_col — parse a property
            prop = self._parse_property()
            properties.append(prop)
            # Accept optional comma
            if self._peek().type == TT.COMMA:
                self._advance()

        if not properties:
            # Indented block with no properties — shouldn't happen, but backtrack
            self._pos = saved_pos
            return None

        return MapNode(properties=properties, loc=loc)

    def _parse_list(self) -> ListNode:
        """Parse a list: ["a", "b", 3]."""
        open_tok = self._advance()  # [
        loc = self._loc(open_tok)
        items: list[LiteralNode] = []

        self._skip_newlines()
        while self._peek().type != TT.RBRACKET:
            if self._peek().type == TT.EOF:
                raise self._error("Unterminated list — missing ']'", open_tok,
                                   hint="Close the list with ']'")
            val_tok = self._peek()
            if val_tok.type not in (TT.STRING, TT.INTEGER, TT.FLOAT, TT.BOOL, TT.NULL):
                raise self._error("Invalid list item", val_tok,
                                   expected="a scalar value (string, number, bool, null)")
            self._advance()
            items.append(LiteralNode(value=val_tok.value, loc=self._loc(val_tok)))
            self._skip_newlines()
            if self._peek().type == TT.COMMA:
                self._advance()
                self._skip_newlines()

        self._expect(TT.RBRACKET)
        return ListNode(items=items, loc=loc)


# ─────────────────────────────────────────────────────────────────────────────
#  Convenience function
# ─────────────────────────────────────────────────────────────────────────────

def parse(source: str, filename: str = "<string>") -> ModuleNode:
    """Parse .loom source text and return the root ModuleNode."""
    return Parser(source, filename).parse()


__all__ = ["Parser", "parse"]
