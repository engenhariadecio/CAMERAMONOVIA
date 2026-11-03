"""
Núcleo do contador da monovia (linha de pixels).
Recebe, a cada quadro, a coluna de pixels que o celular manda e devolve eventos:
  TROLE (velocidade), GANCHO (empilhamento), PARADA_INICIO / PARADA_FIM.
Não depende de banco nem de rede: dá para testar sozinho.
"""
import numpy as np, os, io
from collections import deque
from PIL import Image

R, T = 128, 32

def _resize(a, w, h):
    """redimensiona array float (alt x larg x 3) por média de área"""
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return np.asarray(im.resize((w, h), Image.BOX))

def preparar(bloco, fundo):
    """bloco: (tempo, linhas, 3); fundo: (linhas, 3) -> (B 128x32x3 uint8, G 128x3 uint8)"""
    b = _resize(np.asarray(bloco, np.float32).transpose(1, 0, 2), T, R)
    g = _resize(np.asarray(fundo, np.float32)[:, None, :], 1, R)[:, 0]
    return b, g

def entrada(B, G):
    b = B.astype(np.float32) / 255
    g = np.repeat(G[:, :, None, :], b.shape[2], axis=2).astype(np.float32) / 255
    d = np.abs(b - g).max(axis=3, keepdims=True)
    return np.ascontiguousarray(np.concatenate([b, g, d], axis=3).transpose(0, 3, 1, 2))

def runs(b):
    r, s = [], None
    for i, v in enumerate(b):
        if v and s is None: s = i
        if not v and s is not None: r.append((s, i)); s = None
    if s is not None: r.append((s, len(b)))
    return r

def contar_mascara(p, lim=0.5, minimo=4):
    return len([1 for s, e in runs(np.asarray(p) > lim) if e - s >= minimo])

class Modelo:
    def __init__(self, caminho):
        self.ok = False
        try:
            import onnxruntime as ort
            if os.path.exists(caminho):
                self.s = ort.InferenceSession(caminho, providers=['CPUExecutionProvider']); self.ok = True
        except Exception as e:
            print('modelo não carregado:', e)
    def prever(self, B, G):
        z = self.s.run(None, {'x': entrada(B[None], G[None])})[0][0]
        return 1 / (1 + np.exp(-z))

def png_gancho(B, G):
    """guarda o bloco do gancho como PNG 33x128: coluna 0 = fundo, 1..32 = bloco"""
    img = np.concatenate([G[:, None, :], B], axis=1)
    buf = io.BytesIO(); Image.fromarray(img).save(buf, 'PNG'); return buf.getvalue()

def ler_png_gancho(png):
    a = np.asarray(Image.open(io.BytesIO(png)).convert('RGB'))
    return a[:, 1:], a[:, 0]

def regra(B, G, th=20):
    """contagem sem IA (só diferença para o fundo) - usada como conferência"""
    d = np.abs(B.astype(np.float32) - G[:, None].astype(np.float32)).max(2)
    prof = np.median(d, axis=1) > th
    k = 3
    m = prof.copy()
    for i in range(len(prof)):                                     # fecha furinhos de 1-2 linhas
        if not prof[i] and prof[max(0, i - k):i].any() and prof[i + 1:i + 1 + k].any(): m[i] = True
    return len([1 for s, e in runs(m) if e - s >= 4])

