#!/usr/bin/env python3
"""
Pokémon Red IA — local com moondream (Ollama).
O jogo nunca para: IA roda em background e o emulador age com a decisão mais recente.
"""

import io
import re
import sys
import threading
from pathlib import Path
from queue import Empty, Queue

try:
    from pyboy import PyBoy
except ImportError:
    print("Faltando PyBoy. Execute: pip install pyboy")
    sys.exit(1)

try:
    import ollama
except ImportError:
    print("Faltando ollama. Execute: pip install ollama")
    sys.exit(1)

try:
    import pyttsx3
except ImportError:
    print("Faltando pyttsx3. Execute: pip install pyttsx3")
    sys.exit(1)

# ─── Configuração ─────────────────────────────────────────────────────────────

ROM_PATH     = "pokemon_red.gb"
MODELO       = "moondream"   # ollama pull moondream  (~1.6 GB, roda em CPU)
FRAMES_CHECK = 30            # aplica decisão a cada 30 frames (~0.5s a 60fps)

# Prompt em inglês: modelos pequenos obedecem melhor. Fala em PT-BR fica no SPEECH.
PROMPT = """You are an enthusiastic Pokémon Red player streaming live, narrating in Brazilian Portuguese.
Look at the Game Boy screen and respond with EXACTLY two lines, nothing else:
ACTION: [one of: A B UP DOWN LEFT RIGHT START SELECT NADA]
SPEECH: [1 short excited sentence in Portuguese about what you see and decide]

Button guide:
- A      = confirm / talk / attack / advance text
- B      = cancel / back / run from battle
- START  = open menu
- Arrows = move or navigate menus
- NADA   = wait (loading screen, animation, cut-scene)"""

MAPA_BOTOES = {
    "A":"a", "B":"b",
    "UP":"up", "DOWN":"down", "LEFT":"left", "RIGHT":"right",
    "START":"start", "SELECT":"select",
    "NADA": None,
}

# ─── Narrador ─────────────────────────────────────────────────────────────────

class Narrador:
    def __init__(self):
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', 155)
        self._lock = threading.Lock()
        for v in self.engine.getProperty('voices'):
            if 'pt' in (v.name + v.id).lower():
                self.engine.setProperty('voice', v.id)
                break

    def falar(self, texto: str):
        threading.Thread(target=self._sync, args=(texto,), daemon=True).start()

    def _sync(self, texto: str):
        with self._lock:
            self.engine.say(texto)
            self.engine.runAndWait()

# ─── IA ───────────────────────────────────────────────────────────────────────

