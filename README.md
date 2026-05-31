<div align="center">

[//]: # (<img src="https://raw.githubusercontent.com/nestifypy/nestifypy/main/docs/assets/logo.png" alt="Nestifypy" width="120" />)

# 🪺 Nestifypy

**A modern, declarative utility and game framework for Python 3.10+**

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen?style=flat-square)](https://github.com/nestifypy/nestifypy/actions)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white)](https://pypi.org/project/nestifypy/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![PyPI](https://img.shields.io/pypi/v/nestifypy?style=flat-square)](https://pypi.org/project/nestifypy/)

Nestifypy is a modular Python framework designed around **declarative patterns**, **developer ergonomics**, and **strict type safety** — whether you're building enterprise CLIs, intelligent configuration systems, or fully-featured 2D games.

[Installation](#-installation) · [Modules](#-ecosystem) · [Quick Start](#-quick-start) · [Docs](#-documentation) · [Contributing](#-contributing)

</div>

---

## 📦 Installation

**Core framework** (no game engine dependencies):
```bash
pip install nestifypy
```

**Full framework** (includes Pyunix game engine):
```bash
pip install "nestifypy[game]"
```

**Ignite enterprise framework** (DI, web, scheduler, JWT):
```bash
pip install nestifypy-ignite[all]
```

> Requires **Python 3.10 or higher**.

---

## 🌐 Ecosystem

Nestifypy is composed of several independent, high-performance packages. Use what you need.

| Package | Description |
|---|---|
| [**Ignite**](#-ignite--enterprise-application-framework) | Spring Boot-inspired DI, EventBus, FastAPI integration, cron jobs |
| [**Komodo**](#-komodo--metaprogramming) | Lombok-style annotation-driven metaprogramming |
| [**Pyunix**](#-pyunix--2d-game-engine) | Declarative 2D game engine built on Pygame |
| [**YAML**](#-yaml--intelligent-config-registry) | O(1) intelligent YAML registry with hot-reload |
| [**Env**](#-env--environment-management) | Typed, chainable `.env` variable management |
| [**Loom**](#-loom--configuration-engine) | Hierarchical typed config format (`.loom` files) |
| [**Flow**](#-flow--control-flow) | Task scheduling, throttling, concurrency helpers |
| [**Promise**](#-promise) | Asynchronous execution API without asyncio |
| [**Trying**](#-trying) | Functional error handling with Try monad |
| [**Input**](#-input) | Interactive CLI inputs, forms, and validation |
| [**Decorators**](#-decorators) | Caching, retries, validation, events and more |
| [**Collections**](#-collections) | Java-inspired strongly-typed data structures |
| [**Console**](#-console--terminal-utilities) | Rich terminal output, spinners, tables, prompts |
| [**SLogger**](#-core--logger-registry-plugins) | Logger (Slogger), Registry, Plugin system |

---

## 🚀 Quick Start

### Smart Configuration

```python
from nestifypy import yaml
from nestifypy.env import Env

Env.load()

# Fetch from any .yml file in your project using dot-notation
db_host = yaml.get("database.host")

# Or use the Pythonic attribute API
db_port = yaml.database.port

# Chainable typed env var access
debug   = env.debug.bool
port    = env.db.port.int
hosts   = env.allowed_hosts.list
```

### Enterprise App with Ignite

```python
from nestifypy.ignite import Application
from nestifypy.ignite.decorators import Service, Controller, PostConstruct
from nestifypy.ignite.web.rest import Get, Post

@Service
class UserService:
    def get_users(self) -> list[str]:
        return ["Hope", "Alex"]

@Controller("/users")
class UserController:
    def __init__(self, user_service: UserService):
        self.user_service = user_service

    @Get("/")
    async def list_users(self):
        return self.user_service.get_users()

    @PostConstruct
    async def on_start(self):
        print("UserController ready!")

app = Application.run(web=True, starters=["web"])
```

### 2D Game with Pyunix

```python
from nestifypy.pyunix import Game, Entity, Rigidbody, BoxCollider, BodyType
from nestifypy.pyunix.math import Vector2, Color

@Game(title="My Game", size=(800, 600), fps=60)
class MyGame:

    @Game.start
    def start(self):
        self.player = Player(x=400, y=300)

    @Game.update
    def update(self, dt: float):
        pass

    @Game.draw
    def draw(self, screen):
        screen.fill(Color.BLACK.to_tuple())

    @Game.text(x=10, y=10, size=24, color="white")
    def score_ui(self):
        return "SCORE: 1000"

class Player(Entity):
    def __init__(self, x, y):
        super().__init__(
            x=x, y=y,
            rigidbody=Rigidbody(body_type=BodyType.DYNAMIC, mass=1.0),
            collider=BoxCollider(width=32, height=32)
        )

    @Entity.update
    def movement(self, dt):
        if self.input.is_action_pressed("jump"):
            self.rigidbody.add_impulse(Vector2(0, -500))

if __name__ == "__main__":
    MyGame().run()
```

### Metaprogramming with Komodo

```python
from nestifypy.komodo import komodo, contract
from nestifypy.komodo.contract import requires, ensures

@komodo.builder
@komodo.data
class DatabaseConfig:
    host: str
    port: int = 5432

@contract(requires(lambda config: config.port > 1024, "Port must be > 1024"))
def connect(config: DatabaseConfig):
    print(f"Connecting to {config.host}:{config.port}")

# Fluent builder API, auto-generated
conf = DatabaseConfig.Builder().with_host("localhost").build()
connect(conf)
```

---

## 🔥 Ignite — Enterprise Application Framework

A Spring Boot-inspired framework for production Python apps.

**Features:** IoC container, constructor injection, lifecycle hooks, EventBus, FastAPI integration, cron scheduling, JWT security, profile-aware configuration, and a `TestContainer` for mocking.

### Dependency Injection

```python
from nestifypy.ignite.decorators import Service, Repository, Component

@Repository
class UserRepository:
    def find(self, id: int) -> dict:
        return {"id": id, "name": "Alice"}

@Service
class UserService:
    # EmailRepository injected automatically by type
    def __init__(self, repo: UserRepository):
        self.repo = repo

    def get_user(self, id: int):
        return self.repo.find(id)
```

### Configuration & Profiles

```yaml
# application.yml
server:
  port: 8080
database:
  url: "postgresql://localhost/myapp"
jwt:
  secret: "my-secret"
  expiry_minutes: 60
```

```python
from nestifypy.ignite.decorators import Value

@Service
class AppConfig:
    @Value("server.port")
    port: int

    @Value("database.url")
    db_url: str
```

### EventBus

```python
from nestifypy.ignite.decorators import EventListener
from nestifypy.ignite.events import EventBus
import dataclasses

@dataclasses.dataclass
class UserRegistered:
    user_id: int
    email: str

@Service
class NotificationService:
    @EventListener(UserRegistered)
    async def on_user_registered(self, event: UserRegistered):
        print(f"Welcome email sent to {event.email}")

# Publish from anywhere
await app.context.event_bus.publish(UserRegistered(user_id=1, email="alice@example.com"))
```

### Scheduled Tasks

```python
from nestifypy.ignite.decorators import Scheduled

@Service
class ReportJob:
    @Scheduled("0 8 * * 1")    # every Monday at 08:00
    async def weekly_report(self):
        ...

    @Scheduled("*/5 * * * *")  # every 5 minutes
    def poll_queue(self):
        ...
```

### Testing

```python
from nestifypy.ignite.testing import TestContainer
from unittest.mock import MagicMock

def test_user_service():
    container = TestContainer()
    mock_repo = MagicMock()
    mock_repo.find.return_value = {"id": 1, "name": "Alice"}

    container.override(UserRepository, mock_repo)
    container.register(UserService)

    service = container.get(UserService)
    assert service.get_user(1)["name"] == "Alice"
```

**Installation extras:**

```bash
pip install nestifypy-ignite[web]       # FastAPI + uvicorn
pip install nestifypy-ignite[jwt]       # PyJWT
pip install nestifypy-ignite[scheduler] # croniter
pip install nestifypy-ignite[all]       # everything
```

---

## 🦎 Komodo — Metaprogramming

Lombok-style annotation-driven metaprogramming. Eliminates class boilerplate using composable decorators — no metaclasses, no runtime proxies.

### Core Decorators

| Decorator | What it does | Lombok equivalent |
|---|---|---|
| `@komodo.data` | Generates `__init__`, `__repr__`, `__eq__`, `__hash__` | `@Data` |
| `@komodo.builder` | Adds a fluent `.Builder` inner class | `@Builder` |
| `@komodo.value` | Immutable data object | `@Value` |
| `@komodo.constructor` | Generates `__init__` from annotations | `@AllArgsConstructor` |
| `@komodo.immutable` | Freezes attributes after construction | `@Immutable` |
| `@komodo.singleton` | Ensures a single instance | — |
| `@komodo.logger` | Injects a stdlib `logger` attribute | `@Slf4j` |
| `@komodo.copyable` | Adds `.copy()` and `.copy_with()` | `@With` |
| `@komodo.non_null` | Raises `ValueError` if any arg is `None` | `@NonNull` |
| `@komodo.validated` | Runtime type-checking from annotations | — |
| `@komodo.observable` | Injects `.subscribe()` and `.notify()` | — |
| `@komodo.sealed` | Prevents subclassing | `sealed` (Java 17) |

### Examples

```python
from nestifypy.komodo import komodo

# Rich domain entity
@komodo.logger
@komodo.copyable
@komodo.data
class Product:
    id: int
    name: str
    price: float
    active: bool = True

p = Product(1, "Widget", 9.99)
p2 = p.copy_with(price=7.99)
Product.logger.info("Price updated")

# Fluent builder with validation
@komodo.builder
@komodo.validated
@komodo.constructor
class CreateUserRequest:
    username: str
    email: str
    role: str = "viewer"

req = (
    CreateUserRequest.Builder()
        .with_username("alice")
        .with_email("alice@example.com")
        .with_role("admin")
        .build()
)

# Immutable value object
@komodo.value
class Money:
    amount: float
    currency: str

m = Money(9.99, "USD")
m.amount = 0.0  # AttributeError: Money is immutable
```

### Design by Contract

```python
from nestifypy.komodo import contract
from nestifypy.komodo.contract import requires, ensures, invariant

@komodo.constructor
class BankAccount:
    balance: float

    @contract(
        requires(lambda self, amount: amount > 0, "amount must be positive"),
        ensures(lambda result: result is None, "withdraw returns None"),
        invariant(lambda self: self.balance >= 0, "balance must never be negative")
    )
    def withdraw(self, amount: float) -> None:
        self.balance -= amount
```

---

## 🎮 Pyunix — 2D Game Engine

A fully declarative game engine built on top of Pygame. Inspired by Unity and Godot — no messy `while True` loops.

### Game Loop

```python
from nestifypy.pyunix.app import Game

@Game(title="My Game", size=(800, 600), fps=60, vsync=True)
class MyGame:

    @Game.start
    def on_start(self):
        pass  # Load resources, create entities

    @Game.update
    def on_update(self, dt: float):
        pass  # Frame logic

    @Game.draw
    def on_draw(self, screen):
        screen.fill((30, 30, 40))

    @Game.layer("ui", order=2)
    def draw_ui(self, screen):
        self.hud.draw(screen)

    @Game.text(x=10, y=10, size=20, color="yellow")
    def score_label(self):
        return f"Score: {self.score}"

MyGame().run()
```

### Entities & Physics

```python
from nestifypy.pyunix.sprite import Entity, Sprite
from nestifypy.pyunix.physics import Rigidbody, BoxCollider, BodyType, PhysicsWorld
from nestifypy.pyunix.input import Input
from nestifypy.pyunix.math import Vector2

PhysicsWorld.set_gravity(0, 900)

class Player(Entity):
    def __init__(self):
        super().__init__(
            x=200, y=300,
            rigidbody=Rigidbody(body_type=BodyType.DYNAMIC, gravity_scale=1.0),
            collider=BoxCollider(28, 48),
        )
        self.on_ground = False

    @Sprite.update
    def move(self, dt):
        h = Input.get_axis("horizontal")
        self.rigidbody.velocity.x = h * 200

        if Input.action_just_pressed("jump") and self.on_ground:
            self.rigidbody.add_impulse(Vector2(0, -450))

    @Sprite.on_collision_enter
    def on_hit(self, info):
        if info.normal.y < -0.5:
            self.on_ground = True
```

### Sprite Lifecycle Hooks

| Hook | When it fires |
|---|---|
| `@Sprite.ready` | Once, on construction |
| `@Sprite.update` | Every frame (receives `dt`) |
| `@Sprite.fixed_update` | Fixed physics timestep |
| `@Sprite.draw` | Every frame (receives `surface`) |
| `@Sprite.destroy` | Before entity is removed |
| `@Sprite.on_collision_enter` | First frame of collision |
| `@Sprite.on_collision_stay` | Each frame while colliding |
| `@Sprite.on_collision_exit` | When collision ends |
| `@Sprite.on_trigger_enter` | On entering a trigger zone |
| `@Sprite.pause` / `@Sprite.resume` | On game pause/resume |

### Included Systems

- **Camera** — smooth follow, world bounds, shake, offset
- **Audio** — music streaming, SFX with pitch variation
- **Assets** — preloading, caching, image/audio/font management
- **Animation** — spritesheet-based with state machine
- **Particles** — burst and continuous emitters
- **Tween** — property animation with easing functions
- **TileMap** — tile-based map rendering with auto-culling
- **Timer** — `Timer.after()`, `Timer.every()` callbacks
- **Scene** — scene manager with push/pop stack
- **Events** — pub/sub event system between entities

> **Debug:** Press `F3` at runtime for an overlay showing FPS, physics bodies, camera position and time scale. Press `ESC` to pause/resume.

---

## ⚙️ YAML — Intelligent Config Registry

Not just a parser — a runtime configuration engine with O(1) lookup and hot-reload.

```yaml
# config/database.yml
database:
  host: "localhost"
  port: 5432
  pool:
    min_size: 2
    max_size: 10
```

```python
from nestifypy import yaml

# Zero-boilerplate: auto-scans .yml files in your project
host     = yaml.get("database.host")        # string path
max_pool = yaml.database.pool.max_size      # Pythonic attribute access

# Watch for changes in long-running processes
yaml.watch(True)

def game_loop():
    while True:
        speed = yaml.get("game.player.speed")  # updates automatically
```

**How it works:** On first access, Nestifypy scans your project and generates a `.nestifypy/yaml_index.json` flat index mapping every dot-path to its file. Subsequent lookups are O(1). Only changed files are re-parsed.

```python
# Explicit scan for specific directories
from pathlib import Path
yaml.scan(Path("src/config/"))

# Trace where a value comes from
print(yaml.where("database.host"))  # "/absolute/path/to/database.yml"
```

> Add `.nestifypy/` to your `.gitignore`.

---

## 🔒 Env — Environment Management

Modern, typed, chainable `.env` variable management. Inspired by NestJS and Spring Boot.

```python
from nestifypy import env
from nestifypy.env import Env

Env.load()  # or Env.load("config/.env")

# Chainable attribute access with auto-uppercasing
host  = env.db.host             # → DB_HOST
port  = env.db.port.int         # → int(DB_PORT)
debug = env.debug.bool          # → bool(DEBUG)
hosts = env.allowed_hosts.list  # → ["localhost", "127.0.0.1"]

# Safe defaults and required fields
secret = env.secret_key.required             # raises ConfigError if missing
db_pw  = env.db.password.default("root")    # fallback value

# Descriptor API for config classes
from nestifypy.env import Env

class Config:
    host = Env.property("DB_HOST", default="localhost")
    port = Env.property("DB_PORT", cast_type=int, default=5432)

# Injection decorator
@Env.inject(api_key="API_KEY", host="DB_HOST")
def connect(api_key=None, host=None):
    ...
```

---

## 🧵 Loom — Configuration Engine

A structured alternative to `.env`/`python-dotenv` with hierarchical, typed, modular config files.

```loom
# app.loom
@module("app")

@server {
    host: "localhost"
    port: 8080
    debug: true
}

@database {
    host: "127.0.0.1"
    port: 5432
    name: "myapp"
    pool: { min: 2, max: 10 }
}
```

```python
from nestifypy.loom import Loom, env

Loom.load("app.loom")

host  = env.app.server.host        # fully qualified
port  = env.server.port.int        # scope-level flattening
debug = env.debug.bool             # global flattening (if unique)

# Schema binding to dataclasses
import dataclasses

@Loom.bind("database", scope="database")
@dataclasses.dataclass
class DbConfig:
    host: str = "localhost"
    port: int = 5432
    name: str = "myapp"

cfg = DbConfig()
print(cfg.host, cfg.port)

# Hot-reload watchers
@Loom.watch("server.port")
def on_port_change(new_value):
    restart_http_server(int(new_value))
```

**Rust-style diagnostics:**

```
🚨 LoomSyntaxError in 'database.loom' (Line 4)

    3 | @db.main {
    4 |     host = "localhost"
               ^
    5 | }

Error:   Property 'host' uses '=' instead of ':'
Found:   '='
Expected: ':'
Hint:    Replace with: host: "localhost"
```

---

## ⏱ Flow — Control Flow

Advanced task scheduling, throttling, concurrency, and rate limiting.

```python
from nestifypy.flow import Flow

# Run every 5 seconds in a background thread
@Flow.interval(5.0)
def ping_server():
    print("Ping!")

# Throttle to at most 1 call per second
@Flow.throttle(1.0)
def on_mouse_move(x, y):
    pass

# Retry up to 3 times on failure
@Flow.retry(times=3, wait=2.0)
def fetch_api():
    pass

# Run concurrently and collect results
results = Flow.parallel(task_a, task_b, task_c)

# Debounce search input
@Flow.debounce(wait=0.3)
def on_search_input(query):
    search(query)
```

**Available utilities:** `@Flow.delay`, `@Flow.repeat`, `@Flow.interval`, `@Flow.retry`, `@Flow.timeout`, `@Flow.debounce`, `@Flow.throttle`, `@Flow.once`, `@Flow.after`, `Flow.parallel`, `@Flow.threaded`, `Flow.run_async`, `Flow.schedule`, `Flow.loop`.

---

## ✨ Decorators

A comprehensive suite of utility decorators, all preserving function metadata via `functools.wraps`.

### Execution & Performance

```python
from nestifypy.decorators import benchmark, cache, once, rate_limit

@benchmark
@cache
def expensive_calculation(x):
    return sum(i * i for i in range(x))
```

### Error Handling & Resiliency

```python
from nestifypy.decorators import safe, trace, retry

@retry(times=3, delay=2.0)
def fetch_api_data():
    pass

@safe  # catches all exceptions, returns None instead of crashing
def risky_operation():
    pass
```

### Type Validation

```python
from nestifypy.decorators import validate_types, not_null, validate

@validate_types
def process_user(age: int, name: str):
    pass  # raises TypeError if types don't match

@not_null
def create_record(id, name):
    pass  # raises ValueError if any arg is None
```

### Architecture & Events

```python
from nestifypy.decorators import singleton, observable, event, emit, startup, shutdown

@event("user_registered")
def send_welcome_email(user_id):
    pass

# Trigger from anywhere
emit("user_registered", 101)

@startup
def init_database():
    pass

@shutdown
def close_connections():
    pass
```

**Full decorator list:** `@benchmark`, `@cache`, `@once`, `@rate_limit`, `@safe`, `@trace`, `@retry`, `@threaded`, `@async_task`, `@delay`, `@not_null`, `@validate`, `@validate_types`, `@singleton`, `@observable`, `@startup`, `@shutdown`, `@event`, `@deprecated`, `@experimental`.

---

## 🗂 Collections

Java-inspired, fluent data structures with type hints support.

```python
from nestifypy.collections import ArrayList, LinkedList, Stack, Queue, OrderedSet, HashMap

# Fluent ArrayList
lista = ArrayList()
lista.add(10).add(20).add(30)

# LIFO Stack
stack = Stack()
stack.push("Scene1").push("Scene2")
active = stack.pop()

# FIFO Queue (built on collections.deque)
q = Queue()
q.enqueue("Task1").enqueue("Task2")
task = q.dequeue()  # "Task1"

# Ordered uniqueness
oset = OrderedSet()
oset.add("A").add("B").add("A")  # ["A", "B"]

# Fluent HashMap
map = HashMap()
map.put("hero", "Link").put("weapon", "Sword")
```

---

## 🖥 Console — Terminal Utilities

Rich terminal output for modern CLI applications.

```python
from nestifypy.console import Console

# Colored printing
Console.success("Migration complete!")
Console.error("Failed to connect.")
Console.warn("Memory usage high.")
Console.info("Server starting...")
Console.print("Custom", color="magenta", bold=True)

# Interactive prompts
name   = Console.ask("Your name?", default="Guest")
go     = Console.confirm("Proceed?", default=True)
env    = Console.choose("Environment", ["dev", "staging", "prod"])

# Progress tracking
with Console.progress(total=100, label="Downloading") as bar:
    for _ in range(100):
        bar.update(1)

# Animated spinner
with Console.spinner("Fetching data..."):
    time.sleep(2)

# Structured table
Console.table([
    {"ID": 1, "Name": "Alice", "Role": "Admin"},
    {"ID": 2, "Name": "Bob",   "Role": "User"},
], title="User Directory")
```

---

## 🔧 Core — Logger, Registry, Plugins

Application backbone: standardized logger, global registry, dynamic plugin system.

```python
from nestifypy.slogger import Logger, LogLevel, Registry, Plugin

# Logger
Logger.set_level(LogLevel.DEBUG)
Logger.set_prefix("MY_APP")
Logger.set_file("app.log")
Logger.info("Application started.")
Logger.warn("Memory usage is high.")
Logger.error("Failed to connect.")
Logger.trace()  # print full stacktrace

# Registry — namespaced global state
Registry.register("services", "database", db_instance)
db = Registry.get("services", "database")


# Plugin system
@Plugin.info(name="auth_plugin", version="1.0.0", description="OAuth support")
class AuthPlugin:
    def authenticate(self):
        pass


Plugin.register(AuthPlugin)
Plugin.load("plugins/custom_auth.py")
all_plugins = Plugin.all()
```

---

## 🏗 CLI Scaffolding

Bootstrap a professional project structure in one command:

```bash
nestifypy init --name my_app
```

Generated structure includes pre-configured support for `ruff`, `pytest`, and `mypy`.

---

## 📝 Changelog

### v0.2.3
- **Trying:** Added `Try` monad for fluent, functional error handling without `try/except`.
- **Promise:** Implemented modern Promise API for async execution (`then`, `catch`, `all`, `race`) without asyncio.
- **Input:** Added comprehensive module for interactive CLI inputs, form handling, and data sanitization.
- **Slogger:** Upgraded core logger module to `slogger`.
- **Scheduler:** Added robust `@Scheduled` cron job decorator for the Ignite framework.

### v0.2.2
- **Pyunix:** Fixed physics bounding box discrepancies (`rect.topleft` vs `rect.center`) ensuring pixel-perfect `BoxCollider` interactions.
- **FlappyBird Demo:** Refactored `examples/flappybird.py` to use Pyunix's modern physics engine, Animator and Trigger zones. Fixed ghost pipe collider on reset.
- **Ignite Docs:** Published comprehensive documentation covering DI, FastAPI, EventBus, Scheduled Tasks, and TestContainers.

### v0.2.1
- **Ignite Core:** Rebranded and refactored the legacy `bolt` container into the `ignite` application framework.
- **EventBus:** Added publish/subscribe event bus.
- **Web module:** Seamless FastAPI integration.
- **Cron Jobs:** Introduced `@Scheduled` decorators via `croniter`.
- **Testing:** Added `TestContainer` for dependency-isolated integration testing.

---

## 📚 Documentation

Full documentation is available in the `docs/` directory:

- 🔥 [Ignite Framework](docs/ignite.md)
- 🦎 [Komodo Metaprogramming](docs/komodo.md)
- 🎮 [Pyunix Game Engine](docs/pyunix.md)
- ⚙️ [YAML Intelligent Registry](docs/yaml.md)
- 🔒 [Environment Management](docs/env.md)
- 🧵 [Loom Configuration](docs/loom.md)
- ⏱ [Flow Control](docs/flow.md)
- ✨ [Decorators](docs/decorators.md)
- 🗂 [Collections](docs/collections.md)
- 🖥 [Console Utilities](docs/console.md)
- 🔧 [Core Systems](docs/core.md)
- 📁 [OS & File Utilities](docs/os.md)

---

## 🤝 Contributing

Contributions are welcome!

1. Clone the repository
2. Install development dependencies: `uv pip install -e ".[dev]"` or `pip install -e ".[dev]"`
3. Run tests: `pytest`
4. Lint code: `ruff check .`

---

## 🛡 Security

Please review our [Security Policy](SECURITY.md) for information on reporting vulnerabilities.

---

## 📜 License

This project is licensed under the [MIT License](LICENSE).

---

<div align="center">
  <sub>Built with ❤️ for Pythonistas who believe in clean, expressive code.</sub>
</div>
