# Try (`nestifypy.trying`)

> Tratamento funcional de erros sem `try/except` espalhados pelo código.  
> Inspirado em Java/Kotlin `Try`, Rust `Result` e Scala `Either`.

---

## Importação

```python
from nestifypy.trying import Try
```

---

## Filosofia

**Antes (Python tradicional):**

```python
try:
    user = load_user()
    if not user.active:
        raise Exception("Inactive")
    print(user.name)
except Exception:
    print("Guest")
```

**Depois (Nestifypy Try):**

```python
Try.of(load_user) \
   .filter(lambda u: u.active, "Inactive user") \
   .map(lambda u: u.name) \
   .recover(lambda ex: "Guest") \
   .on_success(print)
```

---

## Dois estados

Um `Try` é sempre um de dois tipos internos:

| Tipo | Representa |
|---|---|
| `Success(value)` | Operação bem-sucedida |
| `Failure(error)` | Operação falhada |

Todos os métodos de encadeamento **nunca lançam exceções** — erros são capturados e convertidos em `Failure` automaticamente.

---

## Criação

```python
# A partir de qualquer callable
Try.of(load_user)
Try.of(lambda: int("42"))

# Já resolvido / falhado (útil para testes e composição)
Try.success(42)
Try.failure(RuntimeError("algo falhou"))

# A partir de um valor que pode ser None
Try.of_nullable(user_or_none, "User not found")
Try.of_nullable(config.get("key"))
```

---

## Estado

```python
t = Try.of(load_user)

t.is_success()   # True se bem-sucedido
t.is_failure()   # True se falhou
bool(t)          # True se Success, False se Failure
```

---

## Obtenção de valor

```python
# Retorna o valor ou lança a exceção original
value = Try.of(load_user).get()

# Retorna o valor ou None
user = Try.of(load_user).get_or_none()

# Retorna o valor ou um default
name = Try.of(load_user).map(lambda u: u.name).get_or_default("Guest")

# Alias fluente para get_or_default — ideal no fim de cadeias
name = (
    Try.of(load_user)
       .map(lambda u: u.name)
       .or_else("Guest")
)

# Obtém a exceção (None se Success)
error = Try.of(risky).get_error()
```

---

## Transformação

### `.map(fn)` — transforma o valor

Ignorado em `Failure`. Se `fn` lançar exceção, converte em `Failure`.

```python
Try.of(load_user) \
   .map(lambda u: u.name) \
   .map(str.upper)
```

### `.flat_map(fn)` — `fn` retorna outro Try

Para compor operações que também podem falhar.

```python
Try.of(load_user) \
   .flat_map(lambda u: Try.of(lambda: load_profile(u)))
```

### `.map_error(fn)` — transforma a exceção

Ignorado em `Success`. Útil para normalizar tipos de erro.

```python
Try.of(db_query) \
   .map_error(lambda e: DatabaseError(f"Query failed: {e}"))
```

---

## Filtragem

### `.filter(predicate, message)` — converte Success em Failure se predicado falhar

```python
Try.of(load_user) \
   .filter(lambda u: u.active, "Inactive user") \
   .filter(lambda u: u.age >= 18, "Must be 18+")
```

### `.filter_not(predicate, message)` — inverso do filter

```python
Try.of(load_user) \
   .filter_not(lambda u: u.banned, "User is banned")
```

`Failure` passa sempre sem alteração em ambos os métodos.

---

## Recuperação

### `.recover(fn)` — transforma Failure em Success

```python
Try.of(load_user) \
   .recover(lambda ex: GuestUser())
```

### `.recover_with(fn)` — `fn` retorna outro Try

```python
Try.of(load_user) \
   .recover_with(lambda ex: Try.of(load_cached_user))
```

### `.recover_if(exc_type, fn)` — recupera apenas para um tipo específico

```python
Try.of(load_user) \
   .recover_if(ConnectionError, lambda e: load_from_cache()) \
   .recover_if(TimeoutError, lambda e: GuestUser())
```

Outros tipos de erro passam sem alteração.

---

## Captura seletiva

`.catch()` executa um handler sem alterar o estado do Try — para side-effects como logging.

```python
Try.of(load_user) \
   .catch(ValueError, lambda e: log.warn(f"Bad value: {e}")) \
   .catch(FileNotFoundError, lambda e: log.error(f"File missing: {e}"))
```

---