class PokemonIA:
    def __init__(self, rom: str):
        print("[1/2] Iniciando emulador...")
        self.pb = self._criar_emulador(rom)

        print("[2/2] Iniciando narrador...")
        self.narrador = Narrador()

        self.fila: Queue = Queue(maxsize=1)
        self.rodando = True
        self.n = 0

    # Compatível com PyBoy 1.x e 2.x
    def _criar_emulador(self, rom: str):
        for kw in [{"window_type": "SDL2"}, {"window": "SDL2"}, {}]:
            try:
                return PyBoy(rom, **kw)
            except TypeError:
                continue
        raise RuntimeError("Não foi possível criar o emulador PyBoy.")

    def _capturar_tela(self):
        try:
            img = self.pb.screen.image           # PyBoy 2.x
        except AttributeError:
            img = self.pb.botsupport_manager().screen().screen_image()  # PyBoy 1.x
        return img.resize((480, 432))            # escala 3x para o modelo ver melhor

    def _img_bytes(self, img) -> bytes:
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()

    def _parsear(self, texto: str):
        """Extrai ACTION e SPEECH do texto do modelo."""
        acao = "NADA"
        fala = ""
        for linha in texto.strip().splitlines():
            upper = linha.upper()
            if upper.startswith("ACTION:"):
                token = linha.split(":", 1)[1].strip().upper()
                if token in MAPA_BOTOES:
                    acao = token
            elif upper.startswith("SPEECH:"):
                fala = linha.split(":", 1)[1].strip()
        # Fallback: procura o primeiro botão mencionado
        if acao == "NADA" and fala == "":
            m = re.search(r'\b(A|B|UP|DOWN|LEFT|RIGHT|START|SELECT|NADA)\b', texto.upper())
            if m:
                acao = m.group(1)
        return acao, fala

    def _pressionar(self, acao: str):
        botao = MAPA_BOTOES.get(acao)
        if not botao:
            return
        try:
            self.pb.button(botao)               # PyBoy 2.x
        except AttributeError:
            from pyboy import WindowEvent       # PyBoy 1.x
            ev = {
                'a':      (WindowEvent.PRESS_BUTTON_A,      WindowEvent.RELEASE_BUTTON_A),
                'b':      (WindowEvent.PRESS_BUTTON_B,      WindowEvent.RELEASE_BUTTON_B),
                'up':     (WindowEvent.PRESS_ARROW_UP,      WindowEvent.RELEASE_ARROW_UP),
                'down':   (WindowEvent.PRESS_ARROW_DOWN,    WindowEvent.RELEASE_ARROW_DOWN),
                'left':   (WindowEvent.PRESS_ARROW_LEFT,    WindowEvent.RELEASE_ARROW_LEFT),
                'right':  (WindowEvent.PRESS_ARROW_RIGHT,   WindowEvent.RELEASE_ARROW_RIGHT),
                'start':  (WindowEvent.PRESS_BUTTON_START,  WindowEvent.RELEASE_BUTTON_START),
                'select': (WindowEvent.PRESS_BUTTON_SELECT, WindowEvent.RELEASE_BUTTON_SELECT),
            }
            if botao in ev:
                p, r = ev[botao]
                self.pb.send_input(p)
                self.pb.tick(6)
                self.pb.send_input(r)

    # ── Thread da IA (roda em paralelo ao emulador) ────────────────────────────

    def _ai_loop(self):
        while self.rodando:
            try:
                img = self._capturar_tela()
                resp = ollama.generate(
                    model=MODELO,
                    prompt=PROMPT,
                    images=[self._img_bytes(img)],
                    options={"temperature": 0.4, "num_predict": 60},
                )
                acao, fala = self._parsear(resp["response"])

                # Descarta decisão anterior não consumida e coloca a nova
                try:
                    self.fila.get_nowait()
                except Empty:
                    pass
                self.fila.put((acao, fala))

            except Exception as e:
                print(f"[IA] Erro: {e}")

    # ── Game loop principal ────────────────────────────────────────────────────

    def rodar(self):
        print("\n=== Pokémon IA rodando! Feche a janela do emulador para sair. ===")
        print("    (A IA começa a agir em alguns segundos enquanto o modelo carrega)\n")

        threading.Thread(target=self._ai_loop, daemon=True).start()

        try:
            while self.pb.tick(FRAMES_CHECK, render=True):
                try:
                    acao, fala = self.fila.get_nowait()
                    self.n += 1
                    print(f"#{self.n:04d}  [{acao:8s}]  {fala}")
                    self._pressionar(acao)
                    if fala:
                        self.narrador.falar(fala)
                except Empty:
                    pass  # IA ainda processando — emulador continua rodando normalmente
        except KeyboardInterrupt:
            print("\nInterrompido.")
        finally:
            self.rodando = False
            self.pb.stop()
            print("Fim de jogo!")

# ─── Ponto de entrada ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    rom = sys.argv[1] if len(sys.argv) > 1 else ROM_PATH

    if not Path(rom).exists():
        print(f"\nERRO: ROM não encontrada: '{rom}'")
        print("Uso: python pokemon_ai.py caminho\\para\\pokemon_red.gb\n")
        sys.exit(1)

    PokemonIA(rom).rodar()
