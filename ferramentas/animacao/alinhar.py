"""Alinha um áudio narrado ao seu roteiro: quando começa e termina cada fala, quem fala, e o tempo de
cada palavra (para a legenda karaokê). Serve para qualquer história do motor de animação.

Roteiro no formato do Estúdio (uma fala por marcação):
    [narra:curiosidade] Chapeuzinho Vermelho era uma linda menina...
    [lobo:neutra] Bom dia, Chapeuzinho Vermelho.

    F:\\Projeto IA\\.venv_omni\\Scripts\\python.exe alinhar.py ROTEIRO.txt AUDIO.wav SAIDA.json

Como: o faster-whisper transcreve com tempo por palavra; as palavras do ROTEIRO (grafia certa) são
casadas com as reconhecidas (difflib), e as que o reconhecedor errou herdam o tempo por interpolação.
"""
import difflib, json, re, sys, unicodedata
from pathlib import Path


def ler_roteiro(caminho):
    t = Path(caminho).read_text(encoding="utf-8")
    partes = re.split(r"\[([\w:]+)\]", t)
    falas = []
    for i in range(1, len(partes) - 1, 2):
        texto = " ".join(partes[i + 1].split())
        if texto:
            quem, _, emo = partes[i].partition(":")
            falas.append({"quem": quem, "emocao": emo or "neutra", "texto": texto})
    return falas


def norm(p):
    p = unicodedata.normalize("NFD", p.lower())
    return "".join(c for c in p if c.isalnum() and not unicodedata.combining(c))


def transcrever(audio, modelo="base"):
    from faster_whisper import WhisperModel
    m = WhisperModel(modelo, device="cpu", compute_type="int8")
    segs, _ = m.transcribe(str(audio), language="pt", word_timestamps=True, vad_filter=False)
    return [(w.word.strip(), w.start, w.end) for s in segs for w in s.words if norm(w.word)]


def alinhar(falas, reconhecidas):
    # palavras do roteiro, com a fala a que pertencem
    rot = [(k, p) for k, f in enumerate(falas) for p in f["texto"].split() if norm(p)]
    a, b = [norm(p) for _, p in rot], [norm(w[0]) for w in reconhecidas]
    t0, t1 = [None] * len(rot), [None] * len(rot)
    for bl in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for j in range(bl.size):
            t0[bl.a + j], t1[bl.a + j] = reconhecidas[bl.b + j][1], reconhecidas[bl.b + j][2]
    casadas = sum(x is not None for x in t0)
    # interpola os tempos das palavras que o reconhecedor errou (proporcional ao tamanho da palavra)
    idx = [i for i, x in enumerate(t0) if x is not None]
    for i in range(len(rot)):
        if t0[i] is None:
            ant = max([j for j in idx if j < i], default=None)
            pos = min([j for j in idx if j > i], default=None)
            ini = t1[ant] if ant is not None else 0.0
            fim = t0[pos] if pos is not None else ini + 0.4 * (len(rot) - i)
            buraco = list(range((ant if ant is not None else -1) + 1, pos if pos is not None else len(rot)))
            pesos = [len(a[j]) + 1 for j in buraco]
            acum = sum(pesos[:buraco.index(i)])
            passo = (fim - ini) / max(sum(pesos), 1)
            t0[i], t1[i] = ini + acum * passo, ini + (acum + pesos[buraco.index(i)]) * passo
    saida = []
    for k, f in enumerate(falas):
        ws = [{"w": rot[i][1], "t0": round(t0[i], 3), "t1": round(t1[i], 3)} for i in range(len(rot)) if rot[i][0] == k]
        saida.append({**f, "inicio": ws[0]["t0"], "fim": ws[-1]["t1"], "palavras": ws})
    return saida, casadas / max(len(rot), 1)


def main():
    roteiro, audio, destino = sys.argv[1:4]
    falas = ler_roteiro(roteiro)
    rec = transcrever(audio)
    linha, cobertura = alinhar(falas, rec)
    import soundfile as sf
    dur = sf.info(str(audio)).duration
    Path(destino).write_text(json.dumps({"audio": str(Path(audio).resolve()), "duracao": round(dur, 3),
                                         "cobertura": round(cobertura, 3), "falas": linha},
                                        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(linha)} falas alinhadas; {cobertura:.0%} das palavras casaram com o reconhecimento; {dur:.1f} s")


if __name__ == "__main__":
    main()
