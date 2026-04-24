"""
app.py - Agrishow Sistema de Pedidos v3
- Separacao publico (Dealers) / admin (gestores)
- Login de admins via variavel de ambiente ADMIN_USERS
- Notificacoes por email no Gmail SMTP ao criar/cancelar pedido
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


# ---------------- ADMINS (via env var) ----------------
def get_admins():
    """Parseia ADMIN_USERS=email1:senha1|email2:senha2 e retorna dict {email: senha}."""
    raw = os.environ.get('ADMIN_USERS', '')
    if not raw:
        return {}
    admins = {}
    for par in raw.split('|'):
        par = par.strip()
        if ':' not in par:
            continue
        email, senha = par.split(':', 1)
        email = email.strip().lower()
        senha = senha.strip()
        if email and senha:
            admins[email] = senha
    return admins


def verificar_credenciais(email, senha):
    """True se o par email+senha bate com algum admin cadastrado."""
    if not email or not senha:
        return False
    admins = get_admins()
    return admins.get(email.strip().lower()) == senha


def admin_emails():
    """Lista de emails dos admins (para notificacoes)."""
    return list(get_admins().keys())


def admin_required(f):
    """Decorador: exige sessao de admin ativa para acessar a rota."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_email'):
            flash('Acesso restrito. Faca login como administrador.', 'error')
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated


# ---------------- RATE LIMITING DE LOGIN (memoria) ----------------
_login_attempts = {}  # {ip: [(timestamp, success_bool), ...]}
MAX_FAILED = 5
LOCK_SECONDS = 300


def _cliente_ip():
    """Melhor esforco: pega IP do cliente respeitando proxies do Render."""
    xff = request.headers.get('X-Forwarded-For')
    if xff:
        return xff.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def login_bloqueado(ip):
    """True se o IP tem >= MAX_FAILED falhas nas ultimas LOCK_SECONDS."""
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
    """Converte sqlite3.Row em dict para passar ao email_utils."""
    if pedido_row is None:
        return {}
    return dict(pedido_row)


# ---------------- CONTEXT PROCESSOR ----------------
@app.context_processor
def inject_admin():
    """Disponibiliza admin_logado em TODOS os templates."""
    return {
        'admin_logado': session.get('admin_email'),
    }


# ---------------- HOME / MENU DE COMPRA (publico) ----------------
@app.route('/')
def index():
    conn = db()
    maquinas = conn.execute("SELECT * FROM maquinas ORDER BY modelo, sap").fetchall()
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
            'modelo': m['modelo'], 'sap': m['sap'],
            'd15': d15, 'd30': d30, 'd60': d60,
            'total': d15 + d30 + d60
        })
    dealers = [r['nome'] for r in conn.execute("SELECT nome FROM dealers ORDER BY nome").fetchall()]
    conn.close()
    return render_template('index.html',
                           linhas=linhas,
                           total_15=total_15, total_30=total_30, total_60=total_60,
                           total_geral=total_15 + total_30 + total_60,
                           dealers=dealers)


# ---------------- API DE ESTOQUE (publico) ----------------
@app.route('/api/estoque')
def api_estoque():
    sap = request.args.get('sap', '').strip()
    if not sap:
        return jsonify({'error': 'sap obrigatorio'}), 400
    conn = db()
    m = conn.execute("SELECT modelo FROM maquinas WHERE sap = ?", (sap,)).fetchone()
    if m is None:
        conn.close()
        return jsonify({'error': 'SAP nao encontrado'}), 404
    resp = {
        'modelo': m['modelo'], 'sap': sap,
        'disponivel': {
            '15': estoque_disponivel(conn, sap, 15),
            '30': estoque_disponivel(conn, sap, 30),
            '60': estoque_disponivel(conn, sap, 60),
        }
    }
    conn.close()
    return jsonify(resp)


# ---------------- NOVO PEDIDO (publico) ----------------
@app.route('/pedido/novo', methods=['GET', 'POST'])
def novo_pedido():
    conn = db()
    dealers = [r['nome'] for r in conn.execute("SELECT nome FROM dealers ORDER BY nome").fetchall()]
    maquinas = conn.execute("SELECT modelo, sap FROM maquinas ORDER BY modelo, sap").fetchall()

    if request.method == 'POST':
        dealer = (request.form.get('dealer') or '').strip()
        funcionario = (request.form.get('funcionario') or '').strip()
        sap = (request.form.get('sap') or '').strip()
        try:
            quantidade = int(request.form.get('quantidade') or 0)
            prazo = int(request.form.get('prazo') or 0)
        except ValueError:
            flash('Quantidade ou prazo invalidos.', 'error')
            conn.close()
            return redirect(url_for('novo_pedido'))

        file = request.files.get('assinatura')

        erros = []
        if not dealer or dealer not in dealers:
            erros.append('Selecione um Dealer valido.')
        if not funcionario:
            erros.append('Nome do funcionario e obrigatorio.')
        if prazo not in (15, 30, 60):
            erros.append('Prazo deve ser 15, 30 ou 60 dias.')
        if quantidade <= 0:
            erros.append('Quantidade deve ser maior que zero.')
        if not file or not file.filename:
            erros.append('Anexo de assinatura e obrigatorio.')
        elif not allowed_file(file.filename):
            erros.append('Formato de arquivo nao permitido.')

        modelo = modelo_por_sap(conn, sap)
        if not modelo:
            erros.append('Codigo SAP da maquina invalido.')

        if not erros:
            disp = estoque_disponivel(conn, sap, prazo)
            if quantidade > disp:
                erros.append(f'Estoque insuficiente. Disponivel em {prazo} dias: {disp} unidade(s).')

        if erros:
            for e in erros:
                flash(e, 'error')
            conn.close()
            return redirect(url_for('novo_pedido'))

        id_pedido = gerar_id_pedido()
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = secure_filename(f"{id_pedido}.{ext}")
        file.save(os.path.join(UPLOAD_DIR, filename))

        agora_iso = datetime.now().isoformat(timespec='seconds')
        conn.execute("""
            INSERT INTO pedidos
            (id, data_hora, dealer, funcionario, modelo, sap,
             quantidade, prazo, anexo_filename, status)
            VALUES (?,?,?,?,?,?,?,?,?,'ACEITO')
        """, (id_pedido, agora_iso, dealer, funcionario, modelo, sap,
              quantidade, prazo, filename))
        conn.commit()

        # Dispara email (thread separada)
        pedido_dict = {
            'id': id_pedido, 'data_hora': agora_iso, 'dealer': dealer,
            'funcionario': funcionario, 'modelo': modelo, 'sap': sap,
            'quantidade': quantidade, 'prazo': prazo,
        }
        emails = admin_emails()
        if emails:
            try:
                notificar_pedido_criado(pedido_dict, emails)
            except Exception as e:
                app.logger.error(f"Erro ao disparar email de criacao: {e}")

        conn.close()
        flash(f'Pedido aceito com sucesso! ID: {id_pedido}', 'success')
        return redirect(url_for('sucesso', id_pedido=id_pedido))

    conn.close()
    return render_template('novo_pedido.html', dealers=dealers, maquinas=maquinas)