class Contador:
    def __init__(self, cfg, modelo=None):
        self.modelo = modelo
        self.cfg = cfg                    # x, y0, y1, ry, ya (linha inicial do recorte enviado), passo, th
        self.fundo = None; self.fundo_trilho = None
        self.coletando = None; self.buf_fundo = []
        self.reset_estado()

    def reset_estado(self):
        self.gancho = None; self.ausente = None
        self.trole_escuro = False; self.ult_trole = None; self.intervalos = deque(maxlen=10)
        self.mov_hist = deque(maxlen=1200); self.mov_lim = 0.02; self.mov = 1.0
        self.desloc = 0; self.est_desloc = deque(maxlen=5); self.prox_desloc = 0; self.desloc_mudou = -99
        self.parado_desde = None; self.em_parada = False

    # ---- fundo ----
    def iniciar_fundo(self, t):
        self.coletando = t; self.buf_fundo = []

    def definir_fundo(self, fundo, fundo_trilho):
        self.fundo = np.asarray(fundo, np.float32); self.fundo_trilho = float(fundo_trilho)
        self.desloc = 0; self.est_desloc.clear()

    def _medir_desloc(self, col, y0):
        """a câmera escorregou? compara a parte de cima (trilho/estrutura) com o fundo, em -12..12 px"""
        a = col[:max(20, y0 - 5)].mean(1); b = self.fundo[:max(20, y0 - 5)].mean(1); m = 12
        if len(a) < 2 * m + 10: return
        erros = [np.abs(a[m:-m] - b[m - d:len(b) - m - d]).mean() for d in range(-m, m + 1)]
        self.est_desloc.append(int(np.argmin(erros)) - m)
        if len(self.est_desloc) >= 3:
            novo = int(np.median(list(self.est_desloc)[-3:]))
            if abs(novo - self.desloc) >= 2:                     # tranco da câmera
                self.desloc_mudou = self._t
                if self.gancho is not None and self._t - self.gancho['t0'] < 8: self.gancho = None   # era o tranco, não peça
            self.desloc = novo

    def velocidade(self):
        if not self.intervalos or not self.cfg.get('passo'): return None
        return self.cfg['passo'] / float(np.median(self.intervalos))

    def _rel(self, y):                      # linha do quadro -> linha do recorte enviado
        return int(y) - int(self.cfg.get('ya', 0))

    # ---- um quadro ----
    def quadro(self, t, col, mov):
        """t: segundos (relógio do celular); col: (linhas, 3) do recorte; mov: movimento (0-1) ou None"""
        ev = []
        col = np.asarray(col, np.float32)
        y0, y1, ry = self._rel(self.cfg['y0']), self._rel(self.cfg['y1']), self._rel(self.cfg['ry'])
        trilho = col[max(0, ry - 4):ry + 4].mean()

        # parada / funcionando
        if mov is not None:
            self.mov = mov
            if len(self.mov_hist) > 60: self.mov_lim = max(0.01, 0.35 * float(np.median(self.mov_hist)))
            if not self.em_parada and mov >= self.mov_lim: self.mov_hist.append(mov)
            if mov < self.mov_lim:
                if self.parado_desde is None: self.parado_desde = t - 1.0
                if not self.em_parada and t - self.parado_desde >= self.cfg.get('parada_min', 5):
                    self.em_parada = True; ev.append(('PARADA_INICIO', self.parado_desde, None, {}))
            else:
                if self.em_parada:
                    d = t - 1.0 - self.parado_desde
                    ev.append(('PARADA_FIM', t - 1.0, d, {'inicio_t': self.parado_desde}))
                self.em_parada = False; self.parado_desde = None

        # gravação do fundo (3 s com gancho vazio na linha)
        if self.coletando is not None:
            self.buf_fundo.append(col)
            if t - self.coletando >= 3:
                bf = np.array(self.buf_fundo)
                self.fundo = np.median(bf, axis=0)
                self.fundo_trilho = float(np.percentile(bf[:, max(0, ry - 4):ry + 4].mean(axis=(1, 2)), 80))
                self.coletando = None; self.buf_fundo = []
                self.gancho = None
                ev.append(('FUNDO_OK', t, None, {}))
            return ev
        if self.fundo is None or len(self.fundo) != len(col): return ev
        self._t = t
        if t >= self.prox_desloc:
            self.prox_desloc = t + 1; self._medir_desloc(col, y0)
        if self.desloc:                     # compensa: desloca o recorte de volta para a posição do fundo
            col = np.roll(col, -self.desloc, axis=0)
            trilho = col[max(0, ry - 4):ry + 4].mean()

        # trole -> velocidade
        escuro = self.fundo_trilho - trilho
        P = float(np.median(self.intervalos)) if self.intervalos else 2.0
        if not self.trole_escuro and escuro > 25 and not self.em_parada:
            if self.ult_trole is None or t - self.ult_trole > 0.6 * P:
                iv = None
                if self.ult_trole is not None:
                    iv = t - self.ult_trole
                    if not (len(self.intervalos) >= 3 and iv > 1.5 * P): self.intervalos.append(iv)
                self.trole_escuro = True; self.ult_trole = t
                ev.append(('TROLE', t, self.velocidade(), {'intervalo_s': iv}))
        elif self.trole_escuro and escuro < 12:
            self.trole_escuro = False

        # gancho (espaçamentos)
        th = self.cfg.get('th', 20)
        # diferença para o fundo com folga de ±2 px (a câmera sempre mexe um pouco): fica a menor das 5
        f = self.fundo
        diff = np.min([np.abs(col - np.roll(f, s, axis=0)).max(axis=1) for s in (-2, -1, 0, 1, 2)], axis=0)[y0:y1]
        if (diff > th + 8).mean() > self.cfg.get('ocupacao_min', 0.20):   # fração da altura que precisa mudar para abrir um gancho
            self.ausente = None
            if self.gancho is None:
                if t - self.desloc_mudou < 2: return ev          # câmera acabou de mexer: espera a correção assentar
                self.gancho = {'t0': t, 'cols': []}
            if len(self.gancho['cols']) < 4000: self.gancho['cols'].append(col[y0:y1].astype(np.uint8))
        elif self.gancho is not None:
            if self.ausente is None: self.ausente = t
            if t - self.ausente > 0.7:
                e = self._fechar(self.ausente)
                if e: ev.append(e)
        return ev

    def _fechar(self, t):
        g, self.gancho = self.gancho, None
        dur = t - g['t0']
        if dur < 0.5 or len(g['cols']) < 5: return None
        cols = np.array(g['cols'])
        if len(cols) > 12: cols = cols[2:-2]
        y0, y1 = self._rel(self.cfg['y0']), self._rel(self.cfg['y1'])
        B, G = preparar(cols, self.fundo[y0:y1])
        k_regra = regra(B, G, self.cfg.get('th', 20))
        if self.modelo is not None and self.modelo.ok:
            p = self.modelo.prever(B, G)
            k = contar_mascara(p)
            conf = float((np.abs(p - 0.5) > 0.3).mean())
        else:
            k, conf = k_regra, None
        return ('GANCHO', g['t0'], k, {'duracao_s': round(dur, 1), 'regra': k_regra, 'confianca': conf,
                                        'png': png_gancho(B, G)})
