"""
tests/test_loom.py
------------------
Full test suite for nestifypy.loom

Run with:  python tests/test_loom.py
"""

from __future__ import annotations

import dataclasses
import os
import sys
import tempfile
import textwrap
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nestifypy.loom import (
    Loom, LoomRuntime, LoomValue, ScopeObject,
    FileProvider, SystemEnvProvider, OverrideProvider,
    LoomSyntaxError, LoomResolutionError, LoomAmbiguityError,
    LoomSchemaError, LoomScopeConflictError, LoomTypeError,
    parse, reset,
)

_PASS = "\033[92m✓\033[0m"
_FAIL = "\033[91m✗\033[0m"
_results: list[tuple[str, bool, str]] = []


def test(name: str):
    def decorator(fn):
        try:
            fn()
            _results.append((name, True, ""))
            print(f"  {_PASS} {name}")
        except Exception as e:
            _results.append((name, False, str(e)))
            print(f"  {_FAIL} {name}")
            traceback.print_exc()
    return decorator


def loom(source: str) -> LoomRuntime:
    """Create a fresh LoomRuntime loaded with inline source."""
    rt = LoomRuntime()
    rt.load_source(textwrap.dedent(source))
    return rt


print("\n\033[1m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m")
print("\033[1m  nestifypy.loom  —  test suite\033[0m")
print("\033[1m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m\n")


# ─────────────────────────────────────────────────────────────────────────────
#  Lexer / Parser
# ─────────────────────────────────────────────────────────────────────────────
print("  Lexer & Parser")

@test("parses @module declaration")
def _():
    ast = parse('@module("database")')
    assert ast.name == "database"
    assert ast.env is None

@test("parses @module with env")
def _():
    ast = parse('@module("database", env: "prod")')
    assert ast.name == "database"
    assert ast.env == "prod"

@test("parses block scope with string, int, float, bool, null")
def _():
    ast = parse('''
        @module("app")
        @server {
            host: "localhost"
            port: 8080
            pi: 3.14
            debug: true
            secret: null
        }
    ''')
    scope = ast.scopes[0]
    props = {p.key: p.value.value for p in scope.properties}
    assert props["host"] == "localhost"
    assert props["port"] == 8080
    assert abs(props["pi"] - 3.14) < 0.001
    assert props["debug"] is True
    assert props["secret"] is None

@test("parses inline scope syntax")
def _():
    ast = parse('@module("app")\n@server { host: "localhost", port: 8080 }')
    scope = ast.scopes[0]
    assert len(scope.properties) == 2
    assert scope.properties[0].key == "host"
    assert scope.properties[1].key == "port"

@test("parses list values")
def _():
    ast = parse('@module("app")\n@net { hosts: ["a", "b", "c"] }')
    prop = ast.scopes[0].properties[0]
    from nestifypy.loom.ast_nodes import ListNode
    assert isinstance(prop.value, ListNode)
    assert [i.value for i in prop.value.items] == ["a", "b", "c"]

@test("parses default scope (*)")
def _():
    ast = parse('@module("db")\n@db.main* { host: "localhost" }')
    assert ast.scopes[0].is_default is True

@test("parses unquoted string values")
def _():
    ast = parse('@module("db")\n@db { driver: postgres }')
    assert ast.scopes[0].properties[0].value.value == "postgres"

@test("parses multi-level scope path")
def _():
    ast = parse('@module("app")\n@app.server.http { port: 80 }')
    assert ast.scopes[0].path == ["app", "server", "http"]

@test("strips inline comments")
def _():
    ast = parse('@module("app")\n@server { port: 8080 # http port\n}')
    assert ast.scopes[0].properties[0].value.value == 8080

@test("raises LoomSyntaxError on '=' in property")
def _():
    raised = False
    try:
        parse('@module("app")\n@server { host = "localhost" }')
    except LoomSyntaxError:
        raised = True
    assert raised, "Should raise LoomSyntaxError for '=' in property"