# ---------------- SUCESSO (publico) ----------------
@app.route('/pedido/sucesso/<id_pedido>')
def sucesso(id_pedido):
    conn = db()
    p = conn.execute("SELECT * FROM pedidos WHERE id = ?", (id_pedido,)).fetchone()
    conn.close()
    if p is None:
        abort(404)
    return render_template('sucesso.html', pedido=p)


# ---------------- LOGIN / LOGOUT ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('admin_email'):
        return redirect(url_for('listar_pedidos'))

    if request.method == 'POST':
        ip = _cliente_ip()
        if login_bloqueado(ip):
            flash('Muitas tentativas falhas. Aguarde 5 minutos e tente novamente.', 'error')
            return render_template('login.html')

        email = (request.form.get('email') or '').strip().lower()
        senha = request.form.get('senha') or ''

        if verificar_credenciais(email, senha):
            registrar_tentativa(ip, True)
            session.permanent = True
            session['admin_email'] = email
            flash(f'Bem-vindo, {email}!', 'success')
            next_url = request.args.get('next')
            return redirect(next_url if next_url and next_url.startswith('/') else url_for('listar_pedidos'))
        else:
            registrar_tentativa(ip, False)
            flash('Email ou senha incorretos.', 'error')

    return render_template('login.html')


@app.route('/logout', methods=['POST'])
def logout():
    session.pop('admin_email', None)
    flash('Voce saiu do sistema.', 'success')
    return redirect(url_for('index'))


# ---------------- CANCELAR (admin) ----------------
@app.route('/pedido/cancelar/<id_pedido>', methods=['POST'])
@admin_required
def cancelar_pedido(id_pedido):
    conn = db()
    pedido = conn.execute("SELECT * FROM pedidos WHERE id = ?", (id_pedido,)).fetchone()
    if not pedido:
        conn.close()
        abort(404)
    if pedido['status'] == 'CANCELADO':
        conn.close()
        flash('Este pedido ja foi cancelado.', 'error')
        return redirect(url_for('listar_pedidos'))

    cancelado_por = session.get('admin_email', 'admin')
    cancelado_em = datetime.now().isoformat(timespec='seconds')
    try:
        conn.execute("""
            UPDATE pedidos
            SET status = 'CANCELADO',
                cancelado_por = ?,
                cancelado_em = ?
            WHERE id = ?
        """, (cancelado_por, cancelado_em, id_pedido))
    except sqlite3.OperationalError:
        # Fallback para bancos antigos sem as colunas novas
        conn.execute("UPDATE pedidos SET status = 'CANCELADO' WHERE id = ?", (id_pedido,))
    conn.commit()

    # Dispara email
    pedido_dict = pedido_to_dict(pedido)
    pedido_dict['cancelado_por'] = cancelado_por
    emails = admin_emails()
    if emails:
        try:
            notificar_pedido_cancelado(pedido_dict, cancelado_por, emails)
        except Exception as e:
            app.logger.error(f"Erro ao disparar email de cancelamento: {e}")

    conn.close()
    flash(f'Pedido {id_pedido} cancelado. Estoque liberado.', 'success')
    return redirect(url_for('listar_pedidos'))


# ---------------- HISTORICO (admin) ----------------
@app.route('/pedidos')
@admin_required
def listar_pedidos():
    conn = db()
    pedidos = conn.execute("SELECT * FROM pedidos ORDER BY data_hora DESC").fetchall()
    total_aceitos = sum(1 for p in pedidos if p['status'] == 'ACEITO')
    total_cancelados = sum(1 for p in pedidos if p['status'] == 'CANCELADO')
    conn.close()
    return render_template('pedidos.html',
                           pedidos=pedidos,
                           total_aceitos=total_aceitos,
                           total_cancelados=total_cancelados)


# ---------------- DOWNLOAD ANEXO (admin) ----------------
@app.route('/uploads/<path:filename>')
@admin_required
def download_anexo(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# ---------------- ERROS ----------------
@app.errorhandler(413)
def too_large(e):
    flash(f'Arquivo muito grande. Limite: {MAX_MB}MB.', 'error')
    return redirect(url_for('novo_pedido'))


@app.errorhandler(403)
def forbidden(e):
    return redirect(url_for('login'))


# ---------------- RUN ----------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=port, debug=debug)
