# Promise (`nestifypy.promise`)

> Programação assíncrona sem asyncio, event loops ou futures.  
> Inspirado em JavaScript Promises, Java CompletableFuture e C# Tasks.

---

## Importação

```python
from nestifypy.promise import Promise
```

---

## Criação

```python
# A partir de qualquer callable
Promise.of(load_user)

# Lambda inline
Promise.of(lambda: 10 + 20)

# Já resolvida / rejeitada (útil para testes)
Promise.resolved(42)
Promise.rejected(RuntimeError("algo falhou"))
```

### Obter o resultado (bloqueia a thread atual)

```python
result = Promise.of(lambda: 10 + 20).join()
print(result)  # 30

# Com timeout de espera
result = Promise.of(long_task).join(timeout=10)
```

---

## Encadeamento

### `.then(fn)` — reage ao sucesso (não transforma o valor)

```python
Promise.of(load_user).then(print)
```

### `.map(fn)` — transforma o resultado

```python
Promise.of(load_user) \
       .map(lambda user: user.name) \
       .map(str.upper) \
       .then(print)
```

### `.flat_map(fn)` — `fn` retorna outra Promise

```python
Promise.of(load_user) \
       .flat_map(lambda user: Promise.of(lambda: load_profile(user))) \
       .then(print)
```

---

## Tratamento de erros

### `.catch(fn)` — reage à falha

```python
Promise.of(load_user).catch(print)
```

### `.recover(fn)` — transforma falha em sucesso

```python
Promise.of(load_user) \
       .recover(lambda ex: GuestUser()) \
       .then(print)
```

### `.finally_(fn)` — sempre executado, independente do resultado

```python
Promise.of(load_user) \
       .finally_(cleanup)
```

---

## Operações avançadas

### `.timeout(seconds)` — cancela se demorar demais

```python
Promise.of(api_request).timeout(5).catch(log_timeout)
```

### `.delay(seconds)` — atrasa a propagação do resultado

```python
Promise.of(sync_database).delay(2).then(print)
```

### Retry nativo em `.of()` — recomendado

```python
# Tenta até 3 vezes com 0.5s entre tentativas (padrão)
Promise.of(api_request, retry=3, retry_delay=1.0)
```

### Delay de início em `.of()`

```python
# Aguarda 5s antes de começar
Promise.of(sync_database, delay=5)
```

### Timeout de execução em `.of()`

```python
# Combinando delay + timeout + retry numa linha
Promise.of(api_request, delay=1, timeout=10, retry=3)
```

---

## Callbacks nomeados

```python
Promise.of(load_user) \
       .on_success(lambda user: print("Bem-vindo,", user.name)) \
       .on_failure(lambda ex: print("Erro:", ex)) \
       .on_cancel(lambda: print("Operação cancelada"))
```

---

## Cancelamento

```python
promise = Promise.of(long_task)
# ... mais tarde ...
promise.cancel()
```

---

## Estado

```python
promise.is_running()    # Ainda em execução
promise.is_completed()  # Terminou com sucesso
promise.is_failed()     # Terminou com erro
promise.is_cancelled()  # Foi cancelada
promise.state           # String: "RUNNING", "COMPLETED", "FAILED", "CANCELLED"
```

---

## Execução paralela

### `Promise.all(*fns)` — todos em paralelo, retorna lista ordenada

```python
results = Promise.all(
    load_users,
    load_orders,
    load_products,
).join(timeout=30)

# results → [users, orders, products]
```

Falha se **qualquer** uma falhar (lança `PromiseAllError` com lista de erros indexados).

### `Promise.race(*fns)` — retorna o **primeiro** a terminar (sucesso ou falha)

```python
Promise.race(server1, server2, server3).then(use_fastest)
```

### `Promise.any(*fns)` — retorna o **primeiro sucesso**

```python
Promise.any(api1, api2, api3).then(use_first_success)
# Só falha se TODAS falharem → PromiseAnyError
```

---

## Combinação de duas Promises

```python
Promise.of(load_users) \
       .then_combine(
           Promise.of(load_orders),
           lambda users, orders: {
               "users": users,
               "orders": orders,
           }
       ).then(print)
```

---

## Exemplo completo

```python
from nestifypy.promise import Promise

def sync_database():
    # simula operação real
    import time; time.sleep(0.1)
    return {"records": 42}

def log_error(ex):
    print(f"[ERROR] {ex}")

def cleanup():
    print("[cleanup] conexão fechada")

Promise.of(sync_database, delay=0, timeout=30, retry=3) \
       .map(lambda result: result["records"]) \
       .then(lambda n: print(f"Sincronizados {n} registos")) \
       .catch(log_error) \
       .finally_(cleanup)
```

---

## Exceções

| Exceção | Quando é lançada |
|---|---|
| `PromiseTimeoutError` | Timeout atingido em `.timeout()` ou `.join(timeout=n)` |
| `PromiseCancelledError` | `.join()` numa Promise cancelada |
| `PromiseAllError` | Uma ou mais Promises em `Promise.all()` falharam |
| `PromiseAnyError` | Todas as Promises em `Promise.any()` falharam |

---

## Backends internos

A implementação usa `concurrent.futures.ThreadPoolExecutor` com pool global reutilizável. Sem asyncio, sem event loops expostos.

```
Promise
│
├── ThreadPoolExecutor (pool global lazy)
├── threading.Event   (sincronização de estado)
└── threading.Lock    (thread-safe callbacks)
```

---

## Integração com Try (planeado)

```python
Promise.of(
    lambda: Try.of(sync_database).recover(lambda ex: restore_backup())
)
```

## Integração com Scheduler (planeado)

```python
Scheduler.every(10).minutes(
    lambda:
        Promise.of(sync_database, retry=3, timeout=60)
               .catch(log_error)
)
```
