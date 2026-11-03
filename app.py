"""
MONOVIA - VISÃO  (serviço do Railway)
  /camera   -> página que o celular abre: filma a monovia e manda a linha de pixels
  /         -> painel: peças, empilhamento, velocidade (m/s), funcionando/parada, conferência dos ganchos
  /api/resumo?dia=AAAA-MM-DD -> números do dia em JSON (para o Banho e Monovia ler)
Variáveis no Railway: DATABASE_URL (o mesmo Postgres do Banho e Monovia), MONOVIA_USUARIO e MONOVIA_SENHA (administrador),
MONOVIA_CHAVE_API (opcional: para o Banho e Monovia ler /api/resumo sem login).
"""
import os, io, json, time, struct, asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, Response, JSONResponse, RedirectResponse
from PIL import Image
import banco, acesso
from contador import Contador, Modelo, ler_png_gancho, runs

TZ = ZoneInfo(os.environ.get('FUSO', 'America/Sao_Paulo'))
DIAS_IMAGENS = int(os.environ.get('DIAS_IMAGENS', '30'))
AQUI = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title='Monovia - Visão')
banco.criar()
acesso.criar_tabela()
modelo = Modelo(os.path.join(AQUI, 'modelo_empilhamento.onnx'))
print('modelo de IA carregado:', modelo.ok)

def agora(): return datetime.now(TZ)
def fmt(dt): return dt.strftime('%Y-%m-%d %H:%M:%S')

# ---------------- estado ao vivo ----------------
class Estado:
    def __init__(s):
        s.cfg = banco.ler_config(); s.montar()
        s.conectado = False; s.ult_pacote = 0; s.pacotes = 0; s.fps = 0; s.off = None; s.t = 0
        s.ult_online = 0
    def montar(s):
        s.cont = Contador(s.cfg, modelo) if s.cfg.get('x') is not None else None
        if s.cont and s.cfg.get('fundo') is not None:
            s.cont.definir_fundo(np.array(s.cfg['fundo'], np.float32), s.cfg['fundo_trilho'])
E = Estado()

def logado(request: Request):
    u = acesso.ler_sessao(request.cookies.get(acesso.COOKIE))
    if not u: raise HTTPException(401, 'faça login')
    return u

def logado_ou_chave(request: Request):
    if acesso.chave_ok(request.headers.get('x-chave') or request.query_params.get('chave')): return {'usuario': 'api', 'admin': False}
    return logado(request)

def admin(request: Request):
    u = logado(request)
    if not u['admin']: raise HTTPException(403, 'só o administrador')
    return u

def dh_do_t(t):      # relógio do celular -> data/hora de Brasília
    return datetime.fromtimestamp(t + (E.off or 0), TZ)

def limpar_imagens():
    lim = fmt(agora() - timedelta(days=DIAS_IMAGENS))
    banco.q('UPDATE monovia_ganchos SET imagem=NULL WHERE datahora < ? AND rotulo IS NULL', (lim,))
limpar_imagens()

def gravar(ev):
    tipo, t, valor, det = ev
    dh = fmt(dh_do_t(t))
    if tipo == 'TROLE':
        banco.evento(dh, 'TROLE', valor, {'intervalo_s': round(det['intervalo_s'], 2) if det.get('intervalo_s') else None})
    elif tipo == 'GANCHO':
        banco.gancho(dh, det['duracao_s'], int(valor), int(det['regra']), det['confianca'], det['png'])
    elif tipo == 'PARADA_INICIO':
        banco.evento(dh, 'PARADA_INICIO')
    elif tipo == 'PARADA_FIM':
        banco.evento(fmt(dh_do_t(det['inicio_t'])), 'PARADA', round(valor, 1), {'fim': dh})
    elif tipo == 'FUNDO_OK':
        E.cfg['fundo'] = np.round(E.cont.fundo, 1).tolist(); E.cfg['fundo_trilho'] = E.cont.fundo_trilho
        E.cfg['fundo_em'] = dh; banco.salvar_config(E.cfg)
        banco.evento(dh, 'FUNDO_GRAVADO')

# ---------------- páginas ----------------
def pagina(nome):
    return HTMLResponse(open(os.path.join(AQUI, 'static', nome), encoding='utf-8').read())

def _pagina_logada(request, nome, caminho):
    if not acesso.ler_sessao(request.cookies.get(acesso.COOKIE)):
        return RedirectResponse('/entrar?prox=' + caminho, 303)
    return pagina(nome)

@app.get('/', response_class=HTMLResponse)
def painel(request: Request): return _pagina_logada(request, 'painel.html', '/')

@app.get('/camera', response_class=HTMLResponse)
def camera(request: Request): return _pagina_logada(request, 'camera.html', '/camera')