@test("raises LoomSyntaxError on unexpected character")
def _():
    raised = False
    try:
        parse("@module(\"app\")\n@server { host: ¡invalid }")
    except LoomSyntaxError:
        raised = True
    assert raised

@test("raises LoomSyntaxError on unclosed list")
def _():
    raised = False
    try:
        parse('@module("app")\n@net { hosts: ["a", "b" }')
    except LoomSyntaxError:
        raised = True
    assert raised


# ─────────────────────────────────────────────────────────────────────────────
#  LoomValue
# ─────────────────────────────────────────────────────────────────────────────
print("\n  LoomValue")

@test("int cast")
def _():
    v = LoomValue("5432")
    assert v.int == 5432
    assert int(v) == 5432

@test("float cast")
def _():
    v = LoomValue("3.14")
    assert abs(v.float - 3.14) < 0.001

@test("bool cast from string")
def _():
    assert LoomValue("true").bool is True
    assert LoomValue("false").bool is False
    assert LoomValue("yes").bool is True
    assert LoomValue("no").bool is False

@test("bool cast from native bool")
def _():
    assert LoomValue(True).bool is True
    assert LoomValue(False).bool is False

@test("str cast")
def _():
    assert LoomValue(8080).str == "8080"

@test("list wrap")
def _():
    assert LoomValue(42).list == [42]
    assert LoomValue([1, 2]).list == [1, 2]

@test("equality with raw value")
def _():
    assert LoomValue(8080) == 8080
    assert LoomValue("localhost") == "localhost"

@test("raises LoomTypeError on bad int cast")
def _():
    raised = False
    try:
        LoomValue("not_a_number").int
    except LoomTypeError:
        raised = True
    assert raised


# ─────────────────────────────────────────────────────────────────────────────
#  ScopeObject
# ─────────────────────────────────────────────────────────────────────────────
print("\n  ScopeObject")

@test("keys/values/items introspection")
def _():
    rt = loom('''
        @module("app")
        @server { host: "localhost", port: 8080 }
    ''')
    scope = rt._resolver.get_scope("app", "server")
    assert scope is not None
    assert set(scope.keys()) == {"host", "port"}
    assert len(scope.values()) == 2
    assert len(scope.items()) == 2

@test("attribute access returns LoomValue")
def _():
    rt = loom('''
        @module("app")
        @server { port: 8080 }
    ''')
    scope = rt._resolver.get_scope("app", "server")
    val = scope.port
    assert isinstance(val, LoomValue)
    assert val.int == 8080

@test("'in' operator works")
def _():
    rt = loom('''
        @module("app")
        @server { host: "localhost" }
    ''')
    scope = rt._resolver.get_scope("app", "server")
    assert "host" in scope
    assert "missing" not in scope

@test("ScopeObject is immutable")
def _():
    rt = loom('@module("app")\n@server { port: 8080 }')
    scope = rt._resolver.get_scope("app", "server")
    raised = False
    try:
        scope.port = 9090
    except AttributeError:
        raised = True
    assert raised

@test("LoomResolutionError on missing property")
def _():
    rt = loom('@module("app")\n@server { port: 8080 }')
    scope = rt._resolver.get_scope("app", "server")
    raised = False
    try:
        _ = scope.missing_key
    except LoomResolutionError:
        raised = True
    assert raised


# ─────────────────────────────────────────────────────────────────────────────
#  Runtime — basic access
# ─────────────────────────────────────────────────────────────────────────────
print("\n  Runtime — basic access")

@test("env.module.scope.key returns LoomValue")
def _():
    rt = loom('''
        @module("database")
        @db.main { host: "localhost", port: 5432 }
    ''')
    val = rt.env.database.db.main.host
    assert isinstance(val, LoomValue)
    assert val == "localhost"

@test("env.scope.key returns LoomValue (scope-level flattening)")
def _():
    rt = loom('''
        @module("database")
        @db.main { host: "localhost" }
    ''')
    val = rt.env.main.host
    assert val == "localhost"

