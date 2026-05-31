# nestifypy.pyunix — Documentação Completa

> **pyunix** é a camada de desenvolvimento de jogos da biblioteca `nestifypy`. Ela envolve o `pygame` com uma API de alto nível inspirada em Unity e Godot, permitindo criar jogos 2D com muito menos código boilerplate.

---

## Índice

1. [Instalação e Requisitos](#1-instalação-e-requisitos)
2. [Estrutura Geral](#2-estrutura-geral)
3. [Game — O Loop Principal](#3-game--o-loop-principal)
4. [Entity e Sprite — Objetos do Jogo](#4-entity-e-sprite--objetos-do-jogo)
5. [Transform — Posição, Rotação e Escala](#5-transform--posição-rotação-e-escala)
6. [Input — Teclado, Mouse e Gamepad](#6-input--teclado-mouse-e-gamepad)
7. [Physics — Física 2D](#7-physics--física-2d)
8. [Camera — Câmera 2D](#8-camera--câmera-2d)
9. [Assets — Carregamento de Recursos](#9-assets--carregamento-de-recursos)
10. [Animation — Animação por Spritesheet](#10-animation--animação-por-spritesheet)
11. [Audio — Música e Efeitos Sonoros](#11-audio--música-e-efeitos-sonoros)
12. [Particles — Sistema de Partículas](#12-particles--sistema-de-partículas)
13. [Tween — Animações de Propriedades](#13-tween--animações-de-propriedades)
14. [Scene — Gerenciador de Cenas](#14-scene--gerenciador-de-cenas)
15. [Timer — Timers e Callbacks](#15-timer--timers-e-callbacks)
16. [Events — Sistema de Eventos Pub/Sub](#16-events--sistema-de-eventos-pubsub)
17. [TileMap — Mapas em Tiles](#17-tilemap--mapas-em-tiles)
18. [Text — Renderização de Texto](#18-text--renderização-de-texto)
19. [Math — Vetores e Cores](#19-math--vetores-e-cores)
20. [Window — Gerenciamento da Janela](#20-window--gerenciamento-da-janela)
21. [Save — Sistema de Salvamento](#21-save--sistema-de-salvamento)
22. [Exemplo Completo — Jogo Simples](#22-exemplo-completo--jogo-simples)

---

## 1. Instalação e Requisitos

```bash
pip install nestifypy pygame
```

O `pygame` é a única dependência obrigatória. Algumas funcionalidades opcionais (como variação de pitch no áudio) também requerem `numpy`.

---

## 2. Estrutura Geral

A pyunix é composta por módulos independentes que colaboram entre si. O fluxo típico de um jogo é:

```
@Game(...)          ← configura a janela e o loop
  @Game.start       ← carrega recursos, cria entidades
  @Game.update(dt)  ← lógica por frame
  @Game.draw(screen)← renderização por frame
```

Todos os singletons globais (`Camera`, `Input`, `Audio`, `Assets`, `Timer`, `Event`, `PhysicsWorld`, `Scene`, `Save`) são importados diretamente dos módulos correspondentes e já estão prontos para uso — sem necessidade de instanciar nada manualmente.

---

## 3. Game — O Loop Principal

**Módulo:** `nestifypy.pyunix.app`

O decorator `@Game(...)` transforma uma classe Python comum em um jogo completo com janela, loop de eventos, física e renderização.

### Uso básico

```python
from nestifypy.pyunix.app import Game
from nestifypy.pyunix.window import Window

@Game(title="Meu Jogo", size=(800, 600), fps=60)
class MeuJogo:

    @Game.start
    def on_start(self):
        # chamado uma vez antes do loop começar
        pass

    @Game.update
    def on_update(self, dt):
        # chamado todo frame; dt = tempo em segundos desde o frame anterior
        pass

    @Game.draw
    def on_draw(self, screen):
        # chamado todo frame para renderização
        screen.fill((30, 30, 40))  # limpa a tela

MeuJogo().run()
```

### Parâmetros do `@Game(...)`

| Parâmetro | Tipo | Padrão | Descrição |
|---|---|---|---|
| `title` | `str` | `"Pyunix Game"` | Título da janela |
| `size` | `tuple` | `(800, 600)` | Largura e altura em pixels |
| `fps` | `int` | `60` | Target de frames por segundo |
| `fixed_timestep` | `float` | `1/60` | Intervalo do physics update (segundos) |
| `icon` | `str` | `None` | Caminho para o ícone da janela |
| `resizable` | `bool` | `False` | Permite redimensionar a janela |
| `fullscreen` | `bool` | `False` | Inicia em tela cheia |
| `vsync` | `bool` | `True` | Ativa sincronização vertical |

### Hooks de Ciclo de Vida

```python
@Game.start          # uma vez, antes do loop
@Game.stop           # uma vez, ao encerrar
@Game.update         # todo frame — recebe `dt` (float)
@Game.fixed_update   # taxa fixa (física) — sem parâmetros
@Game.draw           # todo frame — recebe `screen` (Surface)
@Game.on_pause       # quando o jogo é pausado (ESC)
@Game.on_resume      # quando o jogo é despausado
```

### Camadas de Renderização (Layers)

Organize o que é desenhado primeiro com `@Game.layer(nome, order=N)`. Layers com `order` menor são desenhadas primeiro (aparecem "atrás").

```python
@Game.layer("fundo", order=0)
def draw_fundo(self, screen):
    screen.blit(self.bg, (0, 0))

@Game.layer("entidades", order=1)
def draw_entidades(self, screen):
    self.enemies.draw(screen, Camera.offset)

@Game.layer("ui", order=2)
def draw_ui(self, screen):
    self.hud.draw(screen)
```

### Labels de Texto Automáticos

Exibe um valor dinâmico como texto sem precisar renderizar manualmente:

```python
@Game.text(x=10, y=10, size=20, color="yellow")
def label_pontuacao(self):
    return f"Pontos: {self.pontos}"
```

### Controle do Jogo em Tempo Real

```python
self.quit()           # encerra o loop
self.pause()          # pausa a simulação
self.resume()         # retoma a simulação
self.time_scale = 0.5 # câmera lenta (0.0 = congelado, 1.0 = normal)
```

### Debug Overlay

Pressione **F3** em tempo de execução para ativar/desativar um overlay que mostra FPS, quantidade de corpos físicos, posição da câmera e escala de tempo.

Pressione **ESC** para pausar/despausar o jogo.

---

## 4. Entity e Sprite — Objetos do Jogo

**Módulo:** `nestifypy.pyunix.sprite`

`Entity` é a classe base de todos os objetos do jogo. Herdar dela e usar os decorators `@Sprite.*` é o jeito pyunix de criar personagens, inimigos, projéteis, etc.

### Criando uma Entidade

```python
from nestifypy.pyunix.sprite import Entity, Sprite, SpriteGroup
from nestifypy.pyunix.input import Input
from nestifypy.pyunix.camera import Camera

class Jogador(Entity):

    @Sprite.ready
    def setup(self):
        # chamado uma vez ao construir a entidade
        self.image = Assets.image("player.png")
        self.velocidade = 150

    @Sprite.update
    def mover(self, dt):
        h = Input.get_axis("horizontal")
        v = Input.get_axis("vertical")
        self.x += h * self.velocidade * dt
        self.y += v * self.velocidade * dt

    @Sprite.draw
    def renderizar(self, surface):
        self.draw_self(surface, Camera.offset)

    @Sprite.on_collision_enter
    def ao_colidir(self, info):
        print(f"Colidiu com {info.other}")
```

### Hooks de Ciclo de Vida do `@Sprite`

| Decorator | Quando é chamado |
|---|---|
| `@Sprite.ready` | Uma vez, ao construir a entidade |
| `@Sprite.update` | Todo frame (recebe `dt`) |
| `@Sprite.fixed_update` | Na taxa fixa de física |
| `@Sprite.draw` | Todo frame para renderização (recebe `surface`) |
| `@Sprite.destroy` | Antes da entidade ser removida |
| `@Sprite.on_collision_enter` | Primeiro frame de colisão (recebe `CollisionInfo`) |
| `@Sprite.on_collision_stay` | Cada frame enquanto colide (recebe `CollisionInfo`) |
| `@Sprite.on_collision_exit` | Quando a colisão termina (recebe `CollisionInfo`) |
| `@Sprite.on_trigger_enter` | Ao entrar em uma trigger zone |
| `@Sprite.on_trigger_exit` | Ao sair de uma trigger zone |
| `@Sprite.pause` | Quando o jogo é pausado |
| `@Sprite.resume` | Quando o jogo é despausado |

### Propriedades e Métodos da Entity

```python
# Posição (atalhos para transform)
entity.x = 100
entity.y = 200
entity.position = Vector2(100, 200)
entity.rotation = 45.0   # graus
entity.scale = Vector2(2, 2)

# Renderização
entity.visible = True/False
entity.active = True/False   # desativa update E renderização
entity.alpha = 128           # 0–255
entity.tint = Color(255, 100, 100)  # colorização vermelha
entity.image = alguma_surface

# Utilitários
entity.draw_self(surface, offset)  # renderiza respeitando rotação, escala, alpha, tint
entity.collides_with(outro)        # AABB simples sem physics
entity.distance_to(outro)          # distância em pixels
entity.destroy()                   # remove do jogo

# Physics (se tiver Rigidbody)
entity.set_velocity(vx, vy)
entity.add_force(Vector2(0, -500))

# Componentes customizados
entity.add_component("saude", SistemaDeVida())
entity.get_component("saude")
entity.has_component("saude")
entity.remove_component("saude")
```

### SpriteGroup — Grupos de Entidades

```python
inimigos = SpriteGroup()
inimigos.add(Goblin(), Goblin(), Troll())

# No update do jogo:
inimigos.update(dt)

# No draw do jogo:
inimigos.draw(screen, Camera.offset)

# Busca por tag
boss = inimigos.find_first_by_tag("boss")
todos_os_goblins = inimigos.find_by_tag("goblin")

# Remove os destruídos
inimigos.purge_destroyed()
```

> **Regra do draw:** se a entidade define `@Sprite.draw`, esse hook é inteiramente responsável pela renderização — chame `self.draw_self()` dentro dele. Se a entidade **não** define o hook mas possui `image`, o `SpriteGroup` chama `draw_self()` automaticamente como fallback. Isso evita que o sprite seja desenhado duas vezes.

---

## 5. Transform — Posição, Rotação e Escala

**Módulo:** `nestifypy.pyunix.transform`

Cada entidade tem um `transform` que gerencia seu estado espacial. Suporta hierarquia pai-filho, onde filhos herdam a transformação dos pais.

```python
# Espaço local (relativo ao pai)
entity.transform.local_position = Vector2(10, 0)
entity.transform.local_rotation = 45.0
entity.transform.local_scale    = Vector2(1, 1)

# Espaço mundo (composto pela cadeia de pais)
pos_mundo = entity.transform.position
rot_mundo = entity.transform.rotation

# Hierarquia
filho.transform.set_parent(pai.transform, keep_world_position=True)
filho.transform.set_parent(None)  # desvincula

# Utilitários
entity.transform.translate(Vector2(5, 0))  # move no espaço mundo
entity.transform.look_at(alvo_pos)         # rotaciona em direção a um ponto
frente = entity.transform.forward()        # vetor unitário na direção da rotação

# Conversões de espaço
ponto_local = entity.transform.to_local(ponto_mundo)
ponto_mundo = entity.transform.to_world(ponto_local)
```

---

## 6. Input — Teclado, Mouse e Gamepad

**Módulo:** `nestifypy.pyunix.input`

O sistema de input desacopla as intenções do jogo das teclas físicas através do sistema de **actions** e **axes**.

### Configuração (no `@Game.start`)

```python
from nestifypy.pyunix.input import Input

# Actions: mapeia uma intenção para uma ou mais teclas
Input.bind_action("pular",   "SPACE", "W", "UP")
Input.bind_action("atacar",  "z", "j")
Input.bind_action("correr",  "LSHIFT")

# Axes: dois extremos de -1.0 a +1.0
Input.bind_axis("horizontal", positive="RIGHT", negative="LEFT")
Input.bind_axis("vertical",   positive="DOWN",  negative="UP")
```

### API de Polling (dentro do `@Sprite.update` ou `@Game.update`)

```python
# Teclas diretas
Input.is_pressed("SPACE")         # verdadeiro enquanto a tecla está pressionada
Input.is_just_pressed("SPACE")    # verdadeiro apenas no frame em que foi pressionada
Input.is_just_released("SPACE")   # verdadeiro apenas no frame em que foi solta

# Actions
Input.action_pressed("pular")      # verdadeiro se qualquer tecla vinculada estiver pressionada
Input.action_just_pressed("pular")
Input.action_just_released("pular")

# Axes
h = Input.get_axis("horizontal")   # -1.0, 0.0 ou 1.0
movimento = Input.get_axis_vector("horizontal", "vertical")  # Vector2

# Mouse
pos = Input.mouse_position          # (x, y) em pixels
delta = Input.mouse_delta           # movimento desde o último frame
Input.mouse_pressed("left")         # "left", "middle" ou "right"
Input.scroll                        # +1 (cima) ou -1 (baixo)
Input.set_cursor_visible(False)     # esconde o cursor

# Gamepad
Input.gamepad_axis(0, 0)            # joystick 0, eixo X esquerdo
Input.gamepad_button(0, 0)          # joystick 0, botão 0
Input.gamepad_count()               # quantos gamepads estão conectados
```

### API de Decorators (para reações a eventos)

```python
class Jogador(Entity):

    @Input.key_down("SPACE")
    def ao_pular(self):
        self.pular()

    @Input.key_held("RIGHT")
    def ao_mover_direita(self):
        self.x += 2

    @Input.mouse_click("left")
    def ao_clicar(self):
        print("Clique esquerdo!")

    @Input.action("atacar")
    def ao_atacar(self):
        self.disparar()
```

---

## 7. Physics — Física 2D

**Módulo:** `nestifypy.pyunix.physics`

Sistema de física com corpos DYNAMIC, KINEMATIC e STATIC, colisores AABB e circulares, fricção, restituição, raycasting e queries de sobreposição.

### Tipos de Corpo

| BodyType | Comportamento |
|---|---|
| `BodyType.DYNAMIC` | Afetado por gravidade e forças |
| `BodyType.KINEMATIC` | Movido manualmente, colide mas não recebe forças |
| `BodyType.STATIC` | Nunca se move (paredes, plataformas) |

### Criando Entidades com Física

```python
from nestifypy.pyunix.physics import (
    Rigidbody, BoxCollider, CircleCollider,
    PhysicsMaterial, BodyType, PhysicsWorld
)

class Bola(Entity):
    def __init__(self):
        super().__init__(
            x=400, y=100,
            rigidbody=Rigidbody(
                body_type=BodyType.DYNAMIC,
                mass=1.0,
                drag=0.1,
                gravity_scale=1.0,
            ),
            collider=CircleCollider(radius=16),
        )

class Parede(Entity):
    def __init__(self):
        super().__init__(
            x=400, y=580,
            rigidbody=Rigidbody(body_type=BodyType.STATIC),
            collider=BoxCollider(width=800, height=20),
        )
```

### Materiais de Física

```python
material_borracha = PhysicsMaterial(friction=0.1, bounciness=0.8)
collider = BoxCollider(32, 32, material=material_borracha)
```

### Configurando a Gravidade Global

```python
PhysicsWorld.set_gravity(0, 980)    # gravidade padrão (para baixo)
PhysicsWorld.set_gravity(0, 0)      # sem gravidade (top-down)
PhysicsWorld.set_gravity(0, 300)    # gravidade suave
```

### Spatial Hashing — Performance com Muitos Corpos

A detecção de colisão usa **spatial hashing** internamente: o mundo é dividido em células de grade e apenas pares de entidades que ocupam a mesma célula são testados. Isso reduz a complexidade de O(n²) para próximo de O(n), permitindo centenas de corpos físicos sem queda de FPS.

O tamanho padrão da célula é **64 px**. Ajuste para melhor performance conforme o tamanho médio dos seus colisores:

```python
# Regra geral: célula ≈ 2× a dimensão do maior colisador
PhysicsWorld.set_cell_size(64)    # padrão — bom para jogos com tiles de 32 px
PhysicsWorld.set_cell_size(128)   # colisores grandes (veículos, chefes)
PhysicsWorld.set_cell_size(32)    # colisores muito pequenos (projéteis, partículas físicas)
```

### Aplicando Forças

```python
# Pelo Rigidbody
entity.rigidbody.add_force(Vector2(0, -500))   # impulso para cima
entity.rigidbody.add_impulse(Vector2(200, 0))  # mudança direta de velocidade
entity.rigidbody.set_velocity(100, 0)
entity.rigidbody.stop()

# Atalho pela Entity
entity.set_velocity(100, -300)
entity.add_force(Vector2(0, -500))
```

### Congelando Eixos

```python
Rigidbody(freeze_x=True)  # não se move horizontalmente
Rigidbody(freeze_y=True)  # não se move verticalmente
```

### Camadas e Máscaras de Colisão

```python
# Jogador só colide com "inimigos" e "terreno"
Rigidbody(layer="jogador", mask={"inimigos", "terreno"})

# Inimigo só colide com "jogador" e "terreno"
Rigidbody(layer="inimigos", mask={"jogador", "terreno"})
```

### Trigger Zones (Zonas Sem Colisão Física)

```python
collider = BoxCollider(64, 64, is_trigger=True)

class Jogador(Entity):
    @Sprite.on_trigger_enter
    def entrou_zona(self, info):
        print(f"Entrou em {info.other}")
```

### Queries do PhysicsWorld

```python
# Retorna todas as entidades dentro de um raio
proximos = PhysicsWorld.overlap_circle(Vector2(400, 300), radius=100)

# Retorna todas as entidades dentro de um retângulo (l, t, r, b)
na_area = PhysicsWorld.overlap_rect((100, 100, 300, 300))

# Raio — retorna (entidade, ponto_de_impacto, distância) ou None
resultado = PhysicsWorld.raycast(
    origin=jogador.position,
    direction=Vector2(1, 0),
    max_distance=500,
)
if resultado:
    entidade_atingida, ponto, distancia = resultado
```

### Debug Visual

```python
# No seu método de draw:
PhysicsWorld.draw_debug(screen, Camera.offset)
# Desenha wireframes coloridos: verde = DYNAMIC, azul = STATIC, amarelo = trigger
```

---

## 8. Camera — Câmera 2D

**Módulo:** `nestifypy.pyunix.camera`

Câmera com follow suave, dead zone, limites de mundo, zoom, screen shake e camadas parallax.

### Seguindo uma Entidade

```python
from nestifypy.pyunix.camera import Camera

# Suave (0.0 = sem movimento, 1.0 = snap instantâneo)
Camera.follow(jogador, smooth=0.08)

# Dead zone: a câmera só se move quando o alvo sair da área central
Camera.set_dead_zone(80, 60)

# Para de seguir
Camera.unfollow()
```

### Limites do Mundo

```python
# A câmera nunca mostrará fora desse retângulo (left, top, right, bottom)
Camera.set_world_bounds(0, 0, 3200, 1800)
Camera.clear_bounds()
```

### Zoom

```python
Camera.zoom(1.5)                       # zoom imediato
Camera.zoom_to(2.0, duration=0.5)      # zoom animado (usa Tween)
```

### Screen Shake

```python
Camera.shake(intensity=8, duration=0.4)   # shake clássico
Camera.trauma(0.7)                         # shake baseado em trauma (bom para impactos)
```

### Parallax

```python
Camera.add_parallax_layer("ceu",    surface_ceu,    factor=0.1)
Camera.add_parallax_layer("nuvens", surface_nuvens, factor=0.3)
Camera.add_parallax_layer("arvores",surface_arvores,factor=0.6)

# No draw, antes de renderizar as entidades:
Camera.draw_parallax(screen)
```

### Usando o Offset para Renderização

```python
# Ao desenhar sprites no mundo:
entity.draw_self(screen, Camera.offset)

# Converter coordenadas
pos_tela = Camera.world_to_screen(mundo_x, mundo_y)
pos_mundo = Camera.screen_to_world(tela_x, tela_y)
```

---

## 9. Assets — Carregamento de Recursos

**Módulo:** `nestifypy.pyunix.assets`

Cache centralizado para imagens, spritesheets, sons e fontes. Cada asset é carregado apenas uma vez — chamadas subsequentes retornam o objeto em cache.

### Configuração

```python
from nestifypy.pyunix.assets import Assets

Assets.set_base_path("assets/")     # diretório base para todos os assets
Assets.alias("heroi", "personagens/heroi_spritesheet.png")
```

### Imagens

```python
img = Assets.image("player.png")
img = Assets.image("player.png", scale=(64, 64))        # redimensiona
img = Assets.image("player.png", flip_x=True)           # espelha
img = Assets.image("player.png", alpha=False)           # sem transparência
```

### Spritesheets

```python
# Todos os frames de uma spritesheet uniforme
frames = Assets.spritesheet("heroi.png", frame_size=(32, 32))

# Apenas alguns frames (start=índice, count=quantidade)
idle_frames = Assets.spritesheet("heroi.png", (32, 32), start=0, count=4)
run_frames  = Assets.spritesheet("heroi.png", (32, 32), start=4, count=8)

# Uma linha específica
linha2 = Assets.spritesheet_row("inimigo.png", (16, 16), row=1, count=6)

# Regiões arbitrárias (atlas não-uniforme)
frames = Assets.spritesheet_region("atlas.png", [
    (0, 0, 48, 64),
    (48, 0, 48, 64),
    (96, 0, 48, 64),
])
```

### Sons

```python
sfx = Assets.sound("jump.wav")   # pygame.mixer.Sound
```

### Fontes

```python
font = Assets.font("Arial", size=24, bold=True)    # fonte do sistema
font = Assets.font_file("assets/minha.ttf", size=32)  # arquivo de fonte
```

### Pré-carregamento

```python
# Carrega tudo antes do jogo começar, evitando travadas
Assets.preload("player.png", "tiles.png", "bg.png")
Assets.preload_sounds("jump.wav", "music.ogg")
```

### Utilitários de Surface

```python
# Criar surface em branco
surf = Assets.create_surface(64, 64, color=(0, 0, 0, 0))

# Colorir uma surface
tintada = Assets.tint_surface(sprite.image, (255, 100, 100))

# Contorno ao redor dos pixels opacos
contornada = Assets.outline_surface(sprite.image, color=(255, 255, 0), thickness=2)
```

---

## 10. Animation — Animação por Spritesheet

**Módulo:** `nestifypy.pyunix.animation`

Sistema de animação por estados com state machine automática, eventos por frame, ping-pong e callbacks de loop/conclusão.

### Configurando Clips

```python
from nestifypy.pyunix.animation import AnimationClip

class Heroi(Entity):

    @Sprite.ready
    def setup(self):
        sheet = Assets.spritesheet("heroi.png", (32, 32))

        anim = self.animator  # acesso lazy ao Animator

        anim.add_clip("idle", sheet[0:4],  fps=8)
        anim.add_clip("run",  sheet[4:12], fps=16)
        anim.add_clip("jump", sheet[12:16], fps=12, loop=False,
                      on_complete=self.ao_pousar)

        # Transições automáticas (state machine)
        anim.add_transition("idle", "run",  condition=lambda: abs(self.vel_x) > 10)
        anim.add_transition("run",  "idle", condition=lambda: abs(self.vel_x) <= 10)

        anim.play("idle")

    def ao_pousar(self):
        self.animator.play("idle")

    @Sprite.update
    def atualizar(self, dt):
        self.animator.update(dt)
```

### Opções dos Clips

```python
anim.add_clip(
    name="correr",
    frames=frames,
    fps=16,
    loop=True,            # loop contínuo
    ping_pong=False,      # vai e volta (para animações de balanço, etc.)
    frame_events={        # callbacks em frames específicos
        3: lambda: Audio.play_sfx("passos.wav"),
        7: lambda: Audio.play_sfx("passos.wav"),
    },
    on_complete=minha_funcao,   # só para clips com loop=False
    on_loop=minha_funcao,       # chamado a cada reinício do loop
)
```

### Controle de Reprodução

```python
anim.play("idle")           # inicia o clip
anim.play("idle", reset=True)  # força reinício do mesmo clip
anim.stop()                 # pausa no frame atual
anim.resume()               # continua de onde parou
anim.set_speed(2.0)         # velocidade: 1.0 normal, 2.0 dobro, -1.0 reverso
anim.set_frame(3)           # vai direto para o frame 3

# Propriedades de leitura
anim.current_clip_name      # nome do clip atual
anim.current_frame          # índice do frame atual
anim.is_playing             # True/False
anim.normalized_time        # 0.0–1.0 (progresso no clip)
```

---

## 11. Audio — Música e Efeitos Sonoros

**Módulo:** `nestifypy.pyunix.audio`

```python
from nestifypy.pyunix.audio import Audio
```

### Música (streaming)

```python
Audio.play_music("trilha.mp3", loop=True, fade_ms=1000)
Audio.stop_music(fade_ms=500)
Audio.pause_music()
Audio.resume_music()
Audio.set_music_volume(0.8)   # 0.0–1.0
Audio.music_playing           # True/False
```

### Efeitos Sonoros

```python
Audio.play_sfx("explosao.wav")
Audio.play_sfx("tiro.wav", volume=0.6)
Audio.play_sfx("moeda.wav", pitch_variance=0.15)  # variação aleatória de pitch (requer numpy)
Audio.play_sfx("laser.wav", loops=-1)             # loop infinito
Audio.set_sfx_volume(0.5)
```

> **`pitch_variance`:** requer `numpy`. O som gerado é mantido em memória enquanto toca e descartado automaticamente ao terminar — sem risco de corte prematuro pelo garbage collector.

### Áudio Posicional 2D

```python
# Volume atenuado pela distância entre fonte e ouvinte
Audio.play_positional(
    "passos.wav",
    source_x=inimigo.x, source_y=inimigo.y,
    listener_x=jogador.x, listener_y=jogador.y,
    max_distance=600,
)
```

### Controles Globais

```python
Audio.pause_all()    # pausa música e efeitos
Audio.resume_all()
Audio.stop_all()
Audio.is_paused      # True/False
```

---

## 12. Particles — Sistema de Partículas

**Módulo:** `nestifypy.pyunix.particles`

```python
from nestifypy.pyunix.particles import ParticleSystem
from nestifypy.pyunix.math import Color, Vector2
```

> **Performance:** o `ParticleSystem` usa um **object pool de tamanho fixo**. Os objetos de partícula são alocados uma única vez ao chamar `configure()` ou `start()` e depois apenas *reativados* — sem alocações por frame, sem pressão no garbage collector. Emissores de alta frequência (fogo, faíscas, rain) se beneficiam diretamente disso.

### Explosão (burst)

```python
explosao = ParticleSystem(x=400, y=300)
explosao.configure(
    count=80,
    lifetime=(0.4, 1.2),        # (mínimo, máximo) em segundos
    speed=(60, 200),            # velocidade inicial
    angle=(-180, 180),          # qualquer direção
    start_color=Color.from_hex("#FF6600"),
    end_color=Color(80, 0, 0, 0),  # desaparece
    start_size=6,
    end_size=0,
    gravity=Vector2(0, 120),
)
explosao.burst()   # dispara tudo de uma vez
```

### Emissor Contínuo (fogo, fumaça)

```python
fogo = ParticleSystem(x=200, y=500)
fogo.configure(
    emit_rate=40,                # partículas por segundo
    lifetime=(0.5, 1.5),
    speed=(20, 80),
    angle=(-110, -70),           # para cima com variação
    start_color=Color(255, 150, 0, 200),
    end_color=Color(100, 50, 0, 0),
    start_size=3,
    end_size=8,
    spread=(5, 0),               # variação na posição de spawn
)
fogo.start()

# Para parar
fogo.stop()
```

### No Loop do Jogo

```python
@Sprite.update
def atualizar(self, dt):
    self.fogo.update(dt)

@Sprite.draw
def renderizar(self, surface):
    self.fogo.draw(surface, Camera.offset)
```

---

## 13. Tween — Animações de Propriedades

**Módulo:** `nestifypy.pyunix.tween`

Anima qualquer atributo numérico de qualquer objeto ao longo do tempo, com curvas de easing.

```python
from nestifypy.pyunix.tween import Tween, Ease
```

### Exemplos Básicos

```python
# Move o objeto para x=300 em 1 segundo
Tween.to(entity.transform, "x", 300, duration=1.0, ease=Ease.OUT_CUBIC)

# Fade (transparência)
Tween.fade(entity, end_alpha=0, duration=0.5)

# Move para uma posição (Vector2)
Tween.move(entity, target=Vector2(400, 300), duration=1.0)

# Escala
Tween.scale_to(entity, target=Vector2(2, 2), duration=0.3)

# Rotação
Tween.rotate_to(entity, target_degrees=180, duration=0.8)

# Cor
Tween.color(entity, "tint", Color.RED, duration=0.4)
```

### Encadeamento e Callbacks

```python
(Tween.to(caixa, "x", 200, 0.5)
      .then(Tween.to(caixa, "y", 300, 0.5))
      .then(Tween.to(caixa, "x", 100, 0.5))
      .on_complete(lambda: print("Animação completa!")))
```

### Com Delay

```python
Tween.to(entity, "alpha", 0, duration=1.0, delay=2.0)  # começa após 2 segundos
```

### Curvas de Easing Disponíveis

```
Ease.LINEAR
Ease.IN_QUAD    Ease.OUT_QUAD    Ease.IN_OUT_QUAD
Ease.IN_CUBIC   Ease.OUT_CUBIC   Ease.IN_OUT_CUBIC
Ease.IN_QUART   Ease.OUT_QUART   Ease.IN_OUT_QUART
Ease.IN_SINE    Ease.OUT_SINE    Ease.IN_OUT_SINE
Ease.IN_EXPO    Ease.OUT_EXPO    Ease.IN_OUT_EXPO
Ease.IN_ELASTIC Ease.OUT_ELASTIC
Ease.IN_BOUNCE  Ease.OUT_BOUNCE  Ease.IN_OUT_BOUNCE
Ease.IN_BACK    Ease.OUT_BACK    Ease.IN_OUT_BACK
```

### Cancelando Tweens

```python
Tween.kill(entity)    # cancela todos os tweens do objeto
Tween.kill_all()      # cancela todos os tweens ativos
```

---

## 14. Scene — Gerenciador de Cenas

**Módulo:** `nestifypy.pyunix.scene`

Gerenciamento de estados do jogo (menu, gameplay, gameover) via uma pilha de cenas.

### Criando e Registrando Cenas

```python
from nestifypy.pyunix.scene import Scene

@Scene("menu")
class MenuCena:

    @Scene.load
    def ao_carregar(self):
        self.titulo = Text("Menu Principal", x=400, y=200, anchor="center")

    @Scene.unload
    def ao_descarregar(self):
        pass  # limpeza se necessário

    @Scene.update
    def atualizar(self, dt):
        if Input.is_just_pressed("RETURN"):
            Scene.switch("jogo", data={"dificuldade": "normal"})

    @Scene.draw
    def renderizar(self, surface):
        surface.fill((20, 20, 30))
        self.titulo.draw(surface)

@Scene("jogo")
class JogoCena:

    @Scene.load
    def ao_carregar(self, data=None):
        # data contém o que foi passado por push/switch
        dificuldade = data.get("dificuldade", "normal") if data else "normal"
        self.jogador = Jogador(dificuldade=dificuldade)

    @Scene.update
    def atualizar(self, dt):
        self.jogador._dispatch("update", dt)

    @Scene.draw
    def renderizar(self, surface):
        surface.fill((0, 0, 0))
        self.jogador._dispatch("draw", surface)
```

### Operações de Pilha

```python
Scene.push("menu")                            # empurra nova cena, pausa a atual
Scene.push("pause_menu", data={"origem": "jogo"})  # com dados opcionais

Scene.pop()                                   # remove cena do topo, retorna à anterior
Scene.pop(data={"resultado": "vitoria"})      # passa dados para o @Scene.resume da cena abaixo

Scene.switch("jogo")                          # substitui a cena do topo
Scene.switch("jogo", data={"nivel": 2})       # com dados para o @Scene.load

Scene.pop_all()                               # limpa toda a pilha

# Forçar recriação de uma cena (descarta o estado salvo)
Scene.destroy_instance("menu")
```

> **Compatibilidade:** o parâmetro `data` é totalmente opcional. Hooks `@Scene.load` sem o argumento continuam funcionando — o dispatch detecta a assinatura e chama sem parâmetro se necessário.

### No Loop Principal

```python
@Game.update
def atualizar(self, dt):
    Scene.update(dt)

@Game.draw
def renderizar(self, screen):
    Scene.draw(screen)
```

---

## 15. Timer — Timers e Callbacks

**Módulo:** `nestifypy.pyunix.timer`

```python
from nestifypy.pyunix.timer import Timer
```

```python
# Executar uma função uma vez após X segundos
Timer.after(3.0, lambda: print("3 segundos!"))

# Executar repetidamente a cada X segundos
ticker = Timer.every(1.0, lambda: print("Tick!"))

# Cancelar um timer específico
Timer.cancel(ticker)

# Cancelar por tag
Timer.after(5.0, lambda: spawnar_inimigo(), tag="spawn")
Timer.cancel_tag("spawn")

# Cancelar todos
Timer.clear()

# Pausar e retomar TODOS os timers
Timer.pause()     # tick() fica inativo enquanto pausado
Timer.resume()
Timer.is_paused   # True/False

# Quantidade de timers ativos
print(Timer.count)
```

> **Integração com pausa do jogo:** chame `Timer.pause()` dentro do `@Game.on_pause` e `Timer.resume()` dentro do `@Game.on_resume` para que os timers respeitem o estado de pausa da simulação.

---

## 16. Events — Sistema de Eventos Pub/Sub

**Módulo:** `nestifypy.pyunix.events`

Comunicação desacoplada entre sistemas do jogo sem referências diretas.

```python
from nestifypy.pyunix.events import Event
```

### Emitindo e Ouvindo

```python
# Registrar um ouvinte
@Event.on("jogador_morreu")
def ao_morrer(data):
    print(f"Pontuação final: {data['pontos']}")

# Emitir um evento
Event.emit("jogador_morreu", {"pontos": 1500})

# Ouvinte que dispara apenas uma vez
@Event.once("primeiro_inimigo_derrotado")
def conquista_desbloqueada():
    print("Conquista!")
```

### Eventos Adiados (Próximo Frame)

```python
# Útil para evitar modificar listas enquanto itera sobre elas
Event.emit_deferred("fase_concluida")
Event.flush()  # processa todos os eventos adiados (feito automaticamente pelo engine)
```

### Gerenciamento

```python
Event.off("jogador_morreu", ao_morrer)    # remove um ouvinte específico
Event.clear("jogador_morreu")             # remove todos os ouvintes do evento
Event.clear()                             # remove todos os ouvintes
Event.listeners("jogador_morreu")         # lista os ouvintes
Event.has_listeners("jogador_morreu")     # True/False
```

---

## 17. TileMap — Mapas em Tiles

**Módulo:** `nestifypy.pyunix.tilemap`

```python
from nestifypy.pyunix.tilemap import TileSet, TileMap
```

### Criando um Mapa

```python
# Tileset: imagem + tamanho de cada tile
tileset = TileSet("tiles.png", tile_size=(16, 16))
tileset.mark_solid(1, 2, 3, 4)   # IDs que bloqueiam o movimento

# TileMap: pode ter múltiplas camadas
mapa = TileMap(tileset, tile_size=(16, 16))

# Carregando camadas de arrays 2D (0 = vazio)
mapa.load_layer("fundo", [
    [5, 5, 5, 5, 5],
    [5, 0, 0, 0, 5],
    [5, 0, 0, 0, 5],
    [1, 1, 1, 1, 1],  # chão sólido
])

mapa.load_layer("decoracao", [
    [0, 0, 7, 0, 0],
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0],
])

# Ou carregando de CSV
mapa.load_layer_csv("terreno", "levels/fase1.csv")
```

### Gerando Colisores Automáticos

```python
# Gera BoxColliders estáticos para todos os tiles sólidos
mapa.build_colliders()

# Ou apenas em uma camada específica
mapa.build_colliders(layer_name="fundo")
```

### Renderizando

```python
@Game.draw
def renderizar(self, screen):
    screen.fill((0, 0, 0))
    # A câmera culling é automática — só renderiza tiles visíveis
    mapa.draw(screen, Camera.offset, Camera.zoom_level)
```

### Acessando Tiles

```python
tile_id = mapa.get_tile("fundo", col=3, row=2)
mapa.set_tile("fundo", col=3, row=2, tile_id=0)  # apaga o tile

# Converter entre coordenadas
col, row = mapa.world_to_tile(jogador.x, jogador.y)
mundo_x, mundo_y = mapa.tile_to_world(5, 3)

# Dimensões
print(mapa.width_tiles, mapa.height_tiles)
print(mapa.pixel_width, mapa.pixel_height)
```

### Propriedades Customizadas de Tile

```python
tileset.set_property(7, tipo="agua", dano=5)
tipo = tileset.get_property(7, "tipo")  # "agua"
```

---

## 18. Text — Renderização de Texto

**Módulo:** `nestifypy.pyunix.text`

`Text` é uma `Entity` especializada em renderizar texto com sombra, contorno, quebra de linha e alinhamento.

```python
from nestifypy.pyunix.text import Text

# Texto básico
titulo = Text("Olá, Mundo!", x=400, y=200, size=48, anchor="center")

# Texto com sombra e contorno
label = Text(
    "GAME OVER",
    x=400, y=300,
    size=64,
    color="white",
    shadow=True, shadow_color="black", shadow_offset=(3, 3),
    outline=True, outline_color=(50, 0, 0), outline_size=2,
    anchor="center",
    layer="ui",
)

# Texto com quebra de linha automática
descricao = Text(
    "Uma aventura épica em terras desconhecidas...",
    x=50, y=100,
    size=18,
    max_width=300,   # quebra a linha em 300 pixels
    align="left",    # "left", "center" ou "right"
)

# Atualização dinâmica
label.set_text(f"Pontos: {self.pontos}")
label.set_color("yellow")
label.set_size(32)

# Renderizando
titulo.draw(screen)
```

### Registrando Fontes Customizadas

```python
from nestifypy.pyunix.fonts import Fonts

Fonts.load("pixel", "assets/fontes/pixel.ttf")
label = Text("Score", font_name="pixel", size=24)
```

---

## 19. Math — Vetores e Cores

**Módulo:** `nestifypy.pyunix.math`

### Vector2

```python
from nestifypy.pyunix.math import Vector2

v = Vector2(3, 4)

# Construtores
Vector2.zero()               # (0, 0)
Vector2.one()                # (1, 1)
Vector2.up()                 # (0, -1)
Vector2.down()               # (0, 1)
Vector2.left()               # (-1, 0)
Vector2.right()              # (1, 0)
Vector2.from_angle(45.0)     # a partir de graus
Vector2.from_tuple((3, 4))

# Propriedades
v.magnitude          # comprimento (5.0)
v.magnitude_squared  # mais rápido para comparações
v.normalized         # vetor unitário
v.angle              # ângulo em graus
v.perpendicular      # vetor perpendicular

# Operações
v1 + v2
v1 - v2
v * 2.5
v / 2.0
-v

v1.dot(v2)           # produto escalar
v1.cross(v2)         # produto vetorial 2D
v1.distance_to(v2)
v1.lerp(v2, 0.5)
v1.move_towards(v2, max_delta=5.0)
v1.reflect(normal)
v1.clamp_magnitude(100)
v1.rotate(45.0)
v1.angle_to(v2)

v.to_tuple()         # (x, y)
v.to_int_tuple()     # (int(x), int(y))
```

### Color

```python
from nestifypy.pyunix.math import Color

vermelho = Color(255, 0, 0)
verde = Color.from_hex("#00FF00")
azul = Color.from_normalized(0.0, 0.0, 1.0)
rosa = Color.from_hsv(330, 0.6, 1.0)

# Cores pré-definidas
Color.WHITE, Color.BLACK, Color.RED, Color.GREEN
Color.BLUE, Color.YELLOW, Color.CYAN, Color.MAGENTA
Color.TRANSPARENT

# Operações
mistura = vermelho.lerp(verde, 0.5)
mais_claro = cor.brighten(50)
mais_escuro = cor.darken(30)
semi = cor.with_alpha(128)

# Conversões
cor.to_rgb()         # (255, 0, 0)
cor.to_rgba()        # (255, 0, 0, 255)
cor.to_hex()         # "#FF0000"
cor.to_hsv()         # (0.0, 1.0, 1.0)
cor.to_normalized()  # (1.0, 0.0, 0.0, 1.0)
```

---

## 20. Window — Gerenciamento da Janela

**Módulo:** `nestifypy.pyunix.window`

Normalmente a janela é gerenciada automaticamente pelo `@Game(...)`. Use `Window` diretamente para customizações.

```python
from nestifypy.pyunix.window import Window

Window.set_title("Meu Jogo v1.0")
Window.set_icon("icone.png")
Window.toggle_fullscreen()
Window.screenshot("screenshot.png")
Window.set_clear_color((20, 20, 30))

print(Window.size)        # (800, 600)
print(Window.center_pos)  # (400, 300)
```

---

## 21. Save — Sistema de Salvamento

**Módulo:** `nestifypy.pyunix.save`

Sistema de save/load baseado em JSON com suporte a múltiplos slots, valores default, auto-save por timer e uma API simples de get/set. Tudo é lazy — nada é lido do disco até o primeiro acesso.

```python
from nestifypy.pyunix.save import Save
```

### Configuração Inicial

```python
@Game.start
def iniciar(self):
    Save.set_path("saves/")          # diretório dos arquivos .json
    Save.set_defaults({
        "pontuacao":  0,
        "nivel":      1,
        "vida_max":   3,
        "upgrades":   [],
        "opcoes": {
            "volume_musica": 0.8,
            "volume_sfx":    1.0,
            "fullscreen":    False,
        },
    })
    Save.load()   # carrega o slot 1 (ou inicializa com defaults se não existir)
```

### Leitura e Escrita

```python
# Ler (retorna default se a chave não existir no save)
pontos  = Save.get("pontuacao")          # 0
nivel   = Save.get("nivel")              # 1
opcoes  = Save.get("opcoes")             # dict completo

# Escrever em memória (não vai para o disco ainda)
Save.set("pontuacao", 1500)
Save.set("nivel", 3)
Save.set("upgrades", ["dash", "double_jump"])

# Verificar existência
if Save.has("chave_secreta"):
    desbloquear_easter_egg()

# Remover uma chave
Save.delete("dado_temporario")

# Bulk update
Save.update({"pontuacao": 2000, "nivel": 4})

# Snapshot completo
tudo = Save.all()    # dict com todos os dados em memória
```

### Persistindo no Disco

```python
Save.commit()     # ou Save.save() — sinônimos
```

> **Importante:** `Save.set()` só modifica a memória. Chame `Save.commit()` explicitamente (ex.: ao sair de uma fase, ao fechar o jogo) ou use `auto_save`.

### Auto-Save

```python
# Habilitar auto-save a cada 60 segundos
Save.auto_save(interval=60.0)

# Obrigatório: chamar tick no loop do jogo
@Game.update
def atualizar(self, dt):
    Save.tick(dt)   # só escreve no disco quando o intervalo elapsa E há dados novos
```

### Múltiplos Slots

```python
# Slot atual (padrão: 1)
Save.current_slot        # 1

# Verificar se um slot existe
Save.slot_exists(2)      # False

# Trocar de slot (commit o atual antes se necessário)
Save.commit()
Save.use_slot(2)
Save.load()

# Listar todos os slots com arquivo no disco
slots = Save.list_slots()   # [1, 2, 3]

# Deletar um slot do disco
Save.delete_slot(2)
```

### Reset e Estado

```python
Save.reset()             # volta os dados em memória para os defaults (não apaga o disco)
Save.commit()            # persiste o reset

Save.is_dirty            # True se há mudanças não salvas em memória
```

### Exemplo de Uso Típico

```python
# Ao completar uma fase
def fase_concluida(self):
    Save.set("nivel", Save.get("nivel") + 1)
    Save.set("pontuacao", Save.get("pontuacao") + self.pontos_fase)
    Save.commit()

# Ao abrir o menu de opções
def aplicar_opcoes(self, volume_musica, fullscreen):
    opcoes = Save.get("opcoes")
    opcoes["volume_musica"] = volume_musica
    opcoes["fullscreen"]    = fullscreen
    Save.set("opcoes", opcoes)
    Save.commit()

# Ao fechar o jogo
@Game.stop
def ao_fechar(self):
    Save.commit()   # garante que nada seja perdido
```

---

## 22. Exemplo Completo — Jogo Simples

Um platformer minimalista com física, câmera suave e HUD de pontos.

```python
from nestifypy.pyunix.app import Game
from nestifypy.pyunix.sprite import Entity, Sprite, SpriteGroup
from nestifypy.pyunix.physics import Rigidbody, BoxCollider, BodyType, PhysicsWorld
from nestifypy.pyunix.input import Input
from nestifypy.pyunix.camera import Camera
from nestifypy.pyunix.assets import Assets
from nestifypy.pyunix.math import Vector2, Color
from nestifypy.pyunix.timer import Timer
from nestifypy.pyunix.audio import Audio
from nestifypy.pyunix.save import Save


class Jogador(Entity):

    def __init__(self):
        super().__init__(
            x=200, y=300,
            rigidbody=Rigidbody(
                body_type=BodyType.DYNAMIC,
                gravity_scale=1.0,
            ),
            collider=BoxCollider(28, 48),
        )
        self.velocidade = 200
        self.no_chao = False

    @Sprite.update
    def mover(self, dt):
        h = Input.get_axis("horizontal")
        self.rigidbody.velocity.x = h * self.velocidade

        if Input.action_just_pressed("pular") and self.no_chao:
            self.rigidbody.add_impulse(Vector2(0, -450))
            self.no_chao = False

    @Sprite.on_collision_enter
    def ao_colidir(self, info):
        if info.normal.y < -0.5:
            self.no_chao = True

    # @Sprite.draw definido: SpriteGroup não chamará draw_self automaticamente
    @Sprite.draw
    def renderizar(self, surface):
        import pygame
        rect = pygame.Rect(self.x - 14, self.y - 24, 28, 48)
        pygame.draw.rect(surface, (100, 180, 255), rect)


class Plataforma(Entity):

    def __init__(self, x, y, largura, altura=20):
        super().__init__(
            x=x, y=y,
            rigidbody=Rigidbody(body_type=BodyType.STATIC),
            collider=BoxCollider(largura, altura),
        )
        self._largura = largura
        self._altura  = altura

    @Sprite.draw
    def renderizar(self, surface):
        import pygame
        rect = pygame.Rect(
            self.x - self._largura // 2,
            self.y - self._altura  // 2,
            self._largura, self._altura,
        )
        pygame.draw.rect(surface, (80, 160, 80), rect)


@Game(title="Platformer Simples", size=(800, 450), fps=60)
class MeuJogo:

    @Game.start
    def iniciar(self):
        # Input
        Input.bind_action("pular", "SPACE", "UP", "W")
        Input.bind_axis("horizontal", positive="RIGHT", negative="LEFT")

        # Física
        PhysicsWorld.set_gravity(0, 900)
        PhysicsWorld.set_cell_size(64)   # spatial hash tunado para tiles de 32 px

        # Entidades
        self.jogador = Jogador()
        self.plataformas = SpriteGroup()
        self.plataformas.add(
            Plataforma(400, 420, 800, 40),
            Plataforma(200, 320, 120),
            Plataforma(450, 240, 120),
            Plataforma(650, 160, 120),
        )

        # Câmera
        Camera.follow(self.jogador, smooth=0.1)
        Camera.set_world_bounds(0, 0, 800, 450)

        # Save — carrega pontuação anterior
        Save.set_path("saves/")
        Save.set_defaults({"pontuacao": 0, "recorde": 0})
        Save.load()
        self.pontos = Save.get("pontuacao")
        Save.auto_save(interval=30.0)   # auto-save a cada 30 s

        # Timer de pontuação
        Timer.every(1.0, self._adicionar_pontos)

    def _adicionar_pontos(self):
        self.pontos += 10
        Save.set("pontuacao", self.pontos)

    @Game.update
    def atualizar(self, dt):
        Save.tick(dt)   # necessário para o auto-save funcionar
        self.jogador._dispatch("update", dt)
        self.plataformas.update(dt)

    @Game.layer("mundo", order=0)
    def desenhar_mundo(self, screen):
        screen.fill((30, 30, 50))
        self.plataformas.draw(screen, Camera.offset)
        self.jogador._dispatch("draw", screen)

    @Game.layer("ui", order=1)
    def desenhar_ui(self, screen):
        import pygame
        font = pygame.font.SysFont(None, 32)
        texto = font.render(f"Pontos: {self.pontos}", True, (255, 255, 100))
        screen.blit(texto, (10, 10))

    @Game.on_pause
    def pausado(self):
        Timer.pause()   # congela os timers enquanto pausado

    @Game.on_resume
    def despausado(self):
        Timer.resume()

    @Game.stop
    def ao_fechar(self):
        # Atualiza recorde e persiste tudo antes de sair
        if self.pontos > Save.get("recorde"):
            Save.set("recorde", self.pontos)
        Save.commit()


if __name__ == "__main__":
    MeuJogo().run()
```

---

## Referência Rápida de Atalhos de Teclado

| Tecla | Ação |
|---|---|
| `F3` | Ativa/desativa o debug overlay |
| `ESC` | Pausa/despausa o jogo |

---

## Dicas de Performance

- Use `SpriteGroup.purge_destroyed()` periodicamente para remover entidades inativas da memória.
- Chame `Assets.preload(...)` na tela de carregamento para evitar travadas durante o jogo.
- Prefira `magnitude_squared` em vez de `magnitude` para comparações de distância (evita a raiz quadrada).
- Tiles fora da tela são culled automaticamente pelo `TileMap.draw()` — não é necessário filtrar manualmente.
- Corpos com velocidade próxima de zero entram em "sleep" automaticamente, economizando CPU.
- Para debug de física, use `PhysicsWorld.draw_debug(screen, Camera.offset)` temporariamente.
- Ajuste `PhysicsWorld.set_cell_size()` para o tamanho médio dos seus colisores — célula ≈ 2× a dimensão do maior colisador para menor número de testes desnecessários.
- `ParticleSystem` usa pool fixo: a alocação acontece apenas uma vez em `configure()`. Para emissores que mudam de `count` frequentemente, prefira um pool grande e ajuste `emit_rate` em vez de reconfigurar `count`.
- `Save.commit()` faz I/O de disco — não chame a cada frame. Use `auto_save(interval=N)` + `Save.tick(dt)` para persistência periódica sem impacto no FPS.
- Ao pausar o jogo, chame `Timer.pause()` para congelar timers junto com a simulação.

---

*Documentação gerada para nestifypy.pyunix — baseada no código-fonte dos módulos `app`, `sprite`, `physics`, `camera`, `assets`, `animation`, `audio`, `particles`, `tween`, `scene`, `timer`, `events`, `tilemap`, `text`, `math`, `window`, `transform`, `input`, `fonts` e `save`.*
