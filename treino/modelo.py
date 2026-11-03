import torch, torch.nn as nn, numpy as np

R, T = 128, 32

def entrada(B, G):
    """B: (N,R,T,3) uint8 bloco do gancho; G: (N,R,3) uint8 fundo calibrado -> (N,7,R,T) float32"""
    b = B.astype(np.float32) / 255
    g = np.repeat(G[:, :, None, :], b.shape[2], axis=2).astype(np.float32) / 255
    d = np.abs(b - g).max(axis=3, keepdims=True)
    x = np.concatenate([b, g, d], axis=3)            # N,R,T,7
    return np.ascontiguousarray(x.transpose(0, 3, 1, 2))

class Rede(nn.Module):
    """Olha o bloco do gancho e diz, linha por linha da altura, se é PEÇA ou ESPAÇO."""
    def __init__(s, c=24):
        super().__init__()
        def bl(i, o, st): return [nn.Conv2d(i, o, 3, padding=1, stride=st), nn.BatchNorm2d(o), nn.ReLU()]
        s.enc = nn.Sequential(*bl(7, c, 1), *bl(c, c, (1, 2)), *bl(c, 2 * c, (1, 2)), *bl(2 * c, 2 * c, (1, 2)))
        s.cab = nn.Sequential(nn.Conv1d(4 * c, 64, 5, padding=2), nn.ReLU(),
                              nn.Conv1d(64, 64, 5, padding=4, dilation=2), nn.ReLU(),
                              nn.Conv1d(64, 64, 5, padding=8, dilation=4), nn.ReLU(),
                              nn.Conv1d(64, 1, 1))
    def forward(s, x):
        f = s.enc(x)                                       # N,2c,R,T/8
        f = torch.cat([f.mean(3), f.amax(3)], 1)           # N,4c,R
        return s.cab(f)[:, 0]                              # N,R (logit de "peça")

def contar(p, lim=0.5, minimo=4):
    n, c = 0, 0
    for v in list(p > lim) + [False]:
        if v: c += 1
        else:
            if c >= minimo: n += 1
            c = 0
    return n