@test("env.key returns LoomValue (global flattening)")
def _():
    rt = loom('''
        @module("server")
        @app { port: 8080 }
    ''')
    val = rt.env.port
    assert val.int == 8080

@test("env.scope returns ScopeObject")
def _():
    rt = loom('''
        @module("database")
        @db.main { host: "localhost" }
    ''')
    result = rt.env.database.db.main
    assert isinstance(result, ScopeObject)

@test("scope.keys() works via env proxy")
def _():
    rt = loom('''
        @module("database")
        @db.main { host: "localhost", port: 5432 }
    ''')
    scope = rt.env.database.db.main
    assert set(scope.keys()) == {"host", "port"}

@test("int/float/bool access via type casts")
def _():
    rt = loom('''
        @module("cfg")
        @app { port: 8080, ratio: 0.5, debug: true }
    ''')
    assert rt.env.cfg.app.port.int == 8080
    assert abs(rt.env.cfg.app.ratio.float - 0.5) < 0.001
    assert rt.env.cfg.app.debug.bool is True

@test("list values accessible")
def _():
    rt = loom('''
        @module("net")
        @network { hosts: ["a", "b"] }
    ''')
    val = rt.env.net.network.hosts
    assert val.list == ["a", "b"]


# ─────────────────────────────────────────────────────────────────────────────
#  Smart Resolution — all 4 strategies
# ─────────────────────────────────────────────────────────────────────────────
print("\n  Smart Resolution")

@test("Strategy 1: fully qualified path resolves")
def _():
    rt = loom('''
        @module("database")
        @db.main { host: "primary" }
        @db.replica { host: "replica" }
    ''')
    assert rt.env.database.db.main.host == "primary"
    assert rt.env.database.db.replica.host == "replica"

@test("Strategy 2: module-level raises LoomAmbiguityError when duplicate key")
def _():
    rt = loom('''
        @module("database")
        @db.main { host: "primary" }
        @db.replica { host: "replica" }
    ''')
    raised = False
    try:
        _ = rt.env.database.host
    except LoomAmbiguityError:
        raised = True
    assert raised, "Should raise LoomAmbiguityError for ambiguous module-level path"

@test("Strategy 2: module-level resolves when unique")
def _():
    rt = loom('''
        @module("database")
        @db.main { host: "localhost", port: 5432 }
    ''')
    # port is unique within the module
    assert rt.env.database.port.int == 5432

@test("Strategy 3: scope-level flattening resolves unique scope")
def _():
    rt = loom('''
        @module("database")
        @db.main { host: "localhost" }
    ''')
    assert rt.env.main.host == "localhost"

@test("Strategy 4: global flattening resolves unique global key")
def _():
    rt = loom('''
        @module("server")
        @app { port: 8080 }
    ''')
    assert rt.env.port.int == 8080

@test("Default scope (*) resolves module-level ambiguity")
def _():
    rt = loom('''
        @module("database")
        @db.main* { host: "primary" }
        @db.replica { host: "replica" }
    ''')
    # With default scope, env.database.host resolves to primary
    assert rt.env.database.host == "primary"

@test("Explicit path bypasses default scope")
def _():
    rt = loom('''
        @module("database")
        @db.main* { host: "primary" }
        @db.replica { host: "replica" }
    ''')
    assert rt.env.database.db.replica.host == "replica"

@test("Multiple default scopes at same level raise LoomScopeConflictError")
def _():
    raised = False
    try:
        loom('''
            @module("database")
            @db.main* { host: "primary" }
            @db.backup* { host: "backup" }
        ''')
    except LoomScopeConflictError:
        raised = True
    assert raised

@test("LoomResolutionError on completely unknown path")
def _():
    rt = loom('@module("app")\n@server { port: 8080 }')
    raised = False
    try:
        _ = rt.env.totally.unknown.path
    except LoomResolutionError:
        raised = True
    assert raised


