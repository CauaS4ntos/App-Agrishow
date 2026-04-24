"""
app.py - Agrishow Sistema de Pedidos v3 (REVISADO)
- Login admin com emails via ENV
- Senha unica via ENV
- Rate limit de login
- Notificacoes por email
"""

import os
import sqlite3
import random
import time
from datetime import datetime, timedelta
from functools import wraps
from flask import (Flask, render_template, request, jsonify, session,
                   send_from_directory, redirect, url_for, flash, abort)
from werkzeug.utils import secure_filename

from email_utils import notificar_pedido_criado, notificar_pedido_cancelado

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'agrishow.db')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')

ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'pdf', 'webp'}
MAX_MB = 10
SESSION_HOURS = int(os.environ.get('SESSION_HOURS', '8'))

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-me')
app.config['MAX_CONTENT_LENGTH'] = MAX_MB * 1024 * 1024
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=SESSION_HOURS)

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

if not os.path.exists(DB_PATH):
    import init_db
    init_db.main()

# ---------------- ADMINS ----------------
def get_admin_emails():
    raw = os.environ.get('ADMIN_EMAILS', '')
    return [e.strip().lower() for e in raw.split(',') if e.strip()]

def get_admin_password():
    return os.environ.get('ADMIN_PASSWORD', '')

def verificar_credenciais(email, senha):
    if not email or not senha:
        return False

    email = email.strip().lower()

    # 🔒 restringe dominio (opcional)
    if not email.endswith('@empresa.com'):
        return False

    return (
        email in get_admin_emails()
        and senha == get_admin_password()
    )

def admin_emails():
    return get_admin_emails()

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_email'):
            flash('Acesso restrito. Faca login.', 'error')
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated

# ---------------- RATE LIMIT ----------------
_login_attempts = {}
MAX_FAILED = 5
LOCK_SECONDS = 300

def _cliente_ip():
    xff = request.headers.get('X-Forwarded-For')
    if xff:
        return xff.split(',')[0].strip()
    return request.remote_addr or 'unknown'

def login_bloqueado(ip):
    agora = time.time()
    tentativas = _login_attempts.get(ip, [])
    tentativas = [(t, ok) for (t, ok) in tentativas if agora - t < LOCK_SECONDS]
    _login_attempts[ip] = tentativas
    falhas = sum(1 for (_, ok) in tentativas if not ok)
    return falhas >= MAX_FAILED

def registrar_tentativa(ip, sucesso):
    _login_attempts.setdefault(ip, []).append((time.time(), sucesso))

# ---------------- DB ----------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def estoque_disponivel(conn, sap, prazo):
    col = {15: 'estoque_inicial_15', 30: 'estoque_inicial_30', 60: 'estoque_inicial_60'}.get(prazo)
    if col is None:
        return 0
    row = conn.execute(f"SELECT {col} FROM maquinas WHERE sap = ?", (sap,)).fetchone()
    if row is None:
        return 0
    inicial = row[0] or 0
    usado = conn.execute("""
        SELECT COALESCE(SUM(quantidade), 0)
        FROM pedidos
        WHERE sap = ? AND prazo = ? AND status = 'ACEITO'
    """, (sap, prazo)).fetchone()[0]
    return max(0, inicial - usado)

def modelo_por_sap(conn, sap):
    row = conn.execute("SELECT modelo FROM maquinas WHERE sap = ?", (sap,)).fetchone()
    return row['modelo'] if row else ''

def gerar_id_pedido():
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    rnd = f"{random.randint(0, 999):03d}"
    return f"PED-{ts}-{rnd}"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

def pedido_to_dict(pedido_row):
    return dict(pedido_row) if pedido_row else {}

# ---------------- CONTEXT ----------------
@app.context_processor
def inject_admin():
    return {'admin_logado': session.get('admin_email')}

# ---------------- ROTAS ----------------
@app.route('/')
def index():
    conn = db()
    maquinas = conn.execute("SELECT * FROM maquinas ORDER BY modelo").fetchall()

    linhas = []
    for m in maquinas:
        d15 = estoque_disponivel(conn, m['sap'], 15)
        d30 = estoque_disponivel(conn, m['sap'], 30)
        d60 = estoque_disponivel(conn, m['sap'], 60)

        linhas.append({
            'modelo': m['modelo'],
            'sap': m['sap'],
            'd15': d15,
            'd30': d30,
            'd60': d60,
            'total': d15 + d30 + d60
        })

    dealers = [r['nome'] for r in conn.execute("SELECT nome FROM dealers").fetchall()]
    conn.close()

    return render_template('index.html', linhas=linhas, dealers=dealers)

# ---------------- LOGIN ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('admin_email'):
        return redirect(url_for('listar_pedidos'))

    if request.method == 'POST':
        ip = _cliente_ip()

        if login_bloqueado(ip):
            flash('Muitas tentativas. Aguarde 5 minutos.', 'error')
            return render_template('login.html')

        email = (request.form.get('email') or '').lower()
        senha = request.form.get('senha') or ''

        if verificar_credenciais(email, senha):
            registrar_tentativa(ip, True)
            session.permanent = True
            session['admin_email'] = email

            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('listar_pedidos'))
        else:
            registrar_tentativa(ip, False)
            flash('Email ou senha incorretos.', 'error')

    return render_template('login.html')

# ---------------- LOGOUT ----------------
@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    flash('Logout realizado.', 'success')
    return redirect(url_for('index'))

# ---------------- PEDIDOS ----------------
@app.route('/pedidos')
@admin_required
def listar_pedidos():
    conn = db()
    pedidos = conn.execute("SELECT * FROM pedidos ORDER BY data_hora DESC").fetchall()
    conn.close()
    return render_template('pedidos.html', pedidos=pedidos)

# ---------------- RUN ----------------
if __name__ == '__main__':
    app.run()
