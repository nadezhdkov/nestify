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