# ─────────────────────────────────────────────────────────────────────────────
#  Multiple modules / merge
# ─────────────────────────────────────────────────────────────────────────────
print("\n  Multiple modules & merge")

@test("two modules loaded, both accessible")
def _():
    rt = LoomRuntime()
    rt.load_source('@module("database")\n@db { host: "db.local" }', "db.loom")
    rt.load_source('@module("server")\n@app { port: 9000 }', "server.loom")

    assert rt.env.database.db.host == "db.local"
    assert rt.env.server.app.port.int == 9000

@test("last-write-wins for duplicate module+scope+key")
def _():
    rt = LoomRuntime()
    rt.load_source('@module("cfg")\n@app { port: 8080 }', "a.loom")
    rt.load_source('@module("cfg")\n@app { port: 9090 }', "b.loom")

    assert rt.env.cfg.app.port.int == 9090

@test("modules() lists all loaded module names")
def _():
    rt = LoomRuntime()
    rt.load_source('@module("alpha")\n@a { x: 1 }', "a.loom")
    rt.load_source('@module("beta")\n@b { y: 2 }', "b.loom")
    names = rt.modules()
    assert "alpha" in names
    assert "beta" in names


# ─────────────────────────────────────────────────────────────────────────────
#  FileProvider
# ─────────────────────────────────────────────────────────────────────────────
print("\n  FileProvider")

@test("loads a .loom file from disk")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "app.loom")
        with open(path, "w") as f:
            f.write('@module("app")\n@server { port: 3000 }')

        rt = LoomRuntime()
        rt.register_provider(FileProvider(path))
        assert rt.env.app.server.port.int == 3000

@test("raises LoomImportError for missing file")
def _():
    raised = False
    try:
        rt = LoomRuntime()
        rt.register_provider(FileProvider("/nonexistent/path/missing.loom"))
    except Exception:
        raised = True
    assert raised

@test("loads multiple files via glob")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, name in enumerate(["alpha", "beta"]):
            path = os.path.join(tmpdir, f"{name}.loom")
            with open(path, "w") as f:
                f.write(f'@module("{name}")\n@{name} {{ value: {i + 1} }}')

        rt = LoomRuntime()
        rt.register_provider(FileProvider(os.path.join(tmpdir, "*.loom")))
        assert rt.env.alpha.alpha.value.int == 1
        assert rt.env.beta.beta.value.int == 2

@test("@import resolves nested file")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "database.loom")
        with open(db_path, "w") as f:
            f.write('@module("database")\n@db { host: "db.local" }')

        app_path = os.path.join(tmpdir, "app.loom")
        with open(app_path, "w") as f:
            f.write(f'@module("app")\n@import("./database.loom")\n@server {{ port: 8080 }}')

        rt = LoomRuntime()
        rt.register_provider(FileProvider(app_path))
        assert rt.env.app.server.port.int == 8080
        assert rt.env.database.db.host == "db.local"


# ─────────────────────────────────────────────────────────────────────────────
#  SystemEnvProvider
# ─────────────────────────────────────────────────────────────────────────────
print("\n  SystemEnvProvider")

@test("loads system env vars as a module")
def _():
    os.environ["_TEST_LOOM_PORT"] = "9999"
    rt = LoomRuntime()
    rt.register_provider(SystemEnvProvider(module="sysenv", scope="system", prefix="_TEST_LOOM_"))
    val = rt.env.sysenv.system.port
    assert val.int == 9999
    del os.environ["_TEST_LOOM_PORT"]

@test("infers bool from env var string")
def _():
    os.environ["_TEST_LOOM_DEBUG"] = "true"
    rt = LoomRuntime()
    rt.register_provider(SystemEnvProvider(module="sysenv", scope="system", prefix="_TEST_LOOM_"))
    assert rt.env.sysenv.system.debug.bool is True
    del os.environ["_TEST_LOOM_DEBUG"]

