# Nestifypy Ignite 🐍

> A Spring Boot-inspired framework for Python — decorator-driven, async-first, enterprise-ready.

[![PyPI version](https://img.shields.io/pypi/v/nestifypy-ignite.svg)](https://pypi.org/project/nestifypy-ignite/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../../files(5)/LICENSE)

---

## Features

- **Dependency Injection** — automatic constructor injection via type hints
- **IOC Container** — singleton/prototype scopes, circular dependency detection
- **Decorator-driven** — `@Service`, `@Controller`, `@Repository`, `@Configuration`, `@Bean`
- **YAML Configuration** — `application.yml` + profile overrides (`application-dev.yml`)
- **Event System** — async `EventBus` with `@EventListener`
- **Scheduler** — cron-based `@Scheduled` tasks powered by asyncio
- **Web Layer** — `@Get`, `@Post`, `@Put`, `@Delete`, `@Patch` on controller methods (FastAPI under the hood)
- **Security** — JWT service, route guards, password hashing
- **Starters** — auto-configuration via `web`, `security`, `data`, `cache` starters
- **Lifecycle Hooks** — `@PostConstruct` / `@PreDestroy`
- **Testing Utilities** — `TestContainer`, `mock_bean`, `IntegrationTestRunner`

---

## Installation

```bash
# Core only
pip install nestifypy-ignite

# With web server
pip install "nestifypy-ignite[web]"

# With security
pip install "nestifypy-ignite[security]"

# Everything
pip install "nestifypy-ignite[all]"
```

---

## Quick Start

```python
from nestifypy.ignite import Application
from nestifypy.ignite.decorators import Service, Controller, PostConstruct
from nestifypy.ignite.web.rest import Get, Post

@Service
class UserService:

    def get_users(self) -> list[str]:
        return ["Hope", "Alex"]

    def create_user(self, name: str) -> dict:
        return {"id": 1, "name": name}


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

---

## YAML Configuration

**`application.yml`**
```yaml
server:
  port: 8080

database:
  host: localhost
  port: 5432
  name: mydb

app:
  debug: true
```

**`application-dev.yml`** (overrides)
```yaml
app:
  debug: true
database:
  host: localhost
```

Run with a profile:
```bash
python main.py --profile=dev
# or
NESTIFYPY_PROFILE=dev python main.py
```

---

## Dependency Injection

Constructor injection is automatic via type hints:

```python
@Service
class EmailService:
    async def send(self, to: str, body: str): ...

@Service
class NotificationService:
    def __init__(self, email_service: EmailService):
        self.email_service = email_service  # injected automatically
```

---

## Configuration Beans

```python
from nestifypy.ignite.decorators import Configuration, Bean

@Configuration
class AppConfig:

    @Bean
    def redis_client(self):
        import redis
        return redis.Redis(host="localhost", port=6379)
```

---

## Event System

```python
from dataclasses import dataclass
from nestifypy.ignite.decorators import Service, EventListener

@dataclass
class UserCreatedEvent:
    username: str

@Service
class UserService:
    def __init__(self, event_bus):
        self._event_bus = event_bus

    async def create(self, name: str):
        await self._event_bus.publish(UserCreatedEvent(username=name))

@Service
class AuditService:

    @EventListener(UserCreatedEvent)
    async def on_user_created(self, event: UserCreatedEvent):
        print(f"Audit: user '{event.username}' created")
```

---

## Scheduled Tasks

```python
from nestifypy.ignite.decorators import Service, Scheduled

@Service
class CleanupService:

    @Scheduled("*/5 * * * *")  # every 5 minutes
    async def cleanup(self):
        print("Running scheduled cleanup...")
```

---

## Security

```python
from nestifypy.ignite.security import JwtService, Guard, GuardBase, RequiresRoles
from nestifypy.ignite.web.rest import Get

class AdminGuard(GuardBase):
    async def can_activate(self, request=None) -> bool:
        # Add your auth logic here
        return True

@Controller("/admin")
class AdminController:

    @Guard(AdminGuard)
    @RequiresRoles("admin")
    @Get("/dashboard")
    async def dashboard(self):
        return {"status": "ok"}
```

---

## Testing

```python
from nestifypy.ignite.testing import TestContainer, mock_bean

def test_user_controller():
    mock_service = mock_bean(UserService, get_users=lambda: ["TestUser"])

    container = TestContainer()
    container.override(UserService, mock_service)
    container.register(UserController)

    controller = container.get(UserController)
    assert controller.user_service.get_users() == ["TestUser"]
```

---

## Project Structure

```
my_project/
├── main.py
├── application.yml
├── application-dev.yml
└── src/
    ├── controllers/
    │   └── user_controller.py
    ├── services/
    │   └── user_service.py
    ├── repositories/
    │   └── user_repository.py
    ├── config/
    │   └── app_config.py
    └── models/
        └── user.py
```

---

## Roadmap

- [ ] ORM integration (SQLAlchemy async)
- [ ] Repository pattern with query builders
- [ ] Transaction decorators (`@Transactional`)
- [ ] CLI tooling (`nestifypy new project`)
- [ ] Hot reload for development
- [ ] Reactive streams support
- [ ] Microservice primitives (RPC, event streaming)
- [ ] Native compilation via Nuitka

---

## License

MIT — see [LICENSE](../../files(5)/LICENSE) for details.
