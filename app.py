import os
import sqlite3
import random
from datetime import datetime
from flask import (Flask, render_template, request, jsonify,
                   send_from_directory, redirect, url_for, flash, abort)
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'agrishow.db')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'pdf', 'webp'}
MAX_MB = 10

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-me')
app.config['MAX_CONTENT_LENGTH'] = MAX_MB * 1024 * 1024

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# Inicializa DB automaticamente na primeira execucao
if not os.path.exists(DB_PATH):
    import init_db
    init_db.main()


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


# ---------------- HOME / MENU DE COMPRA ----------------
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
            'modelo': m['modelo'],
            'sap': m['sap'],
            'd15': d15,
            'd30': d30,
            'd60': d60,
            'total': d15 + d30 + d60
        })
    dealers = [r['nome'] for r in conn.execute("SELECT nome FROM dealers ORDER BY nome").fetchall()]
    conn.close()
    return render_template('index.html',
                           linhas=linhas,
                           total_15=total_15,
                           total_30=total_30,
                           total_60=total_60,
                           total_geral=total_15 + total_30 + total_60,
                           dealers=dealers)


# ---------------- API DE ESTOQUE (alimenta o formulario em tempo real) ----------------
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
        'modelo': m['modelo'],
        'sap': sap,
        'disponivel': {
            '15': estoque_disponivel(conn, sap, 15),
            '30': estoque_disponivel(conn, sap, 30),
            '60': estoque_disponivel(conn, sap, 60),
        }
    }
    conn.close()
    return jsonify(resp)


# ---------------- NOVO PEDIDO ----------------
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

        # Validacoes
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
            erros.append('Formato de arquivo nao permitido (use png, jpg, pdf, etc).')

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

        # Salvar arquivo com nome baseado no ID do pedido
        id_pedido = gerar_id_pedido()
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = secure_filename(f"{id_pedido}.{ext}")
        file.save(os.path.join(UPLOAD_DIR, filename))

        # Gravar pedido (agora com modelo correto)
        conn.execute("""
            INSERT INTO pedidos
            (id, data_hora, dealer, funcionario, modelo, sap,
             quantidade, prazo, anexo_filename, status)
            VALUES (?,?,?,?,?,?,?,?,?,'ACEITO')
        """, (id_pedido, datetime.now().isoformat(timespec='seconds'),
              dealer, funcionario, modelo, sap,
              quantidade, prazo, filename))
        conn.commit()
        conn.close()
        flash(f'Pedido aceito com sucesso! ID: {id_pedido}', 'success')
        return redirect(url_for('sucesso', id_pedido=id_pedido))

    conn.close()
    return render_template('novo_pedido.html', dealers=dealers, maquinas=maquinas)


# ---------------- SUCESSO ----------------
@app.route('/pedido/sucesso/<id_pedido>')
def sucesso(id_pedido):
    conn = db()
    p = conn.execute("SELECT * FROM pedidos WHERE id = ?", (id_pedido,)).fetchone()
    conn.close()
    if p is None:
        abort(404)
    return render_template('sucesso.html', pedido=p)


# ---------------- CANCELAR PEDIDO (somente POST) ----------------
@app.route('/pedido/cancelar/<id_pedido>', methods=['POST'])
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
    conn.execute("UPDATE pedidos SET status = 'CANCELADO' WHERE id = ?", (id_pedido,))
    conn.commit()
    conn.close()
    flash(f'Pedido {id_pedido} cancelado. Estoque liberado.', 'success')
    return redirect(url_for('listar_pedidos'))


# ---------------- LISTAR PEDIDOS ----------------
@app.route('/pedidos')
def listar_pedidos():
    conn = db()
    pedidos = conn.execute("SELECT * FROM pedidos ORDER BY data_hora DESC").fetchall()
    conn.close()
    return render_template('pedidos.html', pedidos=pedidos)


# ---------------- DOWNLOAD ----------------
@app.route('/uploads/<path:filename>')
def download_anexo(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# ---------------- ERROS ----------------
@app.errorhandler(413)
def too_large(e):
    flash(f'Arquivo muito grande. Limite: {MAX_MB}MB.', 'error')
    return redirect(url_for('novo_pedido'))


# ---------------- RUN ----------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=port, debug=debug)