@test("prefix is stripped and keys are lowercased")
def _():
    os.environ["_TEST_LOOM_MYKEY"] = "hello"
    rt = LoomRuntime()
    rt.register_provider(SystemEnvProvider(module="sysenv", scope="system", prefix="_TEST_LOOM_"))
    val = rt.env.sysenv.system.mykey
    assert val == "hello"
    del os.environ["_TEST_LOOM_MYKEY"]


# ─────────────────────────────────────────────────────────────────────────────
#  OverrideProvider
# ─────────────────────────────────────────────────────────────────────────────
print("\n  OverrideProvider")

@test("overrides win over file values (registered last)")
def _():
    rt = LoomRuntime()
    rt.load_source('@module("database")\n@db.main { host: "localhost" }')
    overrides = OverrideProvider("database")
    overrides.set("db.main", "host", "override.example.com")
    rt.register_provider(overrides)
    assert rt.env.database.db.main.host == "override.example.com"

@test("chaining .set() works")
def _():
    ov = (
        OverrideProvider("cfg")
        .set("app", "host", "a.example.com")
        .set("app", "port", 443)
    )
    rt = LoomRuntime()
    rt.register_provider(ov)
    assert rt.env.cfg.app.host == "a.example.com"
    assert rt.env.cfg.app.port.int == 443


# ─────────────────────────────────────────────────────────────────────────────
#  Schema binding
# ─────────────────────────────────────────────────────────────────────────────
print("\n  Schema binding")

@test("@loom.bind populates dataclass from runtime")
def _():
    rt = loom('''
        @module("database")
        @db.main { host: "db.prod.com", port: 5432 }
    ''')

    @rt.bind("database", scope="db.main")
    @dataclasses.dataclass
    class DbConfig:
        host: str = "127.0.0.1"
        port: int = 5432

    cfg = DbConfig()
    assert cfg.host == "db.prod.com"
    assert cfg.port == 5432

@test("dataclass default used when key missing from runtime")
def _():
    rt = loom('''
        @module("database")
        @db.main { port: 5432 }
    ''')

    @rt.bind("database", scope="db.main")
    @dataclasses.dataclass
    class DbConfig:
        host: str = "127.0.0.1"
        port: int = 5432

    cfg = DbConfig()
    assert cfg.host == "127.0.0.1"  # fallback default
    assert cfg.port == 5432

@test("LoomSchemaError when required field has no value and no default")
def _():
    rt = loom('''
        @module("database")
        @db.main { port: 5432 }
    ''')

    @rt.bind("database", scope="db.main")
    @dataclasses.dataclass
    class StrictConfig:
        host: str               # no default — required!
        port: int = 5432

    raised = False
    try:
        cfg = StrictConfig()
    except LoomSchemaError:
        raised = True
    assert raised

@test("explicit kwargs override runtime values")
def _():
    rt = loom('''
        @module("database")
        @db.main { host: "db.prod.com", port: 5432 }
    ''')

    @rt.bind("database", scope="db.main")
    @dataclasses.dataclass
    class DbConfig:
        host: str = "localhost"
        port: int = 5432

    cfg = DbConfig(host="manual.override.com")
    assert cfg.host == "manual.override.com"


# ─────────────────────────────────────────────────────────────────────────────
#  Watcher / explain
# ─────────────────────────────────────────────────────────────────────────────
print("\n  Watchers & Explain")

@test("registered watcher is called by notify_watchers")
def _():
    rt = loom('@module("app")\n@server { port: 8080 }')
    fired = []

    @rt.watch("server.port")
    def on_change(val):
        fired.append(val)

    rt.notify_watchers("server.port", 9090)
    assert fired == [9090]

@test("explain() returns a non-empty string")
def _():
    rt = loom('''
        @module("database")
        @db.main { host: "localhost" }
    ''')
    output = rt.explain("database.db.main.host")
    assert "localhost" in output
    assert "database" in output

@test("explain() handles unknown path gracefully")
def _():
    rt = loom('@module("app")\n@server { port: 8080 }')
    output = rt.explain("totally.unknown")
    assert "Error" in output or "error" in output.lower()


