# SLogger – System Logger (`nestifypy.slogger`)

> Um logger profissional, colorido e extensível para qualquer projeto Python —  
> do primeiro `"Hello, World!"` até aplicações em produção.

---

## Instalação / Importação

```python
from nestifypy.slogger import SLogger, LogLevel, get_logger
from nestifypy.slogger import Formatter, SimpleFormatter, JSONFormatter
```

---

## Níveis de Log

| Nível       | Valor | Cor padrão         | Uso                                  |
|-------------|-------|--------------------|--------------------------------------|
| `TRACE`     | 0     | Ciano escuro (dim) | Rastreamento detalhado de fluxo       |
| `DEBUG`     | 1     | Ciano              | Variáveis, estados internos           |
| `INFO`      | 2     | Azul               | Eventos normais da aplicação          |
| `SUCCESS`   | 3     | Verde brilhante    | Operações concluídas com êxito        |
| `WARN`      | 4     | Amarelo brilhante  | Situações incomuns, não-críticas      |
| `ERROR`     | 5     | Vermelho brilhante | Erros recuperáveis                   |
| `FATAL`     | 6     | Fundo vermelho     | Erros irrecuperáveis                 |
| `OFF`       | 99    | —                  | Silencia tudo                        |

---

## Uso rápido

### 1. Logger por instância (recomendado para módulos)

```python
from nestifypy.slogger import get_logger, LogLevel

log = get_logger("my_app", level=LogLevel.DEBUG, file="app.log")

log.trace("Detalhes de fluxo interno")
log.debug("valor de x =", 42)
log.info("Servidor iniciado na porta 8080")
log.success("Conexão estabelecida!")
log.warn("Uso de memória alto")
log.error("Falha ao conectar ao banco")
log.fatal("Sistema irrecuperável")
```

### 2. Logger global (estilo singleton, como no `core` original)

```python
from nestifypy.slogger import SLogger, LogLevel

SLogger.set_prefix("APP")
SLogger.set_level(LogLevel.INFO)
SLogger.set_file("output.log")

SLogger.ginfo("Aplicação iniciada")
SLogger.gwarn("Atenção: modo de debug ativo")
SLogger.gerror("Algo deu errado")
SLogger.gfatal("Shutdown forçado")
```

### 3. Banner ASCII (opcional)

```python
# Na criação da instância
log = get_logger("app", show_banner=True)

# Ou a qualquer momento
SLogger.show_banner()           # Banner grande
SLogger.show_banner(compact=True)  # Banner compacto

log.banner()
log.banner(compact=True)
```

Saída do banner completo:
```
 ███╗   ██╗███████╗███████╗████████╗██╗███████╗██╗   ██╗██████╗ ██╗   ██╗
 ████╗  ██║██╔════╝██╔════╝╚══██╔══╝██║██╔════╝╚██╗ ██╔╝██╔══██╗╚██╗ ██╔╝
 ...
  System Logger  ·  slogger  ·  v2.0.0
```

---

## Formatadores

### `Formatter` (padrão)
```
[14:32:01] [INFO ] [app] Servidor iniciado
```

### `SimpleFormatter`
```
[INFO ] Servidor iniciado
```

### `JSONFormatter`
```json
{"ts": "14:32:01", "level": "INFO", "prefix": "app", "msg": "Servidor iniciado"}
```

```python
from nestifypy.slogger import get_logger, JSONFormatter, LogLevel

log = get_logger("api", formatter=JSONFormatter())
log.info("Request recebido")
# {"ts": "14:32:01", "level": "INFO", "prefix": "api", "msg": "Request recebido"}
```

### Formatador personalizado

```python
from nestifypy.slogger import Formatter, LogLevel

class MyFormatter(Formatter):
    def format(self, level, prefix, message, timestamp):
        return f"[{prefix.upper()}] {message}"

log = get_logger("app", formatter=MyFormatter())
log.info("Olá")  # [APP] Olá
```

---

## Decorators

### `@log.log_calls` / `@SLogger.log` — Logar chamadas de função

```python
log = get_logger("app")

@log.log_calls(level=LogLevel.DEBUG, show_return=True, show_time=True)
def calcular(a, b):
    return a + b

calcular(3, 5)
# → calcular(3, 5)
# ← calcular = 8 (0.01 ms)
```

Global:
```python
@SLogger.log(level=LogLevel.INFO, show_args=False)
def iniciar_servidor():
    ...
```

---

### `@log.catch_errors` / `@SLogger.catch` — Capturar e logar exceções

```python
@log.catch_errors(ValueError, default=0)
def parse_int(s):
    return int(s)

resultado = parse_int("abc")  # loga o erro, retorna 0
```

```python
@SLogger.catch(TypeError, ValueError, reraise=True)
def processar(dados):
    return dados["chave"]  # pode levantar KeyError → não capturado
                           # TypeError → capturado e re-levantado
```

---

### `@log.time_it` / `@SLogger.timeit` — Medir tempo de execução

```python
@log.time_it(label="consulta ao banco")
def buscar_usuarios():
    time.sleep(0.1)

# ⏱  consulta ao banco completed in 100.32 ms
```

---

### `@SLogger.trace_exc` — Rastrear traceback completo

```python
@SLogger.trace_exc
def operacao_arriscada():
    raise RuntimeError("Ops!")

# Loga o traceback completo antes de re-levantar a exceção
```

---

## Métodos utilitários

