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
 
# Inicializa DB automaticamente
if not os.path.exists(DB_PATH):
    import init_db
    init_db.main()
 
# ---------------- DB ----------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
 
def estoque_disponivel(conn, sap, prazo):
    col = {15: 'estoque_inicial_15', 30: 'estoque_inicial_30', 60: 'estoque_inicial_60'}[prazo]
 
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
 
def gerar_id_pedido():
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    rnd = f"{random.randint(0, 999):03d}"
    return f"PED-{ts}-{rnd}"
 
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT
 
# ---------------- ROTAS ----------------
 
@app.route('/')
def index():
    conn = db()
    maquinas = conn.execute("SELECT * FROM maquinas").fetchall()
 
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
 
    dealers = [r['nome'] for r in conn.execute("SELECT nome FROM dealers").fetchall()]
    conn.close()
 
    return render_template('index.html',
                           linhas=linhas,
                           total_15=total_15,
                           total_30=total_30,
                           total_60=total_60,
                           total_geral=total_15 + total_30 + total_60,
                           dealers=dealers)
 
# ---------------- NOVO PEDIDO ----------------
 
@app.route('/pedido/novo', methods=['GET', 'POST'])
def novo_pedido():
    conn = db()
 
    dealers = [r['nome'] for r in conn.execute("SELECT nome FROM dealers").fetchall()]
    maquinas = conn.execute("SELECT modelo, sap FROM maquinas").fetchall()
 
    if request.method == 'POST':
        dealer = request.form.get('dealer')
        funcionario = request.form.get('funcionario')
        sap = request.form.get('sap')
        quantidade = int(request.form.get('quantidade'))
        prazo = int(request.form.get('prazo'))
 
        file = request.files.get('assinatura')
 
        if quantidade > estoque_disponivel(conn, sap, prazo):
            flash('Estoque insuficiente.', 'error')
            return redirect(url_for('novo_pedido'))
 
        id_pedido = gerar_id_pedido()
        filename = secure_filename(f"{id_pedido}.{file.filename.split('.')[-1]}")
        file.save(os.path.join(UPLOAD_DIR, filename))
 
        conn.execute("""
            INSERT INTO pedidos
            (id, data_hora, dealer, funcionario, modelo, sap, quantidade, prazo, anexo_filename, status)
            VALUES (?,?,?,?,?,?,?,?,?,'ACEITO')
        """, (id_pedido, datetime.now().isoformat(),
              dealer, funcionario, "", sap,
              quantidade, prazo, filename))
 
        conn.commit()
        conn.close()
 
        return redirect(url_for('sucesso', id_pedido=id_pedido))
 
    conn.close()
    return render_template('novo_pedido.html', dealers=dealers, maquinas=maquinas)
 
# ---------------- CANCELAR PEDIDO ----------------
 
@app.route('/pedido/cancelar/<id_pedido>', methods=['POST'])
def cancelar_pedido(id_pedido):
    conn = db()
 
    pedido = conn.execute("SELECT * FROM pedidos WHERE id = ?", (id_pedido,)).fetchone()
 
    if not pedido:
        conn.close()
        abort(404)
 
    conn.execute("""
        UPDATE pedidos
        SET status = 'CANCELADO'
        WHERE id = ?
    """, (id_pedido,))
 
    conn.commit()
    conn.close()
 
    flash('Pedido cancelado com sucesso!', 'success')
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
    flash('Arquivo muito grande.', 'error')
    return redirect(url_for('novo_pedido'))
 
# ---------------- RUN ----------------
 
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