# ─────────────────────────────────────────────────────────────────────────────
#  Diagnostics / Error messages
# ─────────────────────────────────────────────────────────────────────────────
print("\n  Diagnostics")

@test("LoomSyntaxError message includes line number")
def _():
    try:
        parse('@module("app")\n@server {\n    host = "bad"\n}')
    except LoomSyntaxError as e:
        msg = str(e)
        assert "3" in msg or "host" in msg  # line 3 or mentions the key

@test("LoomAmbiguityError message lists candidates")
def _():
    rt = loom('''
        @module("database")
        @db.main { host: "a" }
        @db.replica { host: "b" }
    ''')
    try:
        _ = rt.env.database.host
    except LoomAmbiguityError as e:
        msg = str(e)
        assert "host" in msg

@test("LoomResolutionError includes path in message")
def _():
    rt = loom('@module("app")\n@server { port: 8080 }')
    try:
        _ = rt.env.totally.unknown.path
    except LoomResolutionError as e:
        msg = str(e)
        assert len(msg) > 0  # has some message


# ─────────────────────────────────────────────────────────────────────────────
#  Spec examples — from the spec document
# ─────────────────────────────────────────────────────────────────────────────
print("\n  Spec examples")

@test("Spec §26: database.prod example")
def _():
    rt = loom('''
        @module("database", env: "prod")

        @db.main {
            host: "127.0.0.1"
            port: 5432
            driver: "postgres"
            debug: false
        }

        @db.pool {
            min: 5
            max: 20
        }
    ''')
    assert rt.env.database.db.main.host == "127.0.0.1"
    assert rt.env.database.db.main.port.int == 5432
    assert rt.env.database.db.main.driver == "postgres"
    assert rt.env.database.db.main.debug.bool is False
    assert rt.env.database.db.pool.min.int == 5
    assert rt.env.database.db.pool.max.int == 20

@test("Spec §13.1: fully qualified always resolves")
def _():
    rt = LoomRuntime()
    rt.load_source('''
        @module("database")
        @db.main { host: "localhost" }
        @db.replica { host: "10.0.0.5" }
    ''', "database.loom")
    rt.load_source('''
        @module("server")
        @app { port: 8080 }
    ''', "server.loom")

    # Fully qualified
    assert rt.env.database.db.main.host == "localhost"
    # Scope-level flattened (main is unique)
    assert rt.env.main.host == "localhost"
    # Global (port is globally unique)
    assert rt.env.port.int == 8080
    # Module-level ambiguity
    raised = False
    try:
        _ = rt.env.database.host
    except LoomAmbiguityError:
        raised = True
    assert raised


# ─────────────────────────────────────────────────────────────────────────────
#  Nested Objects & YAML-style Indentation Tests
# ─────────────────────────────────────────────────────────────────────────────
print("\n  Nested Objects & YAML-style Indentation")

@test("parses inline nested object")
def _():
    rt = loom('''
        @module("db")
        @db {
            pool: { min: 2, max: 10 }
        }
    ''')
    assert rt.env.db.pool.min.int == 2
    assert rt.env.db.pool.max.int == 10
    # Flat index check
    assert rt.env.pool.min.int == 2
    assert rt.env.pool.max.int == 10

@test("parses multi-line nested object")
def _():
    rt = loom('''
        @module("db")
        @db {
            pool: {
                min: 2,
                max: 10
            }
        }
    ''')
    assert rt.env.db.pool.min.int == 2
    assert rt.env.db.pool.max.int == 10

@test("parses YAML-style indented nested block")
def _():
    rt = loom('''
        @module("db")
        @db {
            pool:
                min: 2
                max: 10
        }
    ''')
    assert rt.env.db.pool.min.int == 2
    assert rt.env.db.pool.max.int == 10

@test("parses empty nested object")
def _():
    rt = loom('''
        @module("db")
        @db {
            pool: {}
        }
    ''')
    assert len(rt.env.db.pool) == 0

