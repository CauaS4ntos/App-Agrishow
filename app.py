"""
app.py - Aplicacao Flask para sistema de compra de maquinas Agrishow.
Lida com: listagem de estoque, validacao em tempo real, criacao de pedidos
com upload de assinatura e geracao de ID unico.
"""
import os
import sqlite3
import random
import uuid
from datetime import datetime
from flask import (Flask, render_template, request, jsonify, send_from_directory,
                   redirect, url_for, flash, abort)
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

# Inicializa DB automaticamente na primeira execucao (importante para Render)
if not os.path.exists(DB_PATH):
    import init_db
    init_db.main()


# ---------------- DB helpers ----------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def estoque_disponivel(conn, sap, prazo):
    """Estoque inicial - soma de pedidos ACEITOS nesse SAP+prazo."""
    col = {15: 'estoque_inicial_15', 30: 'estoque_inicial_30', 60: 'estoque_inicial_60'}[prazo]
    row = conn.execute(f"SELECT {col} AS inicial FROM maquinas WHERE sap = ?", (sap,)).fetchone()
    if row is None:
        return None
    inicial = row['inicial'] or 0
    usado = conn.execute(
        "SELECT COALESCE(SUM(quantidade), 0) AS q FROM pedidos WHERE sap = ? AND prazo = ? AND status = 'ACEITO'",
        (sap, prazo)
    ).fetchone()['q']
    return max(0, inicial - usado)


def gerar_id_pedido():
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    rnd = f"{random.randint(0, 999):03d}"
    return f"PED-{ts}-{rnd}"


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT


# ---------------- Rotas ----------------
@app.route('/')
def index():
    conn = db()
    maquinas = conn.execute("SELECT * FROM maquinas ORDER BY modelo, sap").fetchall()
    # Calcula disponivel para cada maquina
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


@app.route('/api/estoque')
def api_estoque():
    """Retorna estoque disponivel para um SAP em todos os prazos (AJAX)."""
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
            erros.append('Dealer invalido.')
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

        m = conn.execute("SELECT modelo FROM maquinas WHERE sap = ?", (sap,)).fetchone()
        if m is None:
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

        # Salvar arquivo
        id_pedido = gerar_id_pedido()
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = secure_filename(f"{id_pedido}.{ext}")
        file.save(os.path.join(UPLOAD_DIR, filename))

        # Gravar pedido
        conn.execute("""INSERT INTO pedidos
                        (id, data_hora, dealer, funcionario, modelo, sap,
                         quantidade, prazo, anexo_filename, status)
                        VALUES (?,?,?,?,?,?,?,?,?,'ACEITO')""",
                     (id_pedido, datetime.now().isoformat(timespec='seconds'),
                      dealer, funcionario, m['modelo'], sap,
                      quantidade, prazo, filename))
        conn.commit()
        conn.close()
        flash(f'Pedido aceito com sucesso! ID: {id_pedido}', 'success')
        return redirect(url_for('sucesso', id_pedido=id_pedido))

    conn.close()
    return render_template('novo_pedido.html', dealers=dealers, maquinas=maquinas)


@app.route('/pedido/sucesso/<id_pedido>')
def sucesso(id_pedido):
    conn = db()
    p = conn.execute("SELECT * FROM pedidos WHERE id = ?", (id_pedido,)).fetchone()
    conn.close()
    if p is None:
        abort(404)
    return render_template('sucesso.html', pedido=p)


@app.route('/pedidos')
def listar_pedidos():
    conn = db()
    pedidos = conn.execute("SELECT * FROM pedidos ORDER BY data_hora DESC").fetchall()
    conn.close()
    return render_template('pedidos.html', pedidos=pedidos)


@app.route('/uploads/<path:filename>')
def download_anexo(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)


@app.errorhandler(413)
def too_large(e):
    flash(f'Arquivo muito grande. Limite: {MAX_MB}MB.', 'error')
    return redirect(url_for('novo_pedido'))


if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        print("Banco nao encontrado. Execute: python init_db.py")
        import sys
        sys.exit(1)
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=port, debug=debug)