@app.get('/entrar', response_class=HTMLResponse)
def entrar_pagina(): return pagina('entrar.html')

@app.post('/api/entrar')
async def entrar(request: Request):
    ip = request.headers.get('x-forwarded-for', request.client.host if request.client else '?').split(',')[0].strip()
    if acesso.bloqueado(ip): raise HTTPException(429, 'Muitas tentativas. Espere 10 minutos.')
    d = await request.json()
    u = acesso.conferir(d.get('usuario', ''), d.get('senha', ''))
    if not u:
        acesso.errou(ip); raise HTTPException(401, 'Usuário ou senha errados.')
    r = JSONResponse({'ok': True, 'usuario': u['usuario']})
    https = request.headers.get('x-forwarded-proto', request.url.scheme) == 'https'
    r.set_cookie(acesso.COOKIE, acesso.criar_sessao(u['usuario']), max_age=acesso.DIAS_SESSAO * 86400,
                 httponly=True, secure=https, samesite='lax')
    return r

@app.get('/sair')
def sair():
    r = RedirectResponse('/entrar', 303); r.delete_cookie(acesso.COOKIE); return r

@app.get('/api/eu')
def eu(u=Depends(logado)): return u

@app.get('/api/usuarios')
def usuarios(u=Depends(admin)): return acesso.listar()

@app.post('/api/usuarios')
async def usuarios_salvar(request: Request, u=Depends(admin)):
    d = await request.json()
    nome, senha = (d.get('usuario') or '').strip().lower(), d.get('senha') or ''
    if len(nome) < 3 or len(senha) < 6: raise HTTPException(400, 'usuário com 3+ letras e senha com 6+ caracteres')
    acesso.salvar_usuario(nome, senha, bool(d.get('admin')))
    return acesso.listar()

@app.delete('/api/usuarios/{nome}')
def usuarios_apagar(nome: str, u=Depends(admin)):
    if nome.strip().lower() == u['usuario']: raise HTTPException(400, 'não dá para apagar o próprio usuário')
    acesso.apagar_usuario(nome); return acesso.listar()

# ---------------- configuração ----------------
CAMPOS = ('x', 'y0', 'y1', 'ry', 'w', 'h', 'passo', 'parada_min', 'th', 'ocupacao_min')

@app.get('/api/config')
def get_config(u=Depends(logado)):
    c = {kk: E.cfg.get(kk) for kk in CAMPOS}
    c['fundo_ok'] = E.cfg.get('fundo') is not None; c['fundo_em'] = E.cfg.get('fundo_em')
    c['ya'] = E.cfg.get('ya'); c['yb'] = E.cfg.get('yb'); c['modelo_ia'] = modelo.ok
    return c

@app.post('/api/config')
async def post_config(req: Request, u=Depends(logado)):
    d = await req.json()
    geom = any(kk in d and d[kk] != E.cfg.get(kk) for kk in ('x', 'y0', 'y1', 'ry', 'w', 'h'))
    for kk in CAMPOS:
        if kk in d and d[kk] is not None: E.cfg[kk] = float(d[kk]) if kk in ('passo', 'parada_min', 'th', 'ocupacao_min') else int(d[kk])
    if E.cfg.get('x') is not None:
        E.cfg['y0'], E.cfg['y1'] = sorted((E.cfg['y0'], E.cfg['y1']))
        E.cfg['ya'] = max(0, min(E.cfg['ry'], E.cfg['y0']) - 30)
        E.cfg['yb'] = min(E.cfg.get('h') or 10 ** 5, E.cfg['y1'] + 30)
    if geom:                                            # mudou a posição da linha: precisa gravar o fundo de novo
        for kk in ('fundo', 'fundo_trilho', 'fundo_em'): E.cfg.pop(kk, None)
        E.montar()
    elif E.cont: E.cont.cfg = E.cfg
    else: E.montar()
    banco.salvar_config(E.cfg)
    return get_config(u)

