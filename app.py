import os
import sqlite3
import random
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    Flask, render_template, request, jsonify, session,
    send_from_directory, redirect, url_for, flash
)
from werkzeug.utils import secure_filename

# ================= CONFIG =================
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

# cria banco apenas se não existir
if not os.path.exists(DB_PATH):
    import init_db
    init_db.main()

# ================= DB =================
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def estoque_disponivel(conn, sap, prazo):
    col = {
        15: 'estoque_inicial_15',
        30: 'estoque_inicial_30',
        60: 'estoque_inicial_60'
    }.get(prazo)

    if not col:
        return 0

    row = conn.execute(f"SELECT {col} FROM maquinas WHERE sap=?", (sap,)).fetchone()
    if not row:
        return 0

    inicial = row[0] or 0

    usado = conn.execute("""
        SELECT COALESCE(SUM(quantidade),0)
        FROM pedidos
        WHERE sap=? AND prazo=? AND status='ACEITO'
    """, (sap, prazo)).fetchone()[0]

    return max(0, inicial - usado)

def modelo_por_sap(conn, sap):
    r = conn.execute("SELECT modelo FROM maquinas WHERE sap=?", (sap,)).fetchone()
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

# ================= API =================
@app.route('/api/estoque')
def api_estoque():
    try:
        sap = request.args.get('sap')

        if not sap:
            return jsonify({'error': 'sap obrigatório'}), 400

        conn = db()

        maquina = conn.execute(
            "SELECT modelo FROM maquinas WHERE sap=?",
            (sap,)
        ).fetchone()

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
    maquinas = conn.execute("SELECT modelo, sap FROM maquinas").fetchall()

    linhas = []
    total_15 = 0
    total_30 = 0
    total_60 = 0

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
            'd15': d15,
            'd30': d30,
            'd60': d60,
            'total': d15 + d30 + d60
        })

    dealers = [r['nome'] for r in conn.execute("SELECT nome FROM dealers").fetchall()]

    conn.close()

    return render_template(
        'index.html',
        linhas=linhas,
        dealers=dealers,
        total_15=total_15,
        total_30=total_30,
        total_60=total_60,
        total_geral=total_15 + total_30 + total_60
    )

# ================= NOVO PEDIDO =================
@app.route('/pedido/novo', methods=['GET', 'POST'])
def novo_pedido():
    conn = db()

    dealers = [r['nome'] for r in conn.execute("SELECT nome FROM dealers").fetchall()]
    maquinas = conn.execute("SELECT modelo, sap FROM maquinas").fetchall()

    if request.method == 'POST':
        try:
            dealer = request.form.get('dealer')
            funcionario = request.form.get('funcionario')
            sap = request.form.get('sap')
            quantidade = int(request.form.get('quantidade') or 0)
            prazo = int(request.form.get('prazo') or 0)

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
            file.save(os.path.join(UPLOAD_DIR, filename))

            conn.execute("""
                INSERT INTO pedidos
                (id,data_hora,dealer,funcionario,modelo,sap,quantidade,prazo,anexo_filename,status)
                VALUES (?,?,?,?,?,?,?,?,?,'ACEITO')
            """, (
                id_pedido,
                datetime.now().isoformat(),
                dealer,
                funcionario,
                modelo_por_sap(conn, sap),
                sap,
                quantidade,
                prazo,
                filename
            ))

            conn.commit()
            conn.close()

            return redirect(url_for('index'))

        except Exception as e:
            conn.close()
            flash(f'Erro: {e}', 'error')
            return redirect(url_for('novo_pedido'))

    conn.close()
    return render_template('novo_pedido.html', dealers=dealers, maquinas=maquinas)

# ================= ADMIN =================
@app.route('/pedidos')
@admin_required
def listar_pedidos():
    conn = db()
    pedidos = conn.execute("SELECT * FROM pedidos ORDER BY data_hora DESC").fetchall()
    conn.close()
    return render_template('pedidos.html', pedidos=pedidos)

# ================= LOGIN =================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')

        if verificar_credenciais(email, senha):
            session['admin_email'] = email
            return redirect(url_for('listar_pedidos'))

        flash('Login inválido', 'error')

    return render_template('login.html')

# ================= LOGOUT =================
@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('index'))

# ================= DOWNLOAD =================
@app.route('/uploads/<path:filename>')
@admin_required
def download(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# ================= RUN =================
if __name__ == '__main__':
    app.run(debug=True)
