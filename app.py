import os
import random
from datetime import datetime, timedelta
from functools import wraps

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, jsonify, session,
    redirect, url_for, flash
)
from werkzeug.utils import secure_filename
from supabase import create_client, Client

# Carrega variáveis do arquivo .env (só funciona localmente; no Render usa as env vars do painel)
load_dotenv()

# ================= CONFIG =================
ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'pdf', 'webp'}
MAX_MB = 10
SESSION_HOURS = int(os.environ.get('SESSION_HOURS', '8'))
STORAGE_BUCKET = 'assinaturas'  # nome do bucket no Supabase Storage

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-me')
app.config['MAX_CONTENT_LENGTH'] = MAX_MB * 1024 * 1024
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=SESSION_HOURS)

# ================= SUPABASE STORAGE =================
def get_storage() -> Client:
    """Retorna cliente Supabase para operações de Storage."""
    url  = os.environ.get('SUPABASE_URL')
    key  = os.environ.get('SUPABASE_SERVICE_KEY')
    if not url or not key:
        raise RuntimeError("SUPABASE_URL e SUPABASE_SERVICE_KEY são obrigatórios")
    return create_client(url, key)

def upload_arquivo(file_bytes: bytes, filename: str, content_type: str) -> str:
    """
    Faz upload do arquivo para o Supabase Storage.
    Retorna a URL pública permanente do arquivo.
    """
    storage = get_storage()
    # Envia o arquivo para o bucket
    storage.storage.from_(STORAGE_BUCKET).upload(
        path=filename,
        file=file_bytes,
        file_options={"content-type": content_type, "upsert": "true"}
    )
    # Gera URL pública permanente
    url = storage.storage.from_(STORAGE_BUCKET).get_public_url(filename)
    return url

def deletar_arquivo(filename: str):
    """Remove um arquivo do Supabase Storage (usado ao cancelar pedido)."""
    try:
        storage = get_storage()
        storage.storage.from_(STORAGE_BUCKET).remove([filename])
    except Exception as e:
        app.logger.warning(f"Não foi possível deletar {filename} do Storage: {e}")

# ================= DB =================
def db():
    """Abre conexão com o PostgreSQL usando a URL do ambiente."""
    conn = psycopg2.connect(
        os.environ.get('DATABASE_URL'),
        cursor_factory=psycopg2.extras.RealDictCursor  # retorna linhas como dicionários (igual ao row_factory do SQLite)
    )
    return conn

def estoque_disponivel(conn, sap, prazo):
    """Calcula estoque disponível subtraindo pedidos ACEITOS do estoque inicial."""
    col = {
        15: 'estoque_inicial_15',
        30: 'estoque_inicial_30',
        60: 'estoque_inicial_60'
    }.get(prazo)

    if not col:
        return 0

    cur = conn.cursor()
    # Busca o estoque inicial da máquina
    cur.execute(f"SELECT {col} FROM maquinas WHERE sap=%s", (sap,))
    row = cur.fetchone()
    if not row:
        return 0

    inicial = row[col] or 0

    # Soma todos os pedidos ACEITOS para esse SAP e prazo
    cur.execute("""
        SELECT COALESCE(SUM(quantidade), 0) AS usado
        FROM pedidos
        WHERE sap=%s AND prazo=%s AND status='ACEITO'
    """, (sap, prazo))
    usado = cur.fetchone()['usado']

    return max(0, inicial - usado)

def modelo_por_sap(conn, sap):
    cur = conn.cursor()
    cur.execute("SELECT modelo FROM maquinas WHERE sap=%s", (sap,))
    r = cur.fetchone()
    return r['modelo'] if r else ''

def gerar_id_pedido():
    return f"PED-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{random.randint(0,999):03d}"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

# ================= AUTH =================
def get_admin_emails():
    raw = os.environ.get('ADMIN_EMAILS', '')
    return [e.strip().lower() for e in raw.split(',') if e.strip()]

def get_admin_password():
    return os.environ.get('ADMIN_PASSWORD', '')

def verificar_credenciais(email, senha):
    return (email or '').lower().strip() in get_admin_emails() and senha == get_admin_password()

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_email'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ================= CONTEXT PROCESSOR =================
@app.context_processor
def inject_admin():
    """Injeta variável admin_logado em todos os templates."""
    return {'admin_logado': session.get('admin_email')}

# ================= API =================
@app.route('/api/estoque')
def api_estoque():
    try:
        sap = request.args.get('sap')
        if not sap:
            return jsonify({'error': 'sap obrigatório'}), 400

        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT modelo FROM maquinas WHERE sap=%s", (sap,))
        maquina = cur.fetchone()

        if not maquina:
            conn.close()
            return jsonify({'error': 'SAP não encontrado'}), 404

        resp = {
            'modelo': maquina['modelo'],
            'sap': sap,
            'disponivel': {
                '15': estoque_disponivel(conn, sap, 15),
                '30': estoque_disponivel(conn, sap, 30),
                '60': estoque_disponivel(conn, sap, 60),
            }
        }

        conn.close()
        return jsonify(resp)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ================= HOME =================