# ---------------- câmera (celular) ----------------
@app.websocket('/ws/camera')
async def ws_camera(ws: WebSocket):
    if not (acesso.ler_sessao(ws.cookies.get(acesso.COOKIE)) or acesso.chave_ok(ws.query_params.get('chave'))):
        await ws.close(code=4001); return
    await ws.accept()
    E.conectado = True; E.off = None; banco.evento(fmt(agora()), 'CAMERA_CONECTADA')
    ult_envio = 0; cont_fps = 0; t_fps = time.time()
    try:
        while True:
            msg = await ws.receive()
            if msg.get('type') == 'websocket.disconnect': break
            if msg.get('text'):
                d = json.loads(msg['text'])
                if d.get('tipo') == 'fundo' and E.cont: E.cont.iniciar_fundo(E.t)
                continue
            b = msg.get('bytes')
            if not b or len(b) < 16 or E.cont is None: continue
            t_ms, mov, ya, n = struct.unpack('<dfHH', b[:16])
            if len(b) < 16 + n * 3: continue
            col = np.frombuffer(b[16:16 + n * 3], np.uint8).reshape(n, 3)
            t = t_ms / 1000; E.t = t
            if E.off is None: E.off = time.time() - t
            E.cont.cfg['ya'] = ya
            for ev in E.cont.quadro(t, col, None if mov < 0 else float(mov)):
                gravar(ev)
            E.ult_pacote = time.time(); cont_fps += 1
            if time.time() - t_fps >= 2: E.fps = cont_fps / (time.time() - t_fps); cont_fps = 0; t_fps = time.time()
            if time.time() - E.ult_online >= 60:          # "batimento": minutos com câmera funcionando
                banco.evento(fmt(agora()), 'ONLINE'); E.ult_online = time.time()
            if time.time() - ult_envio > 1:
                ult_envio = time.time()
                r = resumo_dia(agora().strftime('%Y-%m-%d'))
                await ws.send_text(json.dumps({'pecas': r['pecas'], 'ganchos': r['ganchos'], 'vel': velocidade_atual(),
                                               'parada': E.cont.em_parada, 'fundo_ok': E.cont.fundo is not None,
                                               'gravando_fundo': E.cont.coletando is not None, 'fps': round(E.fps, 1),
                                               'mexeu': int(abs(E.cont.desloc))}))
    except WebSocketDisconnect:
        pass
    finally:
        E.conectado = False
        if E.cont:
            if E.cont.em_parada and E.cont.parado_desde is not None:       # fecha a parada que estava aberta
                try: gravar(('PARADA_FIM', E.t, E.t - E.cont.parado_desde, {'inicio_t': E.cont.parado_desde}))
                except Exception as e: print('erro ao fechar parada:', e)
            E.cont.reset_estado()                                         # mantém o fundo, zera o resto
        banco.evento(fmt(agora()), 'CAMERA_DESCONECTADA')

def velocidade_atual():
    if not E.cont or not E.conectado: return None
    v = E.cont.velocidade()
    return round(v, 4) if v else None

# ---------------- números ----------------
def resumo_dia(dia):
    a, b = dia + ' 00:00:00', dia + ' 23:59:59'
    r = banco.q('SELECT COUNT(*), COALESCE(SUM(COALESCE(rotulo, empilhamento)),0) FROM monovia_ganchos '
                'WHERE datahora BETWEEN ? AND ? AND COALESCE(rotulo, empilhamento) > 0', (a, b), um=True)
    v = banco.q("SELECT AVG(valor), COUNT(*) FROM monovia_eventos WHERE tipo='TROLE' AND datahora BETWEEN ? AND ?", (a, b), um=True)
    par = banco.q("SELECT datahora, valor, detalhe FROM monovia_eventos WHERE tipo='PARADA' AND datahora BETWEEN ? AND ? ORDER BY datahora", (a, b), todos=True)
    onl = banco.q("SELECT COUNT(DISTINCT SUBSTR(datahora,1,16)) FROM monovia_eventos WHERE tipo='ONLINE' AND datahora BETWEEN ? AND ?", (a, b), um=True)[0]
    parado = sum(p[1] or 0 for p in par)
    hoje = dia == agora().strftime('%Y-%m-%d')
    if hoje and E.cont and E.cont.em_parada and E.conectado: parado += E.t - E.cont.parado_desde
    online = onl * 60
    hora = banco.q('SELECT SUBSTR(datahora,12,2), SUM(COALESCE(rotulo, empilhamento)), COUNT(*) FROM monovia_ganchos '
                   'WHERE datahora BETWEEN ? AND ? AND COALESCE(rotulo, empilhamento) > 0 GROUP BY 1 ORDER BY 1', (a, b), todos=True)
    emp = banco.q('SELECT COALESCE(rotulo, empilhamento), COUNT(*) FROM monovia_ganchos WHERE datahora BETWEEN ? AND ? GROUP BY 1 ORDER BY 1',
                  (a, b), todos=True)
    return dict(dia=dia, pecas=int(r[1]), ganchos=int(r[0]),
                velocidade_media_m_s=round(v[0], 4) if v[0] else None, troles=int(v[1]),
                tempo_camera_s=online, tempo_parado_s=round(parado), tempo_funcionando_s=max(0, round(online - parado)),
                paradas=[dict(inicio=p[0], duracao_s=p[1], fim=json.loads(p[2]).get('fim') if p[2] else None) for p in par],
                por_hora=[dict(hora=h[0], pecas=int(h[1]), ganchos=int(h[2])) for h in hora],
                empilhamento=[dict(pecas=int(e[0]), ganchos=int(e[1])) for e in emp])