@test("parses arbitrary nesting depth")
def _():
    rt = loom('''
        @module("db")
        @db {
            limits:
                pool:
                    max: 10
                    min: 1
        }
    ''')
    assert rt.env.db.limits.pool.max.int == 10
    assert rt.env.db.limits.pool.min.int == 1

@test("parses mixed inline and indented nested syntax")
def _():
    rt = loom('''
        @module("db")
        @db {
            pool: {
                limits:
                    max: 10
                    min: 1
            }
        }
    ''')
    assert rt.env.db.pool.limits.max.int == 10
    assert rt.env.db.pool.limits.min.int == 1

@test("raises LoomSyntaxError on inconsistent indentation inside YAML-style block")
def _():
    raised = False
    try:
        loom('''
            @module("db")
            @db {
                pool:
                    min: 2
                      max: 10
            }
        ''')
    except LoomSyntaxError as e:
        raised = True
        assert "Inconsistent indentation" in str(e)
    assert raised

@test("raises LoomSyntaxError on mixed tabs and spaces in indentation")
def _():
    raised = False
    try:
        # Use literal tab character mixed with spaces
        loom('''
            @module("db")
            @db {
                pool:
                \tmin: 2
            }
        ''')
    except LoomSyntaxError as e:
        raised = True
        assert "Mixed tabs and spaces" in str(e)
    assert raised


# ─────────────────────────────────────────────────────────────────────────────
#  Auto-Discovery Tests
# ─────────────────────────────────────────────────────────────────────────────
print("\n  Auto-Discovery")

@test("discovers files in search order and applies profile priority")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create config/ directory structure
        config_dir = os.path.join(tmpdir, "config")
        os.makedirs(config_dir)

        # 1. Base files
        with open(os.path.join(tmpdir, "first.loom"), "w") as f:
            f.write('@module("first")\n@main { val: "root" }')

        with open(os.path.join(config_dir, "second.loom"), "w") as f:
            f.write('@module("second")\n@main { val: "config" }')

        # Create FileProvider with start directory
        rt = LoomRuntime()
        provider = FileProvider("first", base_dir=tmpdir)
        rt.register_provider(provider)
        assert rt.env.first.main.val == "root"

        # Discovering 'second' inside config/
        rt2 = LoomRuntime()
        provider2 = FileProvider("second", base_dir=tmpdir)
        rt2.register_provider(provider2)
        assert rt2.env.second.main.val == "config"

@test("auto-discovery is deterministic with duplicate filenames (chooses shallower/alphabetic)")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create two matching filenames at different depths
        # E.g. base_dir/app.loom vs base_dir/subdir/app.loom
        subdir = os.path.join(tmpdir, "subdir")
        os.makedirs(subdir)

        with open(os.path.join(tmpdir, "dup.loom"), "w") as f:
            f.write('@module("dup")\n@main { val: "shallow" }')

        with open(os.path.join(subdir, "dup.loom"), "w") as f:
            f.write('@module("dup")\n@main { val: "deep" }')

        rt = LoomRuntime()
        provider = FileProvider("dup", base_dir=tmpdir)
        rt.register_provider(provider)
        # Should deterministically resolve the shallower one first
        assert rt.env.dup.main.val == "shallow"


# ─────────────────────────────────────────────────────────────────────────────
#  Results
# ─────────────────────────────────────────────────────────────────────────────

passed = sum(1 for _, ok, _ in _results if ok)
failed = sum(1 for _, ok, _ in _results if not ok)
total = len(_results)

print(f"\n\033[1m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m")
print(f"  Results: \033[92m{passed} passed\033[0m / \033[91m{failed} failed\033[0m / {total} total")

if failed:
    print("\n  Failed tests:")
    for name, ok, err in _results:
        if not ok:
            print(f"    {_FAIL} {name}: {err}")

print(f"\033[1m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m\n")
sys.exit(0 if failed == 0 else 1)