### `log.exception` — Logar exceção com traceback

```python
try:
    int("abc")
except ValueError:
    log.exception("Erro ao converter valor")
    # Loga mensagem + traceback completo
```

### `log.path_trace` — Rastrear caminho de arquivo

```python
log.path_trace("./config/settings.toml")
# [INFO ] [app] 📄 ./config/settings.toml
# [TRACE] [app]     → /home/user/projeto/config/settings.toml  [file]  ✓ exists

log.path_trace("./nao_existe.txt")
# [INFO ] [app] ❓ ./nao_existe.txt
# [TRACE] [app]     → /home/user/projeto/nao_existe.txt  [?]  ✗ not found
```

### `log.ruler` — Separador horizontal

```python
log.ruler()                          # ────────────────────────────────────────────
log.ruler(label="INICIALIZAÇÃO")     # ──────────── INICIALIZAÇÃO ─────────────────
log.ruler(char="═", width=40)        # ════════════════════════════════════════
```

---

## Context Managers — Nível temporário

```python
log = get_logger("app", level=LogLevel.INFO)

log.debug("não aparece")  # INFO > DEBUG

with log.level_context(LogLevel.TRACE):
    log.trace("aparece aqui!")  # temporariamente em TRACE

log.debug("não aparece novamente")
```

Global:
```python
with SLogger.global_level_context(LogLevel.OFF):
    SLogger.gfatal("silenciado!")  # não aparece
```

---

## Configuração avançada

### Output para arquivo

```python
# Por instância
log = get_logger("app", file="logs/app.log")

# Global
SLogger.set_file("logs/global.log")
```

### Redirecionar para stderr

```python
import sys
SLogger.set_stream(sys.stderr)
```

### Silenciar/reativar globalmente

```python
SLogger.disable()
SLogger.ginfo("silenciado")  # nada
SLogger.enable()
SLogger.ginfo("de volta!")
```

---

## Exemplo completo — projeto real

```python
from nestifypy.slogger import get_logger, SLogger, LogLevel

# Banner de boas-vindas
SLogger.show_banner(compact=True)

# Logger do módulo principal
log = get_logger("server", level=LogLevel.DEBUG, file="server.log")

log.ruler(label="BOOT")
log.info("Inicializando servidor…")
log.path_trace("./config/server.toml")

@log.log_calls(level=LogLevel.DEBUG, show_time=True)
@log.catch_errors(ConnectionError, default=None)
def conectar_banco(host: str, porta: int):
    # simulação
    raise ConnectionError("recusado")

@log.time_it(label="startup")
def iniciar():
    log.info("Carregando módulos…")
    conectar_banco("localhost", 5432)
    log.success("Servidor pronto!")

iniciar()
log.ruler()
```

Saída:
```
  ╔╗╔┌─┐┌─┐┌┬┐┬┌─┐┬ ┬┌─┐┬ ┬
  ║║║├┤ └─┐ │ │├┤ └┬┘├─┘└┬┘
  ╝╚╝└─┘└─┘ ┴ ┴└   ┴ ┴   ┴

────────────────── BOOT ──────────────────
[14:32:01] [INFO ] [server] Inicializando servidor…
[14:32:01] [INFO ] [server] 📁 ./config/server.toml
[14:32:01] [TRACE] [server]     → /home/user/server/config/server.toml  [?]  ✗ not found
[14:32:01] [DEBUG] [server] → conectar_banco('localhost', 5432)
[14:32:01] [ERROR] [server] conectar_banco raised ConnectionError: recusado
[14:32:01] [INFO ] [server] ⏱  startup completed in 0.82 ms
[14:32:01] [ OK  ] [server] Servidor pronto!
──────────────────────────────────────────
```

---

## Resumo da API

| Método / Decorator               | Tipo      | Descrição                                  |
|----------------------------------|-----------|--------------------------------------------|
| `get_logger(prefix, ...)`        | Factory   | Cria instância configurada                 |
| `log.info/debug/warn/error/...`  | Instância | Log por nível                              |
| `log.exception(...)`             | Instância | Loga erro + traceback                      |
| `log.path_trace(path)`           | Instância | Mostra caminho resolvido + existência      |
| `log.ruler(char, width, label)`  | Instância | Separador horizontal                       |
| `log.banner(compact)`            | Instância | Imprime banner ASCII                       |
| `log.level_context(level)`       | Ctx Mgr   | Nível temporário                           |
| `@log.log_calls(...)`            | Decorator | Loga entrada/saída de funções              |
| `@log.catch_errors(...)`         | Decorator | Captura exceções e loga                    |
| `@log.time_it(...)`              | Decorator | Mede tempo de execução                     |
| `SLogger.set_level/prefix/file`  | Global    | Configura o singleton global               |
| `SLogger.ginfo/gdebug/...`       | Global    | Log global por nível                       |
| `@SLogger.log(...)`              | Decorator | Decorator global para chamadas             |
| `@SLogger.trace_exc`             | Decorator | Traceback completo antes de re-levantar    |
| `@SLogger.catch(...)`            | Decorator | Decorator global para exceções             |
| `@SLogger.timeit(...)`           | Decorator | Decorator global para tempo                |
| `SLogger.global_level_context`   | Ctx Mgr   | Nível global temporário                    |
| `SLogger.show_banner(compact)`   | Global    | Banner ASCII global                        |
| `SLogger.ruler(...)`             | Global    | Separador global                           |
