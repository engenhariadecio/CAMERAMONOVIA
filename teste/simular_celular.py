"""
Simula o celular mandando a linha de pixels de um vídeo gravado para o servidor (para testar sem ir à linha).
  python teste/simular_celular.py video.mp4 http://localhost:8000 --senha X --x 380 --y0 280 --y1 600 --ry 100 --fundo-em 10.5
"""
import argparse, asyncio, json, struct, time, urllib.request
import cv2, numpy as np, websockets

ap = argparse.ArgumentParser()
ap.add_argument('video'); ap.add_argument('url')
ap.add_argument('--usuario', default='admin'); ap.add_argument('--senha', default='')
ap.add_argument('--x', type=int); ap.add_argument('--y0', type=int); ap.add_argument('--y1', type=int); ap.add_argument('--ry', type=int)
ap.add_argument('--passo', type=float, default=None)
ap.add_argument('--fundo-em', type=float, default=None, help='segundo do vídeo em que aperta "Gravar fundo"')
ap.add_argument('--fps', type=float, default=15)
ap.add_argument('--tempo-real', action='store_true')
a = ap.parse_args()

COOKIE = ''
def api(c, corpo=None):
    req = urllib.request.Request(a.url + c, data=json.dumps(corpo).encode() if corpo else None,
                                 headers={'Content-Type': 'application/json', 'Cookie': COOKIE})
    r = urllib.request.urlopen(req)
    return r, json.loads(r.read())

def entrar():
    global COOKIE
    r, _ = api('/api/entrar', {'usuario': a.usuario, 'senha': a.senha})
    COOKIE = r.headers['set-cookie'].split(';')[0]

async def main():
    cap = cv2.VideoCapture(a.video); FPS = cap.get(cv2.CAP_PROP_FPS) or 30
    W, H = int(cap.get(3)), int(cap.get(4))
    entrar()
    if a.x is not None:
        api('/api/config', dict(x=a.x, y0=a.y0, y1=a.y1, ry=a.ry, w=W, h=H, passo=a.passo))
    cfg = api('/api/config')[1]
    ws_url = a.url.replace('http', 'ws') + '/ws/camera'
    t0 = time.time() * 1000; passo_q = FPS / a.fps; prox = 0; i = 0; buf = []; ult_mov = -1; mov = -1.0; fundo_mandado = False
    async with websockets.connect(ws_url, max_size=None, additional_headers={'Cookie': COOKIE}) as ws:
        async def ouvir():
            try:
                async for m in ws: pass
            except Exception: pass
        tarefa = asyncio.create_task(ouvir())
        while True:
            ok, f = cap.read()
            if not ok: break
            t = i / FPS; i += 1
            if i - 1 < prox: continue
            prox += passo_q
            if a.fundo_em is not None and not fundo_mandado and t >= a.fundo_em:
                await ws.send(json.dumps({'tipo': 'fundo'})); fundo_mandado = True
            if t - ult_mov >= 0.5:                                   # mesmo cálculo da página do celular
                ult_mov = t
                xa, xb = max(0, cfg['x'] - W // 4), min(W, cfg['x'] + W // 4)
                ya, yb = max(0, min(cfg['ry'], cfg['y0']) - 20), min(H, cfg['y1'] + 20)
                h = max(20, round(180 * (yb - ya) / (xb - xa)))
                g = cv2.cvtColor(cv2.resize(f[ya:yb, xa:xb], (180, h), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.int16)
                buf.append(g); buf = buf[-3:]
                if len(buf) == 3: mov = float((np.abs(buf[-1] - buf[0]) > 12).mean())
            ya, yb = cfg['ya'], min(cfg['yb'], H); x0 = max(0, cfg['x'] - 3)
            col = f[ya:yb, x0:x0 + 6].mean(axis=1)[:, ::-1].round().astype(np.uint8)    # BGR -> RGB
            pac = struct.pack('<dfHH', t0 + t * 1000, mov, ya, yb - ya) + col.tobytes()
            await ws.send(pac)
            if a.tempo_real: await asyncio.sleep(1 / a.fps)
            elif i % 30 == 0: await asyncio.sleep(0)
        await asyncio.sleep(1.5); tarefa.cancel()
    print(json.dumps(api('/api/resumo')[1], ensure_ascii=False, indent=1))

asyncio.run(main())
