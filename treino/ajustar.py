# escolhe os limites da contagem (pós-processamento) SEM olhar o teste: usa sintético novo + ganchos reais de treino
import numpy as np, torch, sys, itertools
from modelo import Rede, entrada
sys.path.insert(0, '/home/claude/monovia-visao')
def segmentos(p, lim):
    r=[];s=None
    for i,v in enumerate(p>lim):
        if v and s is None: s=i
        if not v and s is not None: r.append([s,i]);s=None
    if s is not None: r.append([s,len(p)])
    return r
def contar2(p, lim=0.5, min_peca=4, min_gap=1, gap_conf=1.0, borda=0):
    seg = segmentos(p, lim); out = []
    for s in seg:
        if out:
            a, b = out[-1][1], s[0]                     # espaço entre o anterior e este
            if b - a < min_gap or p[a:b].min() > gap_conf: out[-1][1] = s[1]; continue
        out.append(s)
    n = len(p)   # pedaço curto encostado na borda da faixa calibrada não é peça
    return sum(1 for s, e in out if e - s >= min_peca and not (borda and (s <= 2 or e >= n - 2) and e - s < borda))
if __name__ == '__main__':
    net = Rede(); net.load_state_dict(torch.load(sys.argv[1])); net.eval()
    def prob(f):
        d = np.load(f)
        with torch.no_grad(): return torch.sigmoid(net(torch.from_numpy(entrada(d['B'], d['G'])))).numpy(), d['K']
    conj = {f: prob(f) for f in ('ajuste_a.npz', 'ajuste_c.npz', 'real_treino2_ok.npz')}
    teste = {f: prob(f) for f in ('teste_real2_ok.npz', 'teste_real_sb_sep_ok.npz')}
    res = []
    for lim, mp, mg, gc, bd in itertools.product((0.4, 0.5, 0.6), (4, 6), (1, 2, 3), (1.0,), (0, 8, 12, 16)):
        acc = [np.mean([contar2(x, lim, mp, mg, gc, bd) == k for x, k in zip(*conj[f])]) for f in conj]
        res.append((np.mean(acc), acc, (lim, mp, mg, gc, bd)))
    res.sort(key=lambda r: -r[0])
    padrao = [r for r in res if r[2] == (0.5, 4, 1, 1.0, 0)][0]
    print('padrão  ', np.round(padrao[1], 3), padrao[2])
    for r in res[:5]: print('melhores', np.round(r[1], 3), r[2])
    best = res[0][2]
    for f, (p, K) in teste.items():
        a = np.mean([contar2(x, *padrao[2]) == k for x, k in zip(p, K)]); b = np.mean([contar2(x, *best) == k for x, k in zip(p, K)])
        print(f'TESTE {f}: padrão {a:.3f} -> ajustado {b:.3f}  ({int(round(b * len(K)))}/{len(K)})')