@app.route('/')
def index():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT modelo, sap FROM maquinas ORDER BY modelo")
    maquinas = cur.fetchall()

    linhas = []
    total_15 = total_30 = total_60 = 0

    for m in maquinas:
        d15 = estoque_disponivel(conn, m['sap'], 15)
        d30 = estoque_disponivel(conn, m['sap'], 30)
        d60 = estoque_disponivel(conn, m['sap'], 60)
        total_15 += d15
        total_30 += d30
        total_60 += d60
        linhas.append({
            'modelo': m['modelo'],
            'sap': m['sap'],
            'd15': d15, 'd30': d30, 'd60': d60,
            'total': d15 + d30 + d60
        })

    cur.execute("SELECT nome FROM dealers ORDER BY nome")
    dealers = [r['nome'] for r in cur.fetchall()]
    conn.close()

    return render_template(
        'index.html',
        linhas=linhas, dealers=dealers,
        total_15=total_15, total_30=total_30, total_60=total_60,
        total_geral=total_15 + total_30 + total_60
    )

# ================= NOVO PEDIDO =================
@app.route('/pedido/novo', methods=['GET', 'POST'])
def novo_pedido():
    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT nome FROM dealers ORDER BY nome")
    dealers = [r['nome'] for r in cur.fetchall()]
    cur.execute("SELECT modelo, sap FROM maquinas ORDER BY modelo")
    maquinas = cur.fetchall()

    if request.method == 'POST':
        try:
            dealer      = request.form.get('dealer')
            funcionario = request.form.get('funcionario')
            sap         = request.form.get('sap')
            quantidade  = int(request.form.get('quantidade') or 0)
            prazo       = int(request.form.get('prazo') or 0)

            if quantidade > estoque_disponivel(conn, sap, prazo):
                flash('Estoque insuficiente', 'error')
                return redirect(url_for('novo_pedido'))

            file = request.files.get('assinatura')
            if not file or not allowed_file(file.filename):
                flash('Arquivo inválido', 'error')
                return redirect(url_for('novo_pedido'))

            id_pedido = gerar_id_pedido()
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = secure_filename(f"{id_pedido}.{ext}")

            # Lê o conteúdo do arquivo em memória e envia para o Supabase Storage
            file_bytes = file.read()
            content_type = file.content_type or 'application/octet-stream'
            anexo_url = upload_arquivo(file_bytes, filename, content_type)
            # anexo_url é a URL pública permanente — salva no banco no lugar do filename local

            cur.execute("""
                INSERT INTO pedidos
                    (id, data_hora, dealer, funcionario, modelo, sap, quantidade, prazo, anexo_filename, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACEITO')
            """, (
                id_pedido,
                datetime.now().isoformat(),
                dealer,
                funcionario,
                modelo_por_sap(conn, sap),
                sap,
                quantidade,
                prazo,
                anexo_url   # URL pública do Supabase Storage
            ))

            conn.commit()
            conn.close()
            return redirect(url_for('sucesso', id_pedido=id_pedido))

        except Exception as e:
            conn.close()
            flash(f'Erro: {e}', 'error')
            return redirect(url_for('novo_pedido'))

    conn.close()
    return render_template('novo_pedido.html', dealers=dealers, maquinas=maquinas)

# ================= SUCESSO =================
@app.route('/pedido/sucesso/<id_pedido>')
def sucesso(id_pedido):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM pedidos WHERE id=%s", (id_pedido,))
    pedido = cur.fetchone()
    conn.close()
    return render_template('sucesso.html', pedido=pedido)

# ================= CANCELAR PEDIDO =================
@app.route('/pedido/cancelar/<id_pedido>', methods=['POST'])
@admin_required
def cancelar_pedido(id_pedido):
    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM pedidos WHERE id=%s", (id_pedido,))
    pedido = cur.fetchone()

    if pedido:
        # Tenta deletar o arquivo do Supabase Storage
        # anexo_filename agora é uma URL; extrai só o nome do arquivo
        anexo_url = pedido['anexo_filename'] or ''
        if anexo_url:
            filename = anexo_url.split('/')[-1]
            deletar_arquivo(filename)

    cur.execute("UPDATE pedidos SET status='CANCELADO' WHERE id=%s", (id_pedido,))
    conn.commit()
    conn.close()

    flash('Pedido cancelado com sucesso', 'success')
    return redirect(url_for('listar_pedidos'))

# ================= ADMIN =================
@app.route('/pedidos')
@admin_required
def listar_pedidos():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM pedidos ORDER BY data_hora DESC")
    pedidos = cur.fetchall()
    conn.close()
    return render_template('pedidos.html', pedidos=pedidos)

# ================= LOGIN =================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        if verificar_credenciais(email, senha):
            session.permanent = True
            session['admin_email'] = email
            return redirect(url_for('listar_pedidos'))
        flash('Login inválido', 'error')
    return render_template('login.html')

# ================= LOGOUT =================
@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('index'))

# ================= RUN =================
if __name__ == '__main__':
    app.run(debug=True)
