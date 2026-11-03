"""
Banco: PostgreSQL no Railway (variável DATABASE_URL) ou SQLite local para teste.
Tabelas com prefixo monovia_ para conviver no mesmo banco do Banho e Monovia.
Datas guardadas como texto 'AAAA-MM-DD HH:MM:SS' no horário de Brasília (fácil de ler pelo outro app).
"""
import os, json, sqlite3, threading

URL = os.environ.get('DATABASE_URL')
PG = bool(URL and URL.startswith('postgres'))
_lock = threading.Lock()

if PG:
    import psycopg
    _con = psycopg.connect(URL, autocommit=True)
    PH = '%s'; BLOB = 'BYTEA'; AUTO = 'SERIAL PRIMARY KEY'
else:
    _con = sqlite3.connect(os.environ.get('SQLITE', 'monovia_local.db'), check_same_thread=False, isolation_level=None)
    PH = '?'; BLOB = 'BLOB'; AUTO = 'INTEGER PRIMARY KEY AUTOINCREMENT'

def q(sql, args=(), um=False, todos=False):
    global _con
    sql = sql.replace('?', PH)
    with _lock:
        for tentativa in (1, 2):
            try:
                cur = _con.cursor(); cur.execute(sql, args)
                if um: return cur.fetchone()
                if todos: return cur.fetchall()
                if sql.strip().upper().startswith('INSERT') and 'RETURNING' in sql.upper(): return cur.fetchone()[0]
                return None
            except Exception:
                if PG and tentativa == 1:                       # conexão caiu: reconecta uma vez
                    try: _con = psycopg.connect(URL, autocommit=True); continue
                    except Exception: pass
                raise

def criar():
    q(f'''CREATE TABLE IF NOT EXISTS monovia_config (id INTEGER PRIMARY KEY, dados TEXT)''')
    q(f'''CREATE TABLE IF NOT EXISTS monovia_eventos (id {AUTO}, datahora TEXT, tipo TEXT, valor DOUBLE PRECISION, detalhe TEXT)''')
    q(f'''CREATE TABLE IF NOT EXISTS monovia_ganchos (id {AUTO}, datahora TEXT, duracao_s REAL, empilhamento INTEGER,
          empilhamento_regra INTEGER, confianca REAL, imagem {BLOB}, rotulo INTEGER)''')
    q('CREATE INDEX IF NOT EXISTS ix_mon_ev_dh ON monovia_eventos (datahora)')
    q('CREATE INDEX IF NOT EXISTS ix_mon_ga_dh ON monovia_ganchos (datahora)')

def ler_config():
    r = q('SELECT dados FROM monovia_config WHERE id=1', um=True)
    return json.loads(r[0]) if r else {}

def salvar_config(d):
    s = json.dumps(d)
    if q('SELECT 1 FROM monovia_config WHERE id=1', um=True): q('UPDATE monovia_config SET dados=? WHERE id=1', (s,))
    else: q('INSERT INTO monovia_config (id, dados) VALUES (1, ?)', (s,))

def evento(dh, tipo, valor=None, detalhe=None):
    q('INSERT INTO monovia_eventos (datahora, tipo, valor, detalhe) VALUES (?,?,?,?)',
      (dh, tipo, valor, json.dumps(detalhe, ensure_ascii=False) if detalhe else None))

def gancho(dh, dur, k, k_regra, conf, png):
    if PG:
        return q('INSERT INTO monovia_ganchos (datahora, duracao_s, empilhamento, empilhamento_regra, confianca, imagem) '
                 'VALUES (?,?,?,?,?,?) RETURNING id', (dh, dur, k, k_regra, conf, png))
    q('INSERT INTO monovia_ganchos (datahora, duracao_s, empilhamento, empilhamento_regra, confianca, imagem) VALUES (?,?,?,?,?,?)',
      (dh, dur, k, k_regra, conf, png))
    return q('SELECT last_insert_rowid()', um=True)[0]