## Callbacks

```python
Try.of(load_user) \
   .on_success(lambda u: print("Bem-vindo,", u.name)) \
   .on_failure(lambda e: print("Erro:", e)) \
   .on_complete(lambda t: print("Concluído, ok=", t.is_success()))
```

### `.tap(fn)` — side-effect no meio de uma cadeia, sem alterar o valor

```python
Try.of(load_user) \
   .tap(lambda u: log.debug("Loaded user:", u.id)) \
   .map(lambda u: u.profile) \
   .tap(lambda p: log.debug("Profile loaded:", p.id)) \
   .map(lambda p: p.name)
```

---

## Conversão

```python
# Optional (None em caso de falha)
user: Optional[User] = Try.of(load_user).to_optional()

# Lista com 0 ou 1 elemento
items: list = Try.of(load_user).to_list()  # [user] ou []

# Promise (requer nestifypy.promise)
promise = Try.of(load_user).to_promise()

# Iteração direta (0 ou 1 iteração)
for user in Try.of(load_user):
    print(user.name)
```

---

## Exceções

| Exceção | Quando é lançada |
|---|---|
| `FilterError` | `.filter()` ou `.filter_not()` não satisfeito |
| `EmptyValueError` | `Try.of_nullable(None)` |
| `TryError` | Base de todas as exceções do módulo |

---

## Exemplo completo

```python
from nestifypy.trying import Try

def load_user(user_id: int):
    # simula carregamento
    return {"id": user_id, "name": "Alice", "active": True, "age": 25}

def log_error(ex):
    print(f"[ERROR] {type(ex).__name__}: {ex}")

result = (
    Try.of(lambda: load_user(42))
       .filter(lambda u: u["active"], "Inactive user")
       .filter(lambda u: u["age"] >= 18, "Must be 18+")
       .map(lambda u: u["name"])
       .map(str.upper)
       .tap(lambda name: print(f"[DEBUG] Name resolved: {name}"))
       .recover(lambda ex: "Guest")
       .on_success(lambda name: print(f"Hello, {name}!"))
       .on_failure(log_error)
       .or_else("Unknown")
)

print(f"Final: {result}")
# [DEBUG] Name resolved: ALICE
# Hello, ALICE!
# Final: ALICE
```

---

## Integração com Promise

```python
# Try dentro de uma Promise
Promise.of(
    lambda: Try.of(sync_database)
               .recover(lambda ex: restore_backup())
               .get()
)

# Try convertido em Promise
Try.of(load_user) \
   .filter(lambda u: u.active) \
   .to_promise() \
   .then(print) \
   .catch(log_error)
```

## Integração com Scheduler (planeado)

```python
Scheduler.every(5).minutes(
    lambda:
        Try.of(sync_database)
           .on_failure(log_error)
)
```

---

## Resumo da API

| Método | Success | Failure |
|---|---|---|
| `.map(fn)` | Transforma valor | Passa sem alteração |
| `.flat_map(fn)` | `fn` retorna Try | Passa sem alteração |
| `.map_error(fn)` | Passa sem alteração | Transforma exceção |
| `.filter(pred, msg)` | Falha se pred=False | Passa sem alteração |
| `.filter_not(pred, msg)` | Falha se pred=True | Passa sem alteração |
| `.recover(fn)` | Passa sem alteração | Transforma em Success |
| `.recover_with(fn)` | Passa sem alteração | `fn` retorna Try |
| `.recover_if(type, fn)` | Passa sem alteração | Recupera só se tipo bater |
| `.catch(type, handler)` | Passa sem alteração | Side-effect se tipo bater |
| `.on_success(fn)` | Executa `fn(value)` | Ignora |
| `.on_failure(fn)` | Ignora | Executa `fn(error)` |
| `.on_complete(fn)` | Executa `fn(self)` | Executa `fn(self)` |
| `.tap(fn)` | Side-effect, retorna self | Ignora |
| `.get()` | Retorna valor | Lança exceção |
| `.get_or_none()` | Retorna valor | Retorna `None` |
| `.get_or_default(d)` | Retorna valor | Retorna `d` |
| `.or_else(d)` | Retorna valor | Retorna `d` |
| `.to_optional()` | Retorna valor | Retorna `None` |
| `.to_list()` | `[value]` | `[]` |
| `.to_promise()` | `Promise.resolved(v)` | `Promise.rejected(e)` |