@app.get('/api/resumo')
def api_resumo(dia: str = '', u=Depends(logado_ou_chave)):
    return resumo_dia(dia or agora().strftime('%Y-%m-%d'))

@app.get('/api/status')
def api_status(u=Depends(logado)):
    c = E.cont
    return dict(conectado=E.conectado and time.time() - E.ult_pacote < 10, fps=round(E.fps, 1),
                calibrado=c is not None, fundo_ok=bool(c and c.fundo is not None), fundo_em=E.cfg.get('fundo_em'),
                gravando_fundo=bool(c and c.coletando is not None),
                parada=bool(c and c.em_parada), velocidade_m_s=velocidade_atual(),
                intervalo_troles_s=round(float(np.median(c.intervalos)), 2) if c and c.intervalos else None,
                camera_mexeu_px=int(abs(c.desloc)) if c else 0,
                passo=E.cfg.get('passo'), modelo_ia=modelo.ok, usuario=u['usuario'], admin=u['admin'], hoje=resumo_dia(agora().strftime('%Y-%m-%d')))

@app.get('/api/ganchos')
def api_ganchos(dia: str = '', limite: int = 60, so_duvida: int = 0, u=Depends(logado)):
    dia = dia or agora().strftime('%Y-%m-%d')
    extra = ' AND (confianca < 0.9 OR empilhamento <> empilhamento_regra)' if so_duvida else ''
    rows = banco.q('SELECT id, datahora, duracao_s, empilhamento, empilhamento_regra, confianca, rotulo, imagem IS NOT NULL '
                   f'FROM monovia_ganchos WHERE datahora BETWEEN ? AND ?{extra} ORDER BY id DESC LIMIT ?',
                   (dia + ' 00:00:00', dia + ' 23:59:59', limite), todos=True)
    return [dict(id=r[0], datahora=r[1], duracao_s=r[2], ia=r[3], regra=r[4], confianca=r[5], rotulo=r[6], imagem=bool(r[7])) for r in rows]

@app.get('/api/gancho/{gid}.png')
def api_gancho_png(gid: int, u=Depends(logado)):
    r = banco.q('SELECT imagem FROM monovia_ganchos WHERE id=?', (gid,), um=True)
    if not r or r[0] is None: raise HTTPException(404)
    B, G = ler_png_gancho(bytes(r[0]))
    img = np.concatenate([np.repeat(G[:, None], 6, 1), np.full((B.shape[0], 2, 3), 255, np.uint8), np.repeat(B, 3, 1)], 1)
    buf = io.BytesIO(); Image.fromarray(img).resize((img.shape[1] * 2, img.shape[0] * 2), Image.NEAREST).save(buf, 'PNG')
    return Response(buf.getvalue(), media_type='image/png')

@app.post('/api/gancho/{gid}/rotulo')
async def api_rotulo(gid: int, req: Request, u=Depends(logado)):
    d = await req.json()
    banco.q('UPDATE monovia_ganchos SET rotulo=? WHERE id=?', (None if d.get('rotulo') is None else int(d['rotulo']), gid))
    return {'ok': True}

@app.get('/api/exportar_rotulos')
def api_exportar(u=Depends(logado)):
    """baixa os ganchos conferidos (rotulados) para treinar o modelo de novo no PC"""
    rows = banco.q('SELECT imagem, rotulo FROM monovia_ganchos WHERE rotulo IS NOT NULL AND imagem IS NOT NULL', todos=True)
    B, G, Y, K = [], [], [], []
    from contador import regra
    for img, rot in rows:
        b, g = ler_png_gancho(bytes(img)); y = None
        if modelo.ok:                                   # máscara linha a linha que bate com a contagem conferida
            p = modelo.prever(b, g)
            for lim in (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8):
                m = p > lim
                if len([1 for s, e in runs(m) if e - s >= 4]) == rot: y = m.astype(np.uint8); break
        if y is None and rot == 0: y = np.zeros(len(b), np.uint8)
        if y is None: continue
        B.append(b); G.append(g); Y.append(y); K.append(rot)
    buf = io.BytesIO()
    np.savez_compressed(buf, B=np.array(B), G=np.array(G), Y=np.array(Y), K=np.array(K))
    return Response(buf.getvalue(), media_type='application/octet-stream',
                    headers={'Content-Disposition': f'attachment; filename="rotulados_real_{agora():%Y%m%d}.npz"'})

@app.get('/saude')
def saude(): return {'ok': True}
