# nestifypy · scheduler

> Sistema de agendamento de tarefas para o Nestifypy — API fluente, thread-safe, sem dependências externas.

**v0.1 · Python 3.11+ · Sem asyncio · Sem dependências externas**

---

## Índice

1. [Visão Geral](#1-visão-geral)
2. [Instalação e Importação](#2-instalação-e-importação)
3. [Quick Start](#3-quick-start)
4. [Referência da API](#4-referência-da-api)
   - 4.1 [Scheduler — fachada estática](#41-scheduler--fachada-estática)
   - 4.2 [\_FluentInterval e \_UnitProxy](#42-_fluentinterval-e-_unitproxy)
   - 4.3 [Job](#43-job)
   - 4.4 [Group](#44-group)
   - 4.5 [Persistência e Execuções Perdidas](#45-persistência-e-execuções-perdidas)
   - 4.6 [Sistema de Eventos — JobEvent](#46-sistema-de-eventos--jobevent)
   - 4.7 [CronExpression](#47-cronexpression)
   - 4.8 [Excepções](#48-excepções)
5. [Padrões Avançados](#5-padrões-avançados)
6. [Cheat Sheet](#6-cheat-sheet)

---

## 1  Visão Geral

O módulo `nestifypy.scheduler` fornece um sistema de agendamento de tarefas completo, com API fluente inspirada nos melhores schedulers do ecossistema Python e Java — sem asyncio, sem dependências externas, 100% thread-safe.

**Principais características:**

- API fluente encadeável — `Scheduler.every(5).minutes(fn).named("x").timeout(30).log()`
- Três modos de agendamento: execução única (`after`), periódico (`every`) e cron jobs (`cron`)
- Parser cron de 5 campos embutido — suporta `*`, `*/n`, `n-m`, listas e nomes (`mon`, `jan`…)
- Persistência de estado em disco com estratégias de recuperação para execuções perdidas
- Grupos de jobs para controlo colectivo (pause / resume / cancel)
- Sistema de eventos (`JobEvent`) com listeners locais e globais
- Suporte a timeout, repeat limit, delay inicial e execução assíncrona por thread pool

---

## 2  Instalação e Importação

```bash
# Instalação
pip install nestifypy-boot
```

```python
# Importação recomendada
from nestifypy.scheduler import Scheduler

# Importação completa (para tipagem e eventos)
from nestifypy.scheduler import (
    Scheduler, Job, JobState, JobEvent,
    Group, CronExpression, MissedStrategy,
    SchedulerError, JobNotFoundError, CronParseError, JobTimeoutError,
)
```

---

## 3  Quick Start

### 3.1  Execução única após delay

```python
import time
from nestifypy.scheduler import Scheduler

def hello():
    print("Olá!")

# Executa hello() uma vez, 5 segundos após esta linha
Scheduler.after(5).seconds(hello)

time.sleep(10)
```

### 3.2  Execução periódica

```python
# Executa sync_data() a cada 10 minutos
Scheduler.every(10).minutes(sync_data)

# Como decorator
@Scheduler.every(30).seconds
def clean_cache():
    print("Cache limpa")
```

### 3.3  Cron job

```python
# Todos os dias à meia-noite
Scheduler.cron("0 0 * * *")(backup)

# Como decorator — segunda-feira às 08:00
@Scheduler.cron("0 8 * * 1")
def weekly_report():
    print("Relatório semanal gerado")

# A cada 5 minutos
@Scheduler.cron("*/5 * * * *")
def heartbeat():
    pass
```

### 3.4  Cadeia completa de configuração

```python
job = (
    Scheduler.every(15).minutes(sync_db)
    .named("db-sync")      # nome para lookup posterior
    .timeout(60)           # cancela se demorar > 60 s
    .repeat(100)           # executa no máximo 100 vezes
    .delay(5)              # aguarda 5 s antes da 1.ª execução
    .group("database")     # associa ao grupo "database"
    .log()                 # activa logging automático
    .async_()              # não bloqueia o scheduler
)
```

---

## 4  Referência da API

---

### 4.1  `Scheduler` — fachada estática

Todos os métodos são `classmethod` — nunca é necessário instanciar `Scheduler`.

#### Factories de agendamento

| Método | Retorna | Descrição |
|---|---|---|
| `Scheduler.after(n)` | `_FluentInterval` | Agenda execução única após `n` unidades de tempo. |
| `Scheduler.every(n)` | `_FluentInterval` | Agenda execução periódica de `n` em `n` unidades. |
| `Scheduler.cron(expr)` | `_CronProxy` | Agenda via expressão cron de 5 campos. |

#### Controlo global

| Método | Retorna | Descrição |
|---|---|---|
| `Scheduler.jobs()` | `List[Job]` | Lista todos os jobs activos (RUNNING / PAUSED). |
| `Scheduler.all_jobs()` | `List[Job]` | Lista todos os jobs incluindo CANCELLED e COMPLETED. |
| `Scheduler.running_jobs()` | `List[Job]` | Apenas jobs em estado RUNNING. |
| `Scheduler.paused_jobs()` | `List[Job]` | Apenas jobs em estado PAUSED. |
| `Scheduler.count()` | `int` | Número de jobs activos. |
| `Scheduler.cancel_all()` | `None` | Cancela todos os jobs activos. |
| `Scheduler.pause_all()` | `None` | Pausa todos os jobs activos. |
| `Scheduler.resume_all()` | `None` | Retoma todos os jobs pausados. |

#### Lookup por nome

| Método | Retorna | Descrição |
|---|---|---|
| `Scheduler.job(name)` | `Job` | Obtém um job pelo nome. Lança `JobNotFoundError` se não existir. |

```python
Scheduler.job("db-sync").cancel()
Scheduler.job("heartbeat").pause()
```

#### Grupos

| Método | Retorna | Descrição |
|---|---|---|
| `Scheduler.group(name)` | `Group` | Obtém ou cria um grupo. Veja [secção 4.4](#44-group). |
| `Scheduler.groups()` | `Dict[str, Group]` | Todos os grupos registados. |

#### Monitorização

| Método | Retorna | Descrição |
|---|---|---|
| `Scheduler.summary()` | `str` | Retorna string com tabela de jobs activos. |
| `Scheduler.print_summary()` | `None` | Imprime o summary no stdout. |

```python
Scheduler.print_summary()
# ────────────────────────────────────────────────────────────
#   Scheduler — 2 job(s) activo(s)
# ────────────────────────────────────────────────────────────
#   db-sync     state=RUNNING   runs=42   last=14:05:00  next=14:20:00
#   heartbeat   state=RUNNING   runs=1200 last=14:05:30  next=14:06:00
# ────────────────────────────────────────────────────────────
```

#### Eventos globais

| Método | Descrição |
|---|---|
| `Scheduler.on_event(fn)` | Regista listener para todos os eventos de todos os jobs. |
| `@Scheduler.on_job_start` | Decorator para eventos de início (`kind == "start"`). |
| `@Scheduler.on_job_complete` | Decorator para eventos de conclusão (`kind == "complete"`). |
| `@Scheduler.on_job_error` | Decorator para eventos de erro (`kind == "error"`). |

---

### 4.2  `_FluentInterval` e `_UnitProxy`

Retornado por `Scheduler.every(n)` e `Scheduler.after(n)`. Especifica a unidade de tempo e recebe a função a executar.

#### Unidades disponíveis

| Propriedade | Equivalência |
|---|---|
| `.second` / `.seconds` | Múltiplos de 1 segundo |
| `.minute` / `.minutes` | Múltiplos de 60 segundos |
| `.hour` / `.hours` | Múltiplos de 3 600 segundos |
| `.day` / `.days` | Múltiplos de 86 400 segundos |
| `.week` / `.weeks` | Múltiplos de 604 800 segundos |

Cada unidade retorna um `_UnitProxy` que pode ser:

- **Chamado como função:** `.minutes(fn)` → agenda e retorna `Job`
- **Usado como decorator:** `@Scheduler.every(5).seconds` → decora a função sem parênteses

```python
# Chamada directa
job = Scheduler.every(5).minutes(sync_users)

# Decorator com chamada
@Scheduler.every(5).minutes
def sync_users():
    ...

# Decorator como propriedade (sem parênteses na unidade)
@Scheduler.every(5).seconds
def heartbeat(): ...
```

---

### 4.3  `Job`

Representa uma tarefa agendada. Retornado por todos os métodos de agendamento. Permite configuração fluente encadeada após o agendamento.

#### Propriedades

| Atributo | Tipo | Descrição |
|---|---|---|
| `job.id` | `str` | UUID curto (8 chars), gerado automaticamente. |
| `job.name` | `str` | Nome legível. Default: `"job-{id}"`. |
| `job.run_count` | `int` | Número total de execuções concluídas. |
| `job.last_run` | `Optional[datetime]` | Data/hora da última execução. |
| `job.next_run` | `Optional[datetime]` | Data/hora prevista da próxima execução. |

#### Métodos de estado

| Método | Retorna | Descrição |
|---|---|---|
| `job.running()` | `bool` | `True` se estado == `RUNNING`. |
| `job.paused()` | `bool` | `True` se estado == `PAUSED`. |
| `job.cancelled()` | `bool` | `True` se estado == `CANCELLED`. |
| `job.completed()` | `bool` | `True` se atingiu o repeat limit. |
| `job.is_active()` | `bool` | `True` se ainda pode executar (não cancelado/completado). |

#### Métodos de controlo

| Método | Retorna | Descrição |
|---|---|---|
| `job.cancel()` | `Job` | Cancela permanentemente. Remove do registo global. |
| `job.pause()` | `Job` | Pausa — aguarda `resume()` para continuar. |
| `job.resume()` | `Job` | Retoma job pausado. |
| `job.run_now()` | `Job` | Executa imediatamente fora do ciclo normal. |

#### Métodos de configuração (encadeáveis)

| Método | Retorna | Descrição |
|---|---|---|
| `.named(name)` | `Job` | Regista nome para `Scheduler.job(name)`. Deve ser único. |
| `.timeout(seconds)` | `Job` | Cancela execução se demorar mais do que `seconds`. |
| `.repeat(times)` | `Job` | Limita o número total de execuções. Estado passa a `COMPLETED`. |
| `.delay(seconds)` | `Job` | Atrasa a primeira execução em `seconds` segundos. |
| `.group(name)` | `Job` | Associa ao grupo. Cria grupo se não existir. |
| `.log()` | `Job` | Activa logging de início, fim e duração no stdout. |
| `.async_()` | `Job` | Executa em thread separada — não bloqueia o scheduler. |
| `.process()` | `Job` | Executa em processo separado (tarefas CPU-bound). |
| `.persistent(...)` | `Job` | Persiste estado em disco. Veja [secção 4.5](#45-persistência-e-execuções-perdidas). |

#### Callbacks de ciclo de vida

| Método | Retorna | Descrição |
|---|---|---|
| `.on_start(fn)` | `Job` | `fn()` chamado antes de cada execução. |
| `.on_complete(fn)` | `Job` | `fn(result)` chamado após execução bem-sucedida. |
| `.on_error(fn)` | `Job` | `fn(exception)` chamado se a execução lançar excepção. |
| `.on_cancel(fn)` | `Job` | `fn()` chamado quando o job é cancelado. |
| `.listen(fn)` | `Job` | `fn(JobEvent)` chamado para todos os eventos. |

```python
job = (
    Scheduler.every(1).minute(process_queue)
    .named("queue-processor")
    .timeout(45)
    .on_start(lambda: print("A processar..."))
    .on_complete(lambda r: metrics.record(r))
    .on_error(lambda e: alerts.send(str(e)))
    .listen(lambda ev: audit_log.append(ev))
)
```

---

### 4.4  `Group`

Agrupa jobs para controlo em conjunto. Obtido via `Scheduler.group(name)` ou `.group(name)` na cadeia do `Job`.

| Método | Retorna | Descrição |
|---|---|---|
| `group.jobs()` | `List[Job]` | Lista de jobs activos no grupo. |
| `group.count()` | `int` | Número de jobs activos. |
| `group.cancel_all()` | `None` | Cancela todos os jobs do grupo. |
| `group.pause_all()` | `None` | Pausa todos os jobs do grupo. |
| `group.resume_all()` | `None` | Retoma todos os jobs pausados do grupo. |
| `group.run_all_now()` | `None` | Executa todos imediatamente. |

```python
# Registar jobs no grupo
Scheduler.every(5).minutes(sync_users).group("database")
Scheduler.every(10).minutes(sync_orders).group("database")

# Controlar o grupo
g = Scheduler.group("database")
g.pause_all()
g.resume_all()
g.cancel_all()
print(g)  # Group('database', jobs=2)
```

---

### 4.5  Persistência e Execuções Perdidas

O método `.persistent()` salva o estado do job em disco (JSON). Ao reiniciar a aplicação, o Scheduler detecta execuções perdidas e aplica a estratégia configurada.

#### Assinatura

```python
job.persistent(
    strategy = "skip",               # "catchup" | "skip" | "latest"
    path = ".nestifypy/scheduler",   # pasta de persistência
)
```

#### Estratégias (`MissedStrategy`)

| Estratégia | Descrição |
|---|---|
| `MissedStrategy.SKIP` / `"skip"` | Ignora todas as execuções perdidas. Recomendado para jobs idempotentes. |
| `MissedStrategy.CATCHUP` / `"catchup"` | Executa todas as perdidas em paralelo ao reiniciar. |
| `MissedStrategy.LATEST` / `"latest"` | Executa apenas a mais recente entre as perdidas. |

```python
# Job persistente com recuperação da última execução perdida
Scheduler.every(1).hour(generate_report) \
    .named("hourly-report") \
    .persistent(strategy="latest", path="data/scheduler") \
    .log()
```

> **Nota:** O ficheiro JSON é guardado em `{path}/{nome-do-job}.json`. Certifique-se de chamar `.named()` antes de `.persistent()` para que o ficheiro tenha um nome legível.

---

### 4.6  Sistema de Eventos — `JobEvent`

Cada job emite eventos ao longo do seu ciclo de vida. Podem ser ouvidos localmente (por job) ou globalmente (todos os jobs).

#### Tipos de evento (`JobEvent.kind`)

| Valor | Descrição |
|---|---|
| `"start"` | Emitido antes de cada execução. |
| `"complete"` | Emitido após execução bem-sucedida. `duration_ms` disponível. |
| `"error"` | Emitido quando a função lança excepção. `error` disponível. |
| `"timeout"` | Emitido quando a execução excede o timeout. `error` disponível. |
| `"cancel"` | Emitido quando o job é cancelado. |

#### Atributos de `JobEvent`

| Atributo | Tipo | Descrição |
|---|---|---|
| `event.kind` | `str` | Tipo do evento (ver tabela acima). |
| `event.job` | `Job` | Referência ao job que gerou o evento. |
| `event.timestamp` | `datetime` | Momento em que o evento foi emitido. |
| `event.error` | `Optional[Exception]` | Excepção capturada (nos eventos `error` e `timeout`). |
| `event.duration_ms` | `Optional[float]` | Duração em milissegundos (nos eventos `complete` e `timeout`). |

#### Listeners globais

```python
# Listener para todos os eventos
@Scheduler.on_event
def log_all(event: JobEvent):
    print(f"{event.kind:10} {event.job.name}  {event.timestamp:%H:%M:%S}")

# Filtrado por tipo
@Scheduler.on_job_error
def alert_on_error(event: JobEvent):
    send_alert(f"Job {event.job.name} falhou: {event.error}")

@Scheduler.on_job_complete
def track_metrics(event: JobEvent):
    metrics.record(event.job.name, event.duration_ms)
```

---

### 4.7  `CronExpression`

Parser e avaliador de expressões cron de 5 campos. Disponível de forma independente para uso directo.

| Método | Retorna | Descrição |
|---|---|---|
| `CronExpression(expr)` | — | Instancia e valida. Lança `CronParseError` se inválida. |
| `.matches(dt=None)` | `bool` | `True` se `dt` (default: agora) satisfaz a expressão. |
| `.next_after(dt=None)` | `datetime` | Próximo instante após `dt` que satisfaz a expressão. |

#### Sintaxe suportada

| Token | Descrição |
|---|---|
| `*` | Qualquer valor no campo. |
| `*/n` | Múltiplos de `n`. Ex: `*/5` nos minutos = 0, 5, 10, 15… |
| `n-m` | Intervalo inclusivo. Ex: `9-17` nas horas. |
| `n,m,k` | Lista de valores. Ex: `1,15` nos dias do mês. |
| Nomes | `jan`–`dec` para meses, `sun`–`sat` para dias da semana. |
| Combinado | `1-5,10` ou `*/2,5` são expressões válidas. |

#### Exemplos de expressões

```
"0 0 * * *"           # todos os dias à meia-noite
"*/5 * * * *"         # a cada 5 minutos
"0 8 * * 1"           # segunda-feira às 08:00
"0 9-17 * * mon-fri"  # cada hora entre 09-17, dias úteis
"30 6 1,15 * *"       # dia 1 e dia 15 de cada mês às 06:30
"0 0 * * sun"         # domingos à meia-noite
```

```python
from nestifypy.scheduler import CronExpression

cron = CronExpression("0 8 * * mon-fri")
print(cron.matches())       # True se agora é 08:xx num dia útil
print(cron.next_after())    # próxima segunda-feira às 08:00
```

---

### 4.8  Excepções

| Excepção | Herda de | Descrição |
|---|---|---|
| `SchedulerError` | `Exception` | Classe base de todas as excepções do módulo. |
| `JobNotFoundError` | `SchedulerError` | Lançada por `Scheduler.job(name)` quando o nome não existe. |
| `CronParseError` | `SchedulerError` | Expressão cron inválida (campos incorrectos, sintaxe inválida). |
| `JobTimeoutError` | `SchedulerError` | Execução excedeu o timeout configurado. |

---

## 5  Padrões Avançados

### 5.1  Pipeline de notificações

```python
from nestifypy.scheduler import Scheduler, JobEvent

def send_newsletter(): ...

def notify_slack(event: JobEvent):
    if event.kind == "error":
        slack.send(f":x: Newsletter falhou: {event.error}")
    elif event.kind == "complete":
        slack.send(f":white_check_mark: Newsletter enviada em {event.duration_ms:.0f}ms")

job = (
    Scheduler.cron("0 9 * * mon-fri")(send_newsletter)
    .named("daily-newsletter")
    .timeout(120)
    .log()
    .listen(notify_slack)
)
```

### 5.2  Job com retry manual

```python
import time

def flaky_api_call():
    # pode falhar esporadicamente
    ...

def with_retry(fn, attempts=3, backoff=5):
    def wrapper():
        for i in range(attempts):
            try:
                return fn()
            except Exception as e:
                if i == attempts - 1:
                    raise
                time.sleep(backoff * (i + 1))
    return wrapper

Scheduler.every(15).minutes(with_retry(flaky_api_call))
```

### 5.3  Encerramento gracioso

```python
import signal, time
from nestifypy.scheduler import Scheduler

Scheduler.every(5).seconds(heartbeat).named("hb")
Scheduler.every(1).minute(sync_db).named("sync")

def shutdown(signum, frame):
    print("A encerrar...")
    Scheduler.cancel_all()

signal.signal(signal.SIGINT,  shutdown)
signal.signal(signal.SIGTERM, shutdown)

while Scheduler.count() > 0:
    time.sleep(1)
```

### 5.4  Testes unitários

```python
import unittest
from nestifypy.scheduler import Scheduler

class TestScheduler(unittest.TestCase):

    def setUp(self):
        Scheduler._reset()  # limpa estado global entre testes

    def test_run_now(self):
        results = []
        job = Scheduler.every(999).hours(lambda: results.append(1))
        job.run_now()
        import time; time.sleep(0.1)
        self.assertEqual(results, [1])

    def test_cancel(self):
        job = Scheduler.every(1).second(lambda: None).named("t")
        job.cancel()
        self.assertTrue(job.cancelled())
        self.assertEqual(Scheduler.count(), 0)
```

---

## 6  Cheat Sheet

| Operação | Código |
|---|---|
| Execução única após 30 s | `Scheduler.after(30).seconds(fn)` |
| A cada 10 minutos | `Scheduler.every(10).minutes(fn)` |
| A cada hora | `Scheduler.every(1).hour(fn)` |
| Cron — meia-noite diária | `Scheduler.cron("0 0 * * *")(fn)` |
| Cron — dias úteis às 09:00 | `Scheduler.cron("0 9 * * mon-fri")(fn)` |
| Decorator periódico | `@Scheduler.every(5).minutes` |
| Decorator cron | `@Scheduler.cron("0 0 * * *")` |
| Nomear job | `.named("db-sync")` |
| Timeout de 60 s | `.timeout(60)` |
| Limitar a 10 execuções | `.repeat(10)` |
| Delay de 5 s | `.delay(5)` |
| Adicionar a grupo | `.group("database")` |
| Activar logging | `.log()` |
| Execução assíncrona | `.async_()` |
| Persistência (skip) | `.persistent("skip")` |
| Persistência (catchup) | `.persistent("catchup")` |
| Obter job por nome | `Scheduler.job("db-sync")` |
| Cancelar todos | `Scheduler.cancel_all()` |
| Pausar grupo | `Scheduler.group("x").pause_all()` |
| Listener global | `@Scheduler.on_event` |
| Listener de erros | `@Scheduler.on_job_error` |
| Resumo no stdout | `Scheduler.print_summary()` |
| Reset para testes | `Scheduler._reset()` |
