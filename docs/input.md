# nestifypy.input

Um substituto moderno, type-safe e fluente para o `input()` nativo do Python.

Zero dependências externas. Requer Python 3.10+.

---

## Índice

- [Instalação](#instalação)
- [Visão geral](#visão-geral)
- [ask() — ponto de entrada](#ask--ponto-de-entrada)
  - [Conversões de tipo](#conversões-de-tipo)
  - [Métodos do builder](#métodos-do-builder)
  - [Propriedades especiais](#propriedades-especiais)
- [InputResult](#inputresult)
- [Validators](#validators)
  - [Primitivos](#primitivos)
  - [Numéricos](#numéricos)
  - [Formato e padrão](#formato-e-padrão)
  - [Sistema de ficheiros](#sistema-de-ficheiros)
  - [Segurança](#segurança)
  - [Combinadores](#combinadores)
- [interactive — prompts com cursor](#interactive--prompts-com-cursor)
  - [select()](#select)
  - [multiselect()](#multiselect)
  - [confirm()](#confirm)
  - [table_input()](#table_input)
  - [progress_input()](#progress_input)
- [Form — formulários declarativos](#form--formulários-declarativos)
- [InputHistory — histórico persistente](#inputhistory--histórico-persistente)
- [sanitize — sanitização de strings](#sanitize--sanitização-de-strings)
- [Exceptions](#exceptions)
- [Padrões de tratamento de erros](#padrões-de-tratamento-de-erros)

---

## Instalação

O módulo faz parte do core do nestifypy. Nenhuma dependência adicional é necessária.

```python
from nestifypy.input import ask
```

Para os prompts interativos com cursor (arrow keys):

```python
from nestifypy.input.interactive import select, multiselect, confirm
```

---

## Visão geral

O `input()` nativo do Python devolve sempre uma `str` crua, sem validação, sem conversão de tipo, sem retry e sem qualquer proteção contra entradas maliciosas. O `nestifypy.input` resolve todos esses problemas com uma API fluente e composável.

```python
# Antes — Python puro
while True:
    try:
        port = int(input("Port: "))
        if not 1 <= port <= 65535:
            raise ValueError
        break
    except ValueError:
        print("Invalid port.")

# Depois — nestifypy.input
port = ask("Port?").validate(Validator.range(1, 65535)).retry(3).int
```

---

## ask() — ponto de entrada

`ask(prompt: str) -> InputBuilder`

A única função que precisa de importar para a maior parte dos casos. Devolve um `InputBuilder` que pode ser configurado com métodos encadeados e finalizado com uma propriedade de tipo ou método de conversão.

```python
from nestifypy.input import ask

name   = ask("Your name?").str
age    = ask("Your age?").int
height = ask("Height in m?").float
active = ask("Active?").bool
```

### Conversões de tipo

Aceda a uma propriedade ou chame um método no builder (ou num `InputResult`) para converter e obter o valor final.

| Acesso | Tipo devolvido | Notas |
|--------|---------------|-------|
| `.str` | `str` | String stripped. Nunca lança excepção de conversão. |
| `.int` | `int` | Lança `InputConversionError` se não for inteiro. |
| `.float` | `float` | Lança `InputConversionError` se não for número. |
| `.number` | `int \| float` | Devolve `int` se o valor for inteiro (ex: `5.0 → 5`), senão `float`. |
| `.bool` | `bool` | Aceita: `true/false`, `yes/no`, `y/n`, `1/0`, `on/off`, `sim/não`. |
| `.list(type, sep)` | `list[T]` | Divide por `sep` (default `,`) e converte cada item. |
| `.set(type, sep)` | `set[T]` | Igual ao `.list()` mas devolve um `set` (sem duplicados). |
| `.tuple(*types, sep)` | `tuple` | Divide e aplica cada tipo na posição correspondente. |
| `.path` | `Path` | `pathlib.Path` com expansão de `~` e variáveis de ambiente. |
| `.existing_path` | `Path` | Como `.path`, mas verifica que o caminho existe. |
| `.file_path` | `Path` | Como `.existing_path`, mas verifica que é um ficheiro. |
| `.dir_path` | `Path` | Como `.existing_path`, mas verifica que é um directório. |
| `.email` | `str` | Valida formato de e-mail e devolve em minúsculas. |
| `.url` | `str` | Valida URL HTTP/HTTPS. |
| `.json` | `Any` | Faz parse de JSON. Lança `InputConversionError` se inválido. |
| `.cast(fn)` | `T` | Aplica qualquer callable à string crua. |
| `.choice(options)` | `str` | Valida que o valor pertence a `options` (case-insensitive por default). |
| `.prompt()` | `InputResult` | Executa o prompt e devolve o `InputResult` completo. |

**Exemplos:**

```python
# Listas tipadas
numbers = ask("Numbers?").list(int)          # "1, 2, 3"  → [1, 2, 3]
tags    = ask("Tags?").list()                # "a, b, c"  → ["a", "b", "c"]
hosts   = ask("Hosts?").list(str, " ")       # "a b c"    → ["a", "b", "c"]

# Tuple com tipos diferentes por posição
x, y = ask("x,y?").tuple(float, float)      # "3.5,7.2"  → (3.5, 7.2)

# Caminhos
config = ask("Config file?").file_path       # verifica que existe e é ficheiro
outdir = ask("Output dir?").dir_path         # verifica que existe e é directório

# Cast personalizado
from datetime import date
d = ask("Date (YYYY-MM-DD)?").cast(date.fromisoformat)

# Choice
env = ask("Environment?").choice(["dev", "staging", "prod"])
```

### Métodos do builder

Todos os métodos devolvem `self` para permitir encadeamento.

#### `.default(value)`

Define um valor por defeito mostrado entre parênteses no prompt. Usado quando o utilizador submete uma linha vazia.

```python
host = ask("Host?").default("localhost").str
# Prompt: "Host? (localhost) "
# Enter sem input → devolve "localhost"
```

#### `.required(message?)`

Rejeita input vazio. A mensagem de erro é customizável.

```python
token = ask("API Token?").required("Token is required.").retry(3).str
```

#### `.validate(*validators)`

Associa um ou mais validators. Um validator é um callable `(str) -> str | None`: devolve `None` em caso de sucesso ou uma mensagem de erro em caso de falha. Todos os validators são executados e os erros são apresentados ao utilizador.

```python
from nestifypy.input.validators import Validator

port = ask("Port?").validate(Validator.range(1, 65535)).int

# Vários validators em cadeia
ask("Password?").validate(
    Validator.min_length(8),
    Validator.matches(r"[A-Z]", "Must contain an uppercase letter."),
).str
```

#### `.retry(times=3)`

Permite ao utilizador `times` tentativas antes de lançar `InputValidationError`. Depois de cada tentativa falhada é mostrado quantas tentativas restam.

```python
age = ask("Age?").validate(Validator.range(0, 150)).retry(5).int
```

#### `.timeout(seconds)`

Lança `InputTimeoutError` se o utilizador não responder dentro do tempo. Suportado apenas em Unix. No Windows emite um `RuntimeWarning` e comporta-se como um prompt normal.

```python
answer = ask("Continue? [y/n]").timeout(30).bool
```

#### `.hint(text)`

Mostra uma linha de ajuda a baixo do prompt, em texto esbatido.

```python
ask("Password?").secret.hint("At least 8 characters, one uppercase.").str
```

#### `.choices(options)`

Restringe o input a uma lista de opções (case-insensitive). Equivalente a `.validate(Validator.one_of(options))`, mas também mostra as opções no prompt.

```python
env = ask("Environment?").choices(["dev", "staging", "prod"]).str
# Prompt: "Environment? [dev, staging, prod] "
```

#### `.multiline()`

Colecta múltiplas linhas até o utilizador submeter uma linha em branco. As linhas são unidas com `\n`.

```python
body = ask("Message (blank line to end)?").multiline().str
```

#### `.confirm()`

Pede o valor duas vezes. Se os dois inputs não coincidirem, mostra erro e recomeça.

```python
pwd = ask("New password?").secret.confirm().required().str
```

#### `.no_strip()`

Por defeito o input é stripped de espaços iniciais e finais. Este método preserva-os.

```python
raw = ask("Indented code?").no_strip().str
```

#### `.prompt()`

Executa o prompt e devolve o `InputResult` bruto para inspeção posterior.

```python
result = ask("Name?").required().prompt()
print(result.str)   # string stripped
print(result.raw)   # string original sem strip
print(result.int)   # conversão para int
```

### Propriedades especiais

#### `.secret`

Propriedade (não método). Oculta o input usando `getpass.getpass`. Deve ser acedida antes de finalizar a chain.

```python
pwd = ask("Password?").secret.confirm().validate(Validator.min_length(8)).str
```

---

## InputResult

`InputResult` é o objecto devolvido por `.prompt()`. Contém o valor capturado e expõe todas as conversões como propriedades ou métodos.

Todos os accessors de conversão (`.int`, `.float`, `.bool`, etc.) lançam `InputConversionError` (subclasse de `InputValidationError`) em caso de falha, pelo que todos os erros de input podem ser capturados com um único `except InputValidationError`.

```python
from nestifypy.input.types import InputResult

result = InputResult("42", prompt="Age?")

result.raw          # "42"       — string original sem qualquer modificação
result.str          # "42"       — stripped
result.int          # 42
result.float        # 42.0
result.number       # 42         — int porque não tem parte fraccionária
result.bool         # InputConversionError (42 não é booleano válido)
result.path         # Path("42")
result.email        # InputValidationError (não é e-mail)
result.list(int)    # InputConversionError (não é lista)
result.cast(str.upper)  # "42"
```

**Operadores:**

```python
result == "42"      # True — comparação com str
bool(result)        # True — False apenas se a string for vazia
repr(result)        # "InputResult('42')"
```

---

## Validators

`Validator` é um namespace de validators prontos a usar e combinadores. Todos os validators seguem a assinatura `(str) -> str | None`: devolvem `None` em caso de sucesso ou uma mensagem de erro.

```python
from nestifypy.input.validators import Validator
```

### Primitivos

| Validator | Descrição |
|-----------|-----------|
| `Validator.not_empty` | Rejeita strings vazias ou só com espaços. |
| `Validator.min_length(n)` | Rejeita strings com menos de `n` caracteres (após strip). |
| `Validator.max_length(n)` | Rejeita strings com mais de `n` caracteres. |
| `Validator.length(min, max)` | Combina `min_length` e `max_length`. |

### Numéricos

| Validator | Descrição |
|-----------|-----------|
| `Validator.is_int` | Rejeita strings que não sejam inteiros. |
| `Validator.is_float` | Rejeita strings que não sejam números. |
| `Validator.range(min, max)` | Rejeita números fora do intervalo `[min, max]`. |
| `Validator.positive` | Rejeita valores `<= 0`. |

### Formato e padrão

| Validator | Descrição |
|-----------|-----------|
| `Validator.matches(pattern, msg?)` | Rejeita strings que não coincidam com o regex. |
| `Validator.email` | Valida formato de e-mail (RFC 5322). |
| `Validator.url` | Valida URLs HTTP/HTTPS. |
| `Validator.ip_address` | Valida endereços IPv4 e IPv6. |
| `Validator.one_of(options, case_sensitive?)` | Rejeita valores fora da lista. |

### Sistema de ficheiros

| Validator | Descrição |
|-----------|-----------|
| `Validator.path_exists` | Rejeita caminhos que não existam no disco. |
| `Validator.is_file` | Rejeita caminhos que não sejam ficheiros regulares. |
| `Validator.is_dir` | Rejeita caminhos que não sejam directórios. |
| `Validator.extension(*exts)` | Rejeita ficheiros com extensão fora da lista (ex: `".yml"`, `".yaml"`). |

### Segurança

| Validator | Descrição |
|-----------|-----------|
| `Validator.no_script_injection` | Rejeita `<script>`, `javascript:`, `onXxx=`. |
| `Validator.no_sql_injection` | Rejeita `SELECT/DROP/--` e payloads comuns. |
| `Validator.no_path_traversal` | Rejeita sequências `../../`. |
| `Validator.safe` | Combina os três validators de segurança anteriores. |

> **Nota:** os validators de segurança são uma defesa em profundidade. Para SQL, utilize sempre queries parametrizadas. Para HTML, utilize uma biblioteca de sanitização dedicada.

### Combinadores

#### `Validator.all(*validators)`

Passa apenas se **todos** os validators passarem. Devolve o primeiro erro encontrado.

```python
ask("Config file?").validate(
    Validator.all(
        Validator.path_exists,
        Validator.extension(".yml", ".yaml"),
    )
).file_path
```

#### `Validator.any(*validators)`

Passa se **pelo menos um** dos validators passar. Devolve o último erro se todos falharem.

```python
# Aceita inteiro ou float
ask("Amount?").validate(
    Validator.any(Validator.is_int, Validator.is_float)
).number
```

#### `Validator.custom(fn, message)`

Transforma qualquer função booleana num validator.

```python
ask("Username?").validate(
    Validator.custom(str.isalnum, "Only alphanumeric characters.")
).str
```

**Composição avançada:**

```python
strong_password = Validator.all(
    Validator.min_length(8),
    Validator.matches(r"[A-Z]", "Must contain an uppercase letter."),
    Validator.matches(r"[0-9]", "Must contain a digit."),
    Validator.matches(r"[^a-zA-Z0-9]", "Must contain a special character."),
)

ask("Password?").secret.validate(strong_password).retry(3).str
```

---

## interactive — prompts com cursor

Prompts com navegação por teclado para terminais ANSI (macOS, Linux, Windows 10+). Em ambientes não-TTY (CI, pipes, redirecionamento) fazem fallback automático para prompts de texto simples.

```python
from nestifypy.input.interactive import select, multiselect, confirm, table_input, progress_input
```

### select()

```python
select(
    prompt: str,
    options: Iterable[str],
    *,
    default: int = 0,
    page_size: int = 8,
    hint: str = "↑↓ move  Enter select  Ctrl+C cancel",
) -> str
```

Menu de selecção única com teclas `↑↓`. Suporta paginação automática para listas longas. Devolve a string da opção seleccionada.

**Controlos:**

| Tecla | Acção |
|-------|-------|
| `↑` / `↓` | Navegar |
| `Enter` | Confirmar |
| `Ctrl+U` | Página anterior |
| `Ctrl+D` | Página seguinte |
| `Ctrl+C` / `Esc` | Cancelar (lança `InputCancelledError`) |

```python
env = select("Environment?", ["dev", "staging", "prod"])

# Com default e paginação personalizada
db = select(
    "Select database engine?",
    ["postgresql", "mysql", "sqlite", "mongodb", "redis"],
    default=0,
    page_size=5,
)
```

### multiselect()

```python
multiselect(
    prompt: str,
    options: Iterable[str],
    *,
    defaults: Iterable[int] = (),
    min_selections: int = 0,
    max_selections: int | None = None,
    page_size: int = 8,
    hint: str = "↑↓ move  Space toggle  A all/none  Enter confirm",
) -> list[str]
```

Menu de selecção múltipla com checkboxes. Devolve a lista de strings seleccionadas, na ordem original.

**Controlos:**

| Tecla | Acção |
|-------|-------|
| `↑` / `↓` | Navegar |
| `Space` | Seleccionar / deseleccionar item |
| `A` | Seleccionar todos / limpar todos |
| `Enter` | Confirmar (respeita `min_selections`) |
| `Ctrl+C` / `Esc` | Cancelar |

```python
features = multiselect(
    "Enable features?",
    ["auth", "websocket", "scheduler", "cache", "metrics"],
    defaults=[0, 2],          # auth e scheduler pré-seleccionados
    min_selections=1,
    max_selections=3,
)
```

### confirm()

```python
confirm(
    prompt: str,
    *,
    default: bool | None = None,
    style: str = "yn",
) -> bool
```

Diálogo de confirmação sim/não estilizado. O default (quando definido) é mostrado em maiúscula no prompt (`Y/n` ou `y/N`). Aceita `y/yes/sim/s/true/t/1` e `n/no/não/nao/false/f/0`.

```python
if confirm("Overwrite existing file?", default=False):
    overwrite()

# Estilo true/false
if confirm("Enable debug mode?", default=False, style="tf"):
    ...
```

### table_input()

```python
table_input(
    prompt: str,
    columns: list[dict],
    *,
    min_rows: int = 1,
    max_rows: int | None = None,
) -> list[dict[str, Any]]
```

Colecta uma lista de registos tipados, campo a campo. Cada coluna é definida por um dicionário com as seguintes chaves:

| Chave | Tipo | Descrição |
|-------|------|-----------|
| `name` | `str` | Label mostrado ao utilizador |
| `key` | `str` | Chave no dicionário devolvido |
| `type` | `type` | Tipo Python para conversão: `str`, `int`, `float`, `bool` (default: `str`) |
| `required` | `bool` | Se `True`, rejeita input vazio (default: `False`) |
| `default` | `Any` | Valor por defeito para input vazio |
| `validator` | `ValidatorFn` | Validator opcional para este campo |

Após cada linha o utilizador é questionado se quer adicionar outra. Para quando recusa ou `max_rows` é atingido.

```python
connections = table_input(
    "Configure database connections",
    columns=[
        {"name": "Host",    "key": "host", "type": str, "required": True},
        {"name": "Port",    "key": "port", "type": int, "default": 5432,
         "validator": Validator.range(1, 65535)},
        {"name": "DB name", "key": "db",   "type": str, "required": True},
    ],
    min_rows=1,
    max_rows=5,
)
# → [{"host": "localhost", "port": 5432, "db": "myapp"}, ...]
```

### progress_input()

```python
progress_input(
    prompt: str,
    timeout: float,
    *,
    default: str = "",
    message: str = "Auto-continuing",
) -> str
```

Mostra uma barra de contagem regressiva junto ao prompt. Se o utilizador não responder dentro de `timeout` segundos, devolve `default`. Apenas funcional em Unix; no Windows comporta-se como `ask(prompt).default(default).str`.

```python
answer = progress_input(
    "Use default config?",
    timeout=10,
    default="yes",
    message="Proceeding with defaults",
)
```

---

## Form — formulários declarativos

Define um formulário como uma classe com campos declarados, e colecta todos os valores numa única chamada.

```python
from nestifypy.input.form import Form, field
from nestifypy.input.validators import Validator
```

### Definição de campos com `field()`

```python
field(
    prompt: str,
    *,
    type: type = str,
    default: Any = ...,
    required: bool = False,
    secret: bool = False,
    validator: ValidatorFn | None = None,
    hint: str = "",
    multiline: bool = False,
) -> FieldDef
```

| Parâmetro | Descrição |
|-----------|-----------|
| `prompt` | Texto mostrado ao utilizador |
| `type` | `str`, `int`, `float`, `bool`, ou `list` |
| `default` | Valor usado quando o input é vazio |
| `required` | Se `True`, rejeita input vazio |
| `secret` | Se `True`, oculta o input (getpass) |
| `validator` | `ValidatorFn` para este campo |
| `hint` | Linha de ajuda abaixo do prompt |
| `multiline` | Colecta múltiplas linhas |

### Classe Form

Herda de `Form` e declara campos como atributos de classe. Chama `collect()` para iniciar a colecta interactiva.

```python
class ServerConfig(Form):
    host    = field("Host",          type=str,   default="localhost")
    port    = field("Port",          type=int,   default=8080,
                    validator=Validator.range(1, 65535))
    debug   = field("Debug mode?",   type=bool,  default=False)
    db_url  = field("Database URL",  type=str,   required=True,
                    hint="postgresql://user:pass@host/db")
    notes   = field("Notes",         multiline=True)
    secret  = field("API secret",    secret=True, confirm=True)

config = ServerConfig.collect(title="Server Setup")

# Acesso por atributo
print(config.host, config.port)

# Serialização
data = config.to_dict()
# → {"host": "...", "port": ..., "debug": ..., "db_url": "...", ...}
```

#### `Form.collect(title?, show_summary?)`

| Parâmetro | Tipo | Default | Descrição |
|-----------|------|---------|-----------|
| `title` | `str` | `""` | Cabeçalho impresso antes do primeiro campo |
| `show_summary` | `bool` | `True` | Imprime tabela de resumo após todos os campos |

Os valores dos campos `secret` aparecem mascarados (`••••••••`) no resumo.

**Herança de formulários:**

```python
class BaseConfig(Form):
    host = field("Host", default="localhost")
    port = field("Port", type=int, default=8080)

class AppConfig(BaseConfig):
    app_name = field("App name", required=True)
    debug    = field("Debug?",   type=bool, default=False)

# AppConfig.collect() recolhe host, port, app_name, debug
```

---

## InputHistory — histórico persistente

Integração com readline para recordar inputs anteriores com as teclas `↑↓`, tal como numa shell.

```python
from nestifypy.input.history import InputHistory
```

```python
InputHistory(
    path: str | Path = "~/.nestifypy_input_history",
    max_entries: int = 500,
)
```

### Uso básico

```python
history = InputHistory("~/.myapp/cmd_history")
history.install()    # carrega do disco, activa readline

cmd = ask("Command?").str   # ↑↓ recuperam comandos anteriores

history.save()       # grava no disco
```

### Context manager `.session()`

A forma recomendada: instala no `__enter__` e grava no `__exit__` automaticamente.

```python
with InputHistory("~/.myapp/history").session():
    host = ask("Host?").str
    port = ask("Port?").int
    # histórico gravado ao sair do bloco
```

### Outros métodos

```python
history.clear()          # apaga histórico da memória e do ficheiro
entries = history.entries  # list[str] com todas as entradas actuais
```

> Quando readline não está disponível (ex: Windows sem `pyreadline3`), os métodos não fazem nada e não lançam excepções.

---

## sanitize — sanitização de strings

Funções puras para limpar, normalizar e proteger strings antes de as usar em queries, nomes de ficheiro ou interfaces.

```python
from nestifypy.input.sanitize import (
    sanitize,           # all-in-one
    strip_tags,
    strip_script,
    strip_sql,
    normalize_whitespace,
    mask,
    redact,
    slugify,
    to_safe_filename,
    truncate,
)
```

### `sanitize(value, *, html, sql, whitespace, max_length)` — all-in-one

Aplica um conjunto de passos de sanitização em sequência. Recomendado para input geral que vai ser armazenado ou apresentado.

```python
sanitize(value: str, *, html=True, sql=True, whitespace=True, max_length=None) -> str
```

```python
clean = sanitize(ask("Bio?").str)
# Remove HTML, SQL comments, normaliza espaços

clean = sanitize(ask("Note?").str, max_length=500)
```

### HTML e scripts

```python
strip_tags('<b>Hello</b> world')
# → "Hello world"

strip_script('<script>alert(1)</script> text <div onclick="evil()">safe</div>')
# → " text <div>safe</div>"
```

### SQL

```python
strip_sql("'; DROP TABLE users; --")
# → "' DROP TABLE users"
# Remove: comentários --, blocos /* */, ponto e vírgula
```

> **Aviso:** esta função é uma defesa adicional, não um substituto para queries parametrizadas.

### Whitespace

```python
normalize_whitespace("  hello   world\n\t")
# → "hello world"
```

### Mascaramento

```python
mask(value, *, visible=4, char="•", position="end") -> str
```

| `position` | Exemplo (`visible=4`) |
|-----------|----------------------|
| `"end"` (default) | `"mysecrettoken"` → `"•••••••••oken"` |
| `"start"` | `"mysecrettoken"` → `"myse•••••••••"` |
| `"both"` | `"mysecrettoken"` → `"my•••••••••en"` |

```python
mask("mysecrettoken")                          # "•••••••••oken"
mask("admin@example.com", visible=6, position="both")  # "admin••••••.com"
mask("abc")                                    # "•••"  (mais curto que visible)
```

### Redacção automática

```python
redact(value, *, patterns=None, replacement="[REDACTED]") -> str
```

Substitui padrões sensíveis por `[REDACTED]`. Os padrões por defeito cobrem e-mails, números de cartão de crédito e tokens longos (≥32 caracteres).

```python
redact("Contact admin@example.com for your token abc123...xyz789")
# → "Contact [REDACTED] for your token [REDACTED]"

# Padrões personalizados
redact(log_line, patterns=[r"\b\d{3}-\d{2}-\d{4}\b"])  # SSN
```

### Slug

```python
slugify(value, *, separator="-", lower=True, max_length=None) -> str
```

Converte uma string em slug URL-safe. Normaliza unicode (acentos → ASCII), substitui não-alfanuméricos pelo separador e colapsa separadores repetidos.

```python
slugify("Hello, World! 2024")        # "hello-world-2024"
slugify("Über Café")                  # "uber-cafe"
slugify("My Post Title", separator="_")  # "my_post_title"
slugify("Very long title...", max_length=20)
```

### Nome de ficheiro seguro

```python
to_safe_filename(value, *, replacement="_", max_length=255) -> str
```

Remove ou substitui caracteres inválidos para nomes de ficheiro em Windows, macOS e Linux: separadores de caminho (`/ \`), caracteres reservados do Windows (`< > : " | ? *`), caracteres de controlo e sequências de path traversal (`..`).

```python
to_safe_filename("../../../etc/passwd")         # "etcpasswd" (ou similar)
to_safe_filename("My Report: Q4 2024.pdf")      # "My_Report__Q4_2024.pdf"
to_safe_filename("COM1.txt")                    # "COM1.txt" (nome preservado)
```

### Truncagem

```python
truncate(value, max_length, *, suffix="…", word_boundary=False) -> str
```

```python
truncate("Hello, world!", 8)                     # "Hello, …"
truncate("Hello, world!", 8, suffix="...")       # "Hello..."
truncate("Hello world!", 8, word_boundary=True)  # "Hello …"
truncate("Hi", 10)                               # "Hi"  (sem truncagem)
```

---

## Exceptions

Hierarquia de excepções do módulo:

```
InputError
├── InputValidationError     — um validator rejeitou o input
│   └── InputConversionError — conversão de tipo falhou
├── InputCancelledError      — Ctrl+C / Ctrl+D / EOF
└── InputTimeoutError        — timeout() expirou
```

```python
from nestifypy.input.exceptions import (
    InputError,
    InputValidationError,
    InputConversionError,
    InputCancelledError,
    InputTimeoutError,
)
```

### InputValidationError

Lançada quando um validator rejeita o input ou quando `.required()` é violado após esgotar os retries. Atributos:

| Atributo | Tipo | Descrição |
|----------|------|-----------|
| `message` | `str` | Mensagem de erro (também em `str(exc)`) |
| `raw_value` | `str` | A string crua que falhou |
| `field` | `str` | O texto do prompt associado |

### InputConversionError

Subclasse de `InputValidationError`. Lançada por `.int`, `.float`, `.bool`, `.list()`, `.cast()` etc. Atributos adicionais:

| Atributo | Tipo | Descrição |
|----------|------|-----------|
| `target_type` | `type` | O tipo Python para o qual a conversão foi tentada |

### InputCancelledError

Lançada quando o utilizador cancela o prompt (Ctrl+C, Ctrl+D, EOF). Atributos:

| Atributo | Tipo | Descrição |
|----------|------|-----------|
| `prompt` | `str` | O texto do prompt onde o cancelamento ocorreu |

### InputTimeoutError

Lançada quando `.timeout(n)` expira. Apenas em Unix. Atributos:

| Atributo | Tipo | Descrição |
|----------|------|-----------|
| `seconds` | `float` | Quantos segundos o prompt aguardou |
| `prompt` | `str` | O texto do prompt |

---

## Padrões de tratamento de erros

### Padrão base

```python
from nestifypy.input import ask
from nestifypy.input.exceptions import InputValidationError, InputCancelledError

try:
    port = ask("Port?").validate(Validator.range(1, 65535)).retry(3).int
except InputCancelledError:
    print("Cancelled.")
    sys.exit(0)
except InputValidationError as e:
    print(f"Invalid input: {e}")
    sys.exit(1)
```

### Com timeout

```python
from nestifypy.input.exceptions import InputTimeoutError

try:
    answer = ask("Proceed?").timeout(30).bool
except InputTimeoutError as e:
    print(f"Timed out after {e.seconds:.0f}s. Defaulting to False.")
    answer = False
except InputCancelledError:
    sys.exit(0)
```

### Distinção entre conversão e validação

```python
from nestifypy.input.exceptions import InputConversionError

try:
    value = ask("Number?").int
except InputConversionError as e:
    # Conversão de tipo falhou
    print(f"'{e.raw_value}' is not a valid {e.target_type.__name__}.")
except InputValidationError as e:
    # Outro erro de validação
    print(f"Validation failed: {e}")
```

### Formulário com tratamento de cancelamento

```python
try:
    config = ServerConfig.collect(title="Setup")
except InputCancelledError:
    print("\nSetup cancelled.")
    sys.exit(0)
```

### Sanitização após colecta

```python
from nestifypy.input.sanitize import sanitize, mask

raw_bio = ask("Bio?").required().str
safe_bio = sanitize(raw_bio, max_length=500)

raw_pwd = ask("Password?").secret.str
print(f"Password set: {mask(raw_pwd)}")
```
