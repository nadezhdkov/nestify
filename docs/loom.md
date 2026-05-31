# nestifypy.loom

> A modern, runtime-oriented configuration system for Python — a structured alternative to `.env` / `python-dotenv`.

`.loom` files are hierarchical, typed, modular, and environment-aware. The runtime exposes configuration through attribute-style access with Smart Resolution, schema binding, and Rust-style diagnostic errors.

**Loom Specification:** v0.1  
**Python:** 3.10+  
**Dependencies:** none (stdlib only)

---

## Índice

- [Instalação](#instalação)
- [Início Rápido](#início-rápido)
- [Formato .loom](#formato-loom)
  - [Declaração de módulo](#declaração-de-módulo)
  - [Scopes](#scopes)
  - [Propriedades e tipos](#propriedades-e-tipos)
  - [Objetos Aninhados e Indentação](#objetos-aninhados-e-indentação)
  - [Comentários](#comentários)
  - [Imports](#imports)
  - [Default Scopes](#default-scopes)
- [Runtime](#runtime)
  - [Carregar ficheiros](#carregar-ficheiros)
  - [Auto-Descoberta de Ficheiros (Auto-Discovery)](#auto-descoberta-de-ficheiros-auto-discovery)
  - [Acesso por atributos](#acesso-por-atributos)
  - [LoomValue e type casts](#loomvalue-e-type-casts)
  - [ScopeObject](#scopeobject)
- [Smart Resolution](#smart-resolution)
  - [Estratégia 1 — Fully qualified](#estratégia-1--fully-qualified)
  - [Estratégia 2 — Module-level flattened](#estratégia-2--module-level-flattened)
  - [Estratégia 3 — Scope-level flattened](#estratégia-3--scope-level-flattened)
  - [Estratégia 4 — Global flattened](#estratégia-4--global-flattened)
  - [Ambiguidade](#ambiguidade)
- [Providers](#providers)
  - [FileProvider](#fileprovider)
  - [SystemEnvProvider](#systemenvprovider)
  - [OverrideProvider](#overrideprovider)
  - [Provider customizado](#provider-customizado)
- [Perfis de ambiente](#perfis-de-ambiente)
- [Schema binding](#schema-binding)
- [Watchers e Hot Reload](#watchers-e-hot-reload)
- [Diagnósticos e erros](#diagnósticos-e-erros)
- [Referência de API](#referência-de-api)
- [Arquitectura interna](#arquitectura-interna)
- [Comparação com dotenv](#comparação-com-dotenv)

---

## Instalação

O package `loom` faz parte da biblioteca `nestifypy`. Coloca a pasta `loom/` dentro do teu package:

```
nestifypy/
├── __init__.py
├── loom/
│   ├── __init__.py
│   ├── ast_nodes.py
│   ├── exceptions.py
│   ├── lexer.py
│   ├── parser.py
│   ├── providers.py
│   ├── resolver.py
│   ├── runtime.py
│   ├── schema.py
│   └── scope.py
├── bolt/
└── ...
```

Importação principal:

```python
from nestifypy.loom import Loom, env
```

---

## Início Rápido

**1. Cria o teu ficheiro de configuração:**

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
}
```

**2. Carrega e acede em Python:**

```python
from nestifypy.loom import Loom, env

Loom.load("app.loom")

# Acesso hierárquico
host  = env.app.server.host       # LoomValue → "localhost"
port  = env.app.server.port.int   # 8080  (int nativo)
debug = env.app.server.debug.bool # True  (bool nativo)

# Smart Resolution — podes omitir níveis intermédios
host  = env.server.host   # funciona (scope-level flattening)
port  = env.port          # funciona se "port" for único globalmente

# Acesso a scope completo
server_scope = env.app.server
print(server_scope.keys())    # ['host', 'port', 'debug']
print(server_scope.path)      # 'server'
print(server_scope.module)    # 'app'
```

---

## Formato .loom

### Declaração de módulo

Todo o ficheiro `.loom` DEVE começar com uma declaração `@module`. Ela define o domínio lógico e, opcionalmente, o perfil de ambiente.

```loom
@module("database")
```

```loom
@module("database", env: "prod")
```

**Regras:**
- Deve aparecer no topo do ficheiro, antes de qualquer scope
- O nome do módulo é case-insensitive
- Apenas uma declaração `@module` por ficheiro
- O argumento `env` usa `:` (colon), não `=`

---

### Scopes

Os scopes definem namespaces hierárquicos. Suportam dois estilos sintáticos funcionalmente idênticos — ambos geram o mesmo AST.

**Block syntax** (recomendado para múltiplas propriedades):

```loom
@db.main {
    host: "localhost"
    port: 5432
    driver: "postgres"
}
```

**Inline syntax** (útil para poucos campos):

```loom
@db.main { host: "localhost", port: 5432 }
```

Os paths de scope são separados por pontos e podem ter múltiplos níveis:

```loom
@app.server.http {
    port: 80
}
```

Acesso em Python:

```python
env.app.app.server.http.port  # fully qualified
env.http.port                 # scope-level flattened (se único)
```

---

### Propriedades e tipos

Propriedades usam **obrigatoriamente** a notação com `:` (colon). O sinal `=` é reservado para argumentos de directivas e provoca um `LoomSyntaxError` com hint de correcção se usado por engano.

```loom
key: value
```

#### String

Strings com espaços ou caracteres especiais devem ser entre aspas duplas. Strings alfanuméricas simples podem ser sem aspas.

```loom
name: "Loom API"
driver: postgres
path: "/var/log/app.log"
```

#### Integer

```loom
port: 5432
workers: 4
timeout: 30
```

#### Float

```loom
ratio: 0.75
pi: 3.1415
threshold: 1.5e-3
```

#### Boolean

Apenas os literais `true` e `false` são aceites (case-insensitive). Esta restrição evita colisões de inferência.

```loom
debug: true
ssl: false
enabled: True   # também válido
```

#### Null

```loom
secret: null
optional_field: null
```

#### Lista

```loom
hosts: ["localhost", "10.0.0.1", "10.0.0.2"]
ports: [8080, 8081, 8082]
flags: [true, false, true]
```

#### Inferência automática de tipos

| Valor no ficheiro | Tipo Python inferido |
|-------------------|----------------------|
| `5432`            | `int`                |
| `3.14`            | `float`              |
| `true` / `false`  | `bool`               |
| `"hello"`         | `str`                |
| `postgres`        | `str` (bare word)    |
| `null`            | `None`               |
| `["a", "b"]`      | `list`               |

---

### Objetos Aninhados e Indentação

O Loom suporta objetos e propriedades aninhadas de forma flexível utilizando chaves `{}` ou blocos baseados em indentação (estilo YAML). Objetos aninhados podem ter profundidade arbitrária.

#### 1. Sintaxe Inline (Chaves)
Útil para configurações curtas ou definições em linha única:
```loom
@db {
    pool: { min: 2, max: 10 }
}
```

#### 2. Sintaxe Multi-linha (Chaves)
Ideal para blocos maiores que requerem estrutura organizada por chaves:
```loom
@db {
    pool: {
        min: 2,
        max: 10
    }
}
```

#### 3. Sintaxe Indentada (Estilo YAML)
O Loom permite omitir as chaves e utilizar apenas quebras de linha seguidas por indentação maior para definir objetos aninhados.
```loom
@db {
    pool:
        min: 2
        max: 10
}
```

#### Regras de Indentação:
- Um sub-bloco de indentação começa quando o valor de uma propriedade é omitido (apenas `:` seguido de quebra de linha) e a linha seguinte tem uma indentação maior.
- O sub-bloco termina quando a indentação retorna ao mesmo nível ou a um nível inferior.
- **Inconsistência**: Todos os campos do mesmo sub-bloco devem estar alinhados na mesma coluna. Indentação inconsistente levanta um erro `LoomSyntaxError`.
- **Mistura de Tabs e Spaces**: Misturar caracteres de tabulação (`\t`) e espaços na indentação é estritamente proibido e levanta erro explícito.

#### Acesso no Python:
```python
# Acesso direto a propriedades aninhadas através de atributos:
min_val = env.db.pool.min.int   # 2
max_val = env.db.pool.max.int   # 10

# Acesso através de indexação flat
min_val = env.pool.min.int      # 2 (se 'pool.min' for globalmente único)
```

---

### Comentários

Comentários de linha única com `#`. Podem aparecer em linha própria ou inline após um valor.

```loom
# Configuração principal do servidor
@server {
    host: "localhost"   # endereço de bind
    port: 8080          # porta HTTP padrão
}
```

---

### Imports

O `@import` permite composição modular — dividir a configuração em múltiplos ficheiros.

```loom
@import("./database.loom")
@import("./modules/cache.loom")
```

Suporte a wildcards:

```loom
@import("./modules/*.loom")
```

Imports são resolvidos recursivamente. Ciclos de import são detectados automaticamente e ignorados.

**Exemplo de estrutura modular:**

```
config/
├── app.loom          # @import("./database.loom"), @import("./cache.loom")
├── database.loom     # @module("database") ...
└── cache.loom        # @module("cache") ...
```

```python
Loom.load("config/app.loom")   # carrega tudo automaticamente
```

---

### Default Scopes

Quando múltiplos scopes têm propriedades com o mesmo nome, o acesso flattened seria ambíguo. O sufixo `*` designa um scope como padrão para resolver essa ambiguidade.

```loom
@module("database")

@db.main* {
    host: "primary.db.example.com"
    port: 5432
}

@db.replica {
    host: "replica.db.example.com"
    port: 5432
}
```

```python
env.database.host   # → "primary.db.example.com"  (via default scope)
env.database.db.replica.host  # → "replica.db.example.com"  (path explícito, ignora default)
```

**Regras:**
- Apenas um default scope por nível de hierarquia
- Múltiplos defaults no mesmo nível levantam `LoomScopeConflictError`
- Paths explícitos (fully qualified) sempre ignoram a lógica de default scope

---

## Runtime

### Carregar ficheiros

```python
from nestifypy.loom import Loom, env

# Ficheiro único
Loom.load("app.loom")

# Com perfil de ambiente
Loom.load("database.loom", profile="prod")

# Múltiplos ficheiros
Loom.load(["app.loom", "database.loom", "cache.loom"])

# Glob pattern
Loom.load("config/*.loom")

# Fonte inline (útil em testes)
Loom.load_source('''
    @module("test")
    @server { port: 9999 }
''')

# Provider customizado
from nestifypy.loom import SystemEnvProvider
Loom.register_provider(SystemEnvProvider(prefix="APP_"))
```

Múltiplas chamadas a `load()` são cumulativas. A última definição do mesmo módulo+scope+chave vence (last-write-wins).

---

### Auto-Descoberta de Ficheiros (Auto-Discovery)

Ao carregar ficheiros com `Loom.load()`, podes omitir o caminho completo do ficheiro ou até mesmo a extensão `.loom`. O Loom tentará descobrir e resolver o ficheiro automaticamente com base na seguinte ordem de prioridades:

1. **Caminho informado explicitamente**: O caminho absoluto ou relativo exato passado (e.g. `Loom.load("app.loom")` ou `Loom.load("app")` no diretório local).
2. **Diretório Atual**: Procura no diretório atual de execução (`cwd`).
3. **Diretório `config/`**: Procura em `./config/` relativo ao diretório atual.
4. **Raiz do Projeto**: Deteta a raiz do projeto (procurando por `.git`, `pyproject.toml` ou `setup.py`) e procura o ficheiro nela.
5. **Diretórios Pais**: Sobe a árvore de diretórios a partir do diretório atual em busca do ficheiro.
6. **Busca Recursiva**: Se nenhuma das opções anteriores encontrar o ficheiro, o Loom executará uma busca recursiva a partir da raiz do projeto.

#### Resolução Determinística de Duplicados
Caso existam múltiplos ficheiros com o mesmo nome na árvore de busca (e.g., `app.loom` e `subdir/app.loom`), a busca determinística escolherá:
1. O ficheiro localizado no diretório mais raso (menor profundidade de diretório).
2. Desempate por ordem alfabética do caminho absoluto.

```python
# Procura por "config/app.loom", "./app.loom", etc.
Loom.load("app")
```

---

### Acesso por atributos

O objecto `env` é um proxy lazy que constrói o caminho de resolução à medida que os atributos são acedidos:

```python
from nestifypy.loom import env

# Cada ponto acrescenta um segmento ao path
env.database              # → _EnvProxy(parts=["database"])
env.database.db           # → _EnvProxy(parts=["database", "db"])
env.database.db.main      # → ScopeObject (resolvido)
env.database.db.main.host # → LoomValue("localhost")
```

O `env` global partilha o estado do `Loom` global. Para instâncias isoladas (testes, multi-tenant):

```python
from nestifypy.loom import LoomRuntime

rt = LoomRuntime()
rt.load("app.loom")

host = rt.env.app.server.host
```

---

### LoomValue e type casts

Todas as propriedades resolvidas retornam um `LoomValue` — um wrapper thin que mantém o valor original e expõe conversões de tipo explícitas.

```python
val = env.database.db.main.port   # LoomValue(5432)

# Casts explícitos via propriedade
val.int      # 5432       (int nativo)
val.float    # 5432.0     (float nativo)
val.bool     # True       (truthy)
val.str      # "5432"     (str nativo)
val.list     # [5432]     (wrapped em lista se escalar)
val.value    # 5432       (valor raw Python)

# Protocolos Python nativos
int(val)     # 5432
float(val)   # 5432.0
bool(val)    # True
str(val)     # "5432"

# Comparações directas
val == 5432       # True
val == "5432"     # False
```

`LoomValue` levanta `LoomTypeError` em casts inválidos:

```python
LoomValue("not_a_number").int
# LoomTypeError: Cannot cast 'not_a_number' to int
# Hint: Path '...' has value 'not_a_number' which is not numeric.
```

---

### ScopeObject

Aceder a um scope (sem especificar uma propriedade terminal) retorna um `ScopeObject`. Este nunca é automaticamente desembrulhado para um escalar — garantia de previsibilidade estrutural do spec §13.2.

```python
scope = env.database.db.main   # ScopeObject

# Introspeção dict-like
scope.keys()      # ["host", "port", "driver", "debug"]
scope.values()    # [LoomValue("localhost"), LoomValue(5432), ...]
scope.items()     # [("host", LoomValue("localhost")), ...]
scope.get("host") # LoomValue("localhost")
scope.get("missing", "default")  # "default"

# Metadados
scope.path        # "db.main"
scope.module      # "database"
scope.parent      # ScopeObject pai ou None

# Operadores Python
"host" in scope   # True
len(scope)        # 4
for key, val in scope:
    print(f"{key} = {val.value}")
```

Acesso a propriedade via atributo:

```python
scope.host        # LoomValue("localhost")
scope.port.int    # 5432
scope["host"]     # LoomValue("localhost") — sintaxe alternativa
```

`ScopeObject` é **imutável** — qualquer tentativa de escrita levanta `AttributeError`.

---

## Smart Resolution

O motor de Smart Resolution permite omitir níveis intermédios do path desde que o resultado seja único. É a feature mais poderosa do Loom.

A resolução tenta as 4 estratégias em ordem e para na primeira que for determinística.

### Estratégia 1 — Fully qualified

O path completo `módulo.scope_path.chave`. Nunca ambíguo. Sempre preferível em código de produção.

```python
env.database.db.main.host      # "localhost"
env.database.db.replica.host   # "10.0.0.5"
```

### Estratégia 2 — Module-level flattened

Omite os segmentos do scope, mantendo o nome do módulo.

```loom
@module("database")
@db.main { host: "localhost", port: 5432 }
@db.replica { host: "10.0.0.5" }
```

```python
env.database.port    # → 5432  (único no módulo "database")
env.database.host    # LoomAmbiguityError — "host" existe em db.main e db.replica
```

### Estratégia 3 — Scope-level flattened

Omite o nome do módulo, usa apenas o path do scope.

```python
env.main.host      # → "localhost"  (scope "main" é único globalmente)
env.replica.host   # → "10.0.0.5"
```

### Estratégia 4 — Global flattened

Usa apenas o nome da chave — resolve se for globalmente única.

```loom
# server.loom
@module("server")
@app { port: 8080 }
```

```python
env.port    # → 8080  (se "port" existir apenas num módulo)
```

### Ambiguidade

Quando múltiplas candidatas existem e nenhum default scope resolve o conflito, o runtime levanta `LoomAmbiguityError` — nunca adivinha.

```python
env.database.host
# LoomAmbiguityError: Ambiguous path 'database.host' resolves to multiple values
# Found: 2 candidates: database.db.main.host, database.db.replica.host
# Hint: Use a fully qualified path (e.g. env.database.db.main.host)
#       or mark one scope as default with '*' (e.g. @db.main* {...})
```

**Resumo das estratégias:**

| Acesso | Estratégia | Condição para funcionar |
|--------|-----------|------------------------|
| `env.database.db.main.host` | 1. Fully qualified | Sempre funciona |
| `env.database.host` | 2. Module-level | `host` único no módulo |
| `env.main.host` | 3. Scope-level | Scope `main` único globalmente |
| `env.port` | 4. Global | `port` único em todos os módulos |

---

## Providers

Os providers são a fonte de dados do Loom runtime. Múltiplos providers podem ser registados — o último a definir uma chave vence (last-write-wins).

### FileProvider

Carrega ficheiros `.loom` do disco. Suporta ficheiro único, glob pattern, ou lista de paths.

```python
from nestifypy.loom import FileProvider, LoomRuntime

rt = LoomRuntime()

# Ficheiro único
rt.register_provider(FileProvider("app.loom"))

# Glob
rt.register_provider(FileProvider("config/*.loom"))

# Lista de ficheiros
rt.register_provider(FileProvider(["app.loom", "database.loom"]))

# Com base_dir
rt.register_provider(FileProvider("*.loom", base_dir="/etc/myapp/"))

# Com perfil
rt.register_provider(FileProvider("app.loom", profile="prod"))
```

**Prioridade de perfil** — para cada ficheiro `app.loom`, o FileProvider verifica automaticamente:

```
1. app.local.loom       (maior prioridade — nunca commitar)
2. app.prod.loom        (perfil activo)
3. app.loom             (base — menor prioridade)
```

### SystemEnvProvider

Expõe variáveis de ambiente do sistema como um módulo Loom. Útil para injectar segredos em produção sem os escrever em ficheiros.

```python
from nestifypy.loom import SystemEnvProvider, LoomRuntime

rt = LoomRuntime()
rt.register_provider(SystemEnvProvider(
    module="env",        # nome do módulo Loom gerado
    scope="system",      # nome do scope
    prefix="APP_",       # só importa vars com este prefixo (stripped)
    lowercase=True,      # converte chaves para lowercase
))
```

Exemplo com variáveis de ambiente:

```bash
export APP_DATABASE_HOST=prod.db.example.com
export APP_DATABASE_PORT=5432
export APP_DEBUG=false
```

```python
rt.env.env.system.database_host   # "prod.db.example.com"
rt.env.env.system.database_port.int  # 5432
rt.env.env.system.debug.bool      # False
```

**Inferência de tipos:** o `SystemEnvProvider` converte automaticamente `"true"/"false"`, inteiros, floats e `"null"` dos valores string das env vars.

### OverrideProvider

Provider in-memory para overrides em runtime e em testes. Tem a maior prioridade se registado por último.

```python
from nestifypy.loom import OverrideProvider, LoomRuntime

rt = LoomRuntime()
rt.load("app.loom")

# Overrides programáticos (chaining)
overrides = (
    OverrideProvider("database")
    .set("db.main", "host", "test.db.local")
    .set("db.main", "port", 5433)
)
rt.register_provider(overrides)

rt.env.database.db.main.host   # "test.db.local"
```

Ideal para testes de integração onde se quer substituir valores de ficheiro sem alterar os ficheiros.

### Provider customizado

Implementa a interface `Provider` para criar fontes de dados personalizadas (Vault, Redis, HTTP, etc.):

```python
from nestifypy.loom.providers import Provider
from nestifypy.loom.ast_nodes import ModuleNode, ScopeNode, PropertyNode, LiteralNode

class VaultProvider(Provider):
    def __init__(self, vault_url: str, token: str) -> None:
        self._url = vault_url
        self._token = token

    def load(self) -> list[ModuleNode]:
        # Buscar segredos do Vault
        secrets = self._fetch_from_vault()

        props = [
            PropertyNode(key=k, value=LiteralNode(value=v))
            for k, v in secrets.items()
        ]
        scope = ScopeNode(path=["secrets"], properties=props)
        return [ModuleNode(name="vault", scopes=[scope])]

    def _fetch_from_vault(self) -> dict:
        # ... lógica de fetch
        return {"db_password": "s3cr3t", "api_key": "abc123"}

Loom.register_provider(VaultProvider("https://vault.example.com", token="..."))
```

---

## Perfis de ambiente

O Loom suporta configuração por ambiente sem duplicar ficheiros. O padrão recomendado:

```
config/
├── database.loom          # valores base (commitados)
├── database.dev.loom      # overrides de dev (commitados)
├── database.prod.loom     # overrides de prod (commitados)
└── database.local.loom    # overrides locais (no .gitignore)
```

**database.loom** (base):
```loom
@module("database")
@db.main {
    host: "localhost"
    port: 5432
    debug: true
}
```

**database.prod.loom** (overrides de produção):
```loom
@module("database")
@db.main {
    host: "db.prod.example.com"
    debug: false
}
```

**Python:**
```python
import os
profile = os.getenv("APP_ENV", "dev")
Loom.load("config/database.loom", profile=profile)

# Em dev: host="localhost", debug=True
# Em prod: host="db.prod.example.com", debug=False
```

**Prioridade de resolução completa** (spec §12):
```
1. Runtime overrides (OverrideProvider)
2. Variáveis de ambiente (SystemEnvProvider)
3. *.local.loom
4. *.<profile>.loom
5. base *.loom
6. Defaults de schema
```

---

## Schema binding

O `@loom.bind` liga um `dataclass` a um módulo e scope Loom. Os valores são resolvidos automaticamente no runtime, com fallback para os defaults do dataclass.

```python
import dataclasses
from nestifypy.loom import Loom

Loom.load("database.loom")

@Loom.bind("database", scope="db.main")
@dataclasses.dataclass
class DatabaseConfig:
    host: str = "127.0.0.1"
    port: int = 5432
    debug: bool = False
    name: str = "app"

cfg = DatabaseConfig()
print(cfg.host)   # valor do Loom, ou "127.0.0.1" se não definido
print(cfg.port)   # valor do Loom com coerção para int
```

**Prioridade de resolução** dentro do schema binding:

```
1. Kwargs explícitos:        DatabaseConfig(host="override")
2. Valor no runtime Loom:    definido no .loom file
3. Default do dataclass:     host: str = "127.0.0.1"
4. LoomSchemaError:          campo obrigatório sem valor nem default
```

**Campo obrigatório sem valor:**

```python
@Loom.bind("database", scope="db.main")
@dataclasses.dataclass
class StrictConfig:
    password: str      # obrigatório — sem default

cfg = StrictConfig()
# LoomSchemaError: Required field 'password' of 'StrictConfig' has no value
# in Loom scope 'database.db.main' and no default.
# Hint: Either add a value to your .loom file or define a default in the dataclass.
```

**Coerção de tipos automática:** se o Loom tiver o valor como string `"5432"` e o dataclass declarar `port: int`, a coerção é feita automaticamente.

**Instâncias isoladas:**

```python
from nestifypy.loom import LoomRuntime

rt = LoomRuntime()
rt.load("database.loom")

@rt.bind("database", scope="db.main")
@dataclasses.dataclass
class DbConfig:
    host: str = "localhost"
    port: int = 5432
```

---

## Watchers e Hot Reload

O runtime suporta callbacks para mudanças de valores. Os watchers são invocados manualmente por `notify_watchers()` ou por integrações de hot-reload.

```python
from nestifypy.loom import Loom

Loom.load("app.loom")

@Loom.watch("db.main.host")
def on_host_change(new_value):
    print(f"Host changed to: {new_value}")
    reconnect_database(new_value)

@Loom.watch("server.port")
def on_port_change(new_value):
    restart_http_server(int(new_value))
```

Invocar manualmente (útil em custom hot-reload):

```python
Loom.notify_watchers("db.main.host", "new.db.host")
# → chama on_host_change("new.db.host")
```

**Exemplo de hot-reload com watchdog** (biblioteca externa):

```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class LoomReloadHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith(".loom"):
            Loom.reload()
            print("Configuration reloaded")

observer = Observer()
observer.schedule(LoomReloadHandler(), path="config/", recursive=False)
observer.start()
```

---

## Diagnósticos e erros

O Loom produz erros detalhados com formato inspirado no compilador Rust: ficheiro, linha, coluna, snippet do código, token encontrado vs esperado, e hint de correcção.

### LoomSyntaxError

```loom
# database.loom, linha 4
@db.main {
    host = "localhost"    # ← usa '=' em vez de ':'
}
```

```
🚨 LoomSyntaxError in 'database.loom' (Line 4)

    3 | @db.main {
    4 |     host = "localhost"
               ^
    5 | }

Error:
  Property 'host' uses '=' instead of ':'

Found:
  '='

Expected:
  ':'

Hint:
  Replace with: host: "localhost"
```

### LoomAmbiguityError

```
🚨 LoomAmbiguityError

Error:
  Ambiguous path 'database.host' resolves to multiple values

Found:
  2 candidates: database.db.main.host, database.db.replica.host

Expected:
  a unique property

Hint:
  Use a fully qualified path (e.g. env.database.db.main.host)
  or mark one scope as default with '*' (e.g. @db.main* {...})
```

### Todos os tipos de erro

| Excepção | Quando é levantada |
|----------|-------------------|
| `LoomSyntaxError` | Sintaxe inválida no ficheiro `.loom` |
| `LoomTypeError` | Cast de tipo impossível (e.g. `"abc".int`) |
| `LoomResolutionError` | Path não encontrado em nenhum módulo |
| `LoomAmbiguityError` | Path flattened resolve para múltiplos candidatos |
| `LoomImportError` | `@import` falha (ficheiro não encontrado, permissão negada) |
| `LoomSchemaError` | Campo obrigatório sem valor no runtime nem default no dataclass |
| `LoomScopeConflictError` | Múltiplos default scopes `*` no mesmo nível de hierarquia |

Todos herdam de `LoomError` e podem ser capturados em conjunto:

```python
from nestifypy.loom import LoomError

try:
    Loom.load("app.loom")
    host = env.database.db.main.host
except LoomError as e:
    print(f"Configuration error: {e}")
```

---

## Referência de API

### `Loom` / `LoomRuntime`

```python
Loom.load(path, profile=None)
# Carrega ficheiro(s) .loom. Retorna self para chaining.

Loom.load_source(source, filename="<string>")
# Carrega source text directamente.

Loom.register_provider(provider)
# Regista e carrega um Provider. Retorna self.

Loom.reload()
# Recarrega todos os providers registados do zero.

Loom.modules()
# Retorna lista de nomes de módulos carregados.

Loom.explain("db.main.host")
# Retorna string descrevendo como o path foi resolvido.

Loom.watch("path.to.key")
# Decorator para registar callback de mudança.

Loom.notify_watchers("path", new_value)
# Invoca todos os callbacks registados para o path.

Loom.bind("module", scope="scope.path")
# Decorator factory para binding de dataclasses.

Loom.env
# Retorna o proxy _EnvProxy para acesso por atributos.
```

### `env`

```python
from nestifypy.loom import env

# O env global é um alias para Loom.env
env.module.scope.key       # → LoomValue
env.module.scope           # → ScopeObject
env.key                    # → LoomValue (global flattening)
```

### `LoomValue`

```python
val.int        # cast para int
val.float      # cast para float
val.bool       # cast para bool
val.str        # cast para str
val.list       # cast para list
val.value      # valor raw Python
val.path       # path completo resolvido
val.module     # nome do módulo de origem

int(val)       # protocolo __int__
float(val)     # protocolo __float__
bool(val)      # protocolo __bool__
str(val)       # protocolo __str__
val == other   # comparação directa com raw value
```

### `ScopeObject`

```python
scope.keys()           # list[str]
scope.values()         # list[LoomValue]
scope.items()          # list[tuple[str, LoomValue]]
scope.get(key, default=None)
scope.path             # str — path dotted do scope
scope.module           # str — nome do módulo
scope.parent           # ScopeObject | None

"key" in scope         # bool
len(scope)             # int
for k, v in scope:     # iteração (key, LoomValue)
scope.key              # LoomValue (acesso por atributo)
scope["key"]           # LoomValue (acesso por subscript)
```

### Providers

```python
FileProvider(paths, profile=None, base_dir=None)
SystemEnvProvider(module="env", scope="system", prefix="", lowercase=True)
OverrideProvider(module_name="overrides")
    .set(scope, key, value)   # retorna self para chaining
```

---

## Arquitectura interna

```
.loom source text
      │
      ▼
  [lexer.py]          Tokeniza em Token(TT, value, line, col)
      │
      ▼
  [parser.py]         Parser recursivo-descendente → AST
      │
      ▼
  [ast_nodes.py]      ModuleNode, ScopeNode, PropertyNode, LiteralNode, ListNode
      │
      ▼
  [resolver.py]       Índice flat de _Entry + motor de 4 estratégias
      │
      ▼
  [runtime.py]        LoomRuntime + _EnvProxy + _ScopeProxy
      │
      ▼
  [scope.py]          ScopeObject (ABCMeta) + LoomValue
```

### Fluxo de resolução detalhado

Quando se acede a `env.database.db.main.host`:

1. `env.database` → `_EnvProxy(parts=["database"])`; resolve falha → acumula
2. `.db` → `_EnvProxy(parts=["database", "db"])`; resolve falha → acumula (`"database"` é módulo conhecido)
3. `.main` → `_EnvProxy(parts=["database", "db", "main"])`; resolve → `ScopeObject` → `_ScopeProxy`
4. `.host` → `_ScopeProxy.__getattr__("host")` → `LoomValue("localhost")`

### Por que `ScopeObject` é `ABCMeta`

O `_ScopeProxy` não herda de `ScopeObject` directamente (evitaria conflitos de `__setattr__` e `__getattr__`), mas é registado como subclasse virtual via `ScopeObject.register(_ScopeProxy)`. Isto garante que `isinstance(env.db.main, ScopeObject)` retorna `True` per spec §13.2, sem herança real.

---

## Comparação com dotenv

| Feature | `python-dotenv` | `nestifypy.loom` |
|---------|----------------|-----------------|
| Formato | `KEY=VALUE` flat | Hierárquico, modular, tipado |
| Tipos | Tudo string | Inferência automática |
| Namespaces | Prefixos manuais (`DB_HOST`) | `env.database.db.main.host` |
| Múltiplos ambientes | Ficheiros `.env.prod` manuais | Profile-aware automático |
| Validação | Nenhuma | Schema binding + LoomSchemaError |
| Erros | Genéricos | Diagnósticos estilo Rust |
| Imports | Não | `@import("./modulo.loom")` |
| Acesso | `os.environ["KEY"]` | `env.db.main.host.int` |
| Providers | Só ficheiro | File, EnvVar, Override, custom |
| Watchers | Não | `@Loom.watch("path")` |
| Smart Resolution | Não | 4 estratégias de flattening |
| Dependências | `python-dotenv` | Nenhuma (stdlib only) |

---

*`nestifypy.loom` — parte da biblioteca nestifypy. Especificação: Loom v0.1.*
