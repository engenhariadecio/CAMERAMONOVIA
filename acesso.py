"""
Login com usuário e senha.
- O primeiro usuário (administrador) vem das variáveis MONOVIA_USUARIO e MONOVIA_SENHA do Railway.
- O administrador cadastra outros usuários pelo painel.
- Sessão em cookie assinado (o celular fica logado por 90 dias).
- Para o Banho e Monovia ler os números sem login: chave em MONOVIA_CHAVE_API (cabeçalho X-Chave ou ?chave=).
"""
import os, hmac, hashlib, base64, secrets, time
from collections import defaultdict, deque
import banco

DIAS_SESSAO = 90
COOKIE = 'monovia_sessao'
CHAVE_API = os.environ.get('MONOVIA_CHAVE_API', '')

def criar_tabela():
    banco.q('CREATE TABLE IF NOT EXISTS monovia_usuarios (usuario TEXT PRIMARY KEY, hash TEXT, admin INTEGER)')
    banco.q("CREATE TABLE IF NOT EXISTS monovia_segredo (id INTEGER PRIMARY KEY, valor TEXT)")
    if not banco.q('SELECT 1 FROM monovia_segredo WHERE id=1', um=True):
        banco.q('INSERT INTO monovia_segredo (id, valor) VALUES (1, ?)', (secrets.token_hex(32),))
    u, s = os.environ.get('MONOVIA_USUARIO', '').strip().lower(), os.environ.get('MONOVIA_SENHA', '')
    if u and s: salvar_usuario(u, s, True)            # administrador sempre com a senha das variáveis

def _segredo():
    return (os.environ.get('MONOVIA_SEGREDO') or banco.q('SELECT valor FROM monovia_segredo WHERE id=1', um=True)[0]).encode()

def _hash(senha, sal=None):
    sal = sal or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', senha.encode(), sal.encode(), 200_000).hex()
    return f'{sal}${h}'

def salvar_usuario(usuario, senha, admin=False):
    usuario = usuario.strip().lower()
    if banco.q('SELECT 1 FROM monovia_usuarios WHERE usuario=?', (usuario,), um=True):
        banco.q('UPDATE monovia_usuarios SET hash=?, admin=? WHERE usuario=?', (_hash(senha), int(admin), usuario))
    else:
        banco.q('INSERT INTO monovia_usuarios (usuario, hash, admin) VALUES (?,?,?)', (usuario, _hash(senha), int(admin)))

def apagar_usuario(usuario):
    banco.q('DELETE FROM monovia_usuarios WHERE usuario=?', (usuario.strip().lower(),))

def listar():
    return [dict(usuario=r[0], admin=bool(r[1])) for r in banco.q('SELECT usuario, admin FROM monovia_usuarios ORDER BY usuario', todos=True)]

def conferir(usuario, senha):
    r = banco.q('SELECT hash, admin FROM monovia_usuarios WHERE usuario=?', (usuario.strip().lower(),), um=True)
    if not r: _hash(senha); return None                 # mesmo tempo de resposta com ou sem usuário
    sal, h = r[0].split('$')
    return {'usuario': usuario.strip().lower(), 'admin': bool(r[1])} if hmac.compare_digest(_hash(senha, sal), r[0]) else None

# ---- tentativas de login (trava após 8 erros em 10 min por IP) ----
_erros = defaultdict(deque)
def bloqueado(ip):
    d = _erros[ip]
    while d and time.time() - d[0] > 600: d.popleft()
    return len(d) >= 8
def errou(ip): _erros[ip].append(time.time())

# ---- sessão ----
def criar_sessao(usuario):
    exp = int(time.time()) + DIAS_SESSAO * 86400
    corpo = base64.urlsafe_b64encode(f'{usuario}|{exp}'.encode()).decode()
    ass = hmac.new(_segredo(), corpo.encode(), hashlib.sha256).hexdigest()
    return f'{corpo}.{ass}'

def ler_sessao(valor):
    """devolve {'usuario', 'admin'} ou None"""
    try:
        corpo, ass = (valor or '').rsplit('.', 1)
        if not hmac.compare_digest(ass, hmac.new(_segredo(), corpo.encode(), hashlib.sha256).hexdigest()): return None
        usuario, exp = base64.urlsafe_b64decode(corpo).decode().rsplit('|', 1)
        if int(exp) < time.time(): return None
        r = banco.q('SELECT admin FROM monovia_usuarios WHERE usuario=?', (usuario,), um=True)
        return {'usuario': usuario, 'admin': bool(r[0])} if r else None   # usuário apagado perde o acesso
    except Exception:
        return None

def chave_ok(valor):
    return bool(CHAVE_API) and bool(valor) and hmac.compare_digest(valor, CHAVE_API)
