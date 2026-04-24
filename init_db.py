"""
init_db.py - Inicializa/atualiza SQLite com dados da planilha.
Versao final: compatível com Render + atualização de estoque (sem ON CONFLICT)
"""
import os
import sqlite3
from openpyxl import load_workbook

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'agrishow.db')
XLSX_PATH = os.path.join(BASE_DIR, 'data', 'Agrishow_Machine_Control_Sheet.xlsm')

DEALERS = [
    'CEQUIP', 'DAMAQ', 'JUMASA', 'JUMASA NORTE', 'MEVOS', 'MPM',
    'NORDESTE', 'PRIORI', 'RR', 'SARANDI', 'SERPEMA', 'TRACSUL', 'TRACTORBEL'
]


# ---------------- SCHEMA ----------------
def criar_schema(conn):
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS maquinas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        modelo TEXT NOT NULL,
        sap TEXT UNIQUE NOT NULL,
        estoque_inicial_15 INTEGER DEFAULT 0,
        estoque_inicial_30 INTEGER DEFAULT 0,
        estoque_inicial_60 INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS dealers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL
    );

    CREATE TABLE IF NOT EXISTS pedidos (
        id TEXT PRIMARY KEY,
        data_hora TEXT NOT NULL,
        dealer TEXT NOT NULL,
        funcionario TEXT NOT NULL,
        modelo TEXT NOT NULL,
        sap TEXT NOT NULL,
        quantidade INTEGER NOT NULL,
        prazo INTEGER NOT NULL CHECK(prazo IN (15, 30, 60)),
        anexo_filename TEXT NOT NULL,
        status TEXT DEFAULT 'ACEITO',
        cancelado_por TEXT,
        cancelado_em TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_pedidos_sap ON pedidos(sap);
    CREATE INDEX IF NOT EXISTS idx_pedidos_dealer ON pedidos(dealer);
    CREATE INDEX IF NOT EXISTS idx_pedidos_status ON pedidos(status);
    """)

    conn.commit()

    # garante colunas em bancos antigos
    for coluna in ['cancelado_por', 'cancelado_em']:
        try:
            c.execute(f"ALTER TABLE pedidos ADD COLUMN {coluna} TEXT")
        except sqlite3.OperationalError:
            pass

    conn.commit()


# ---------------- DEALERS ----------------
def popular_dealers(conn):
    c = conn.cursor()
    for d in DEALERS:
        c.execute("INSERT OR IGNORE INTO dealers (nome) VALUES (?)", (d,))
    conn.commit()


# ---------------- MAQUINAS (UPSERT MANUAL) ----------------
def popular_maquinas(conn):
    c = conn.cursor()

    def upsert_maquina(modelo, sap, e15, e30, e60):
        c.execute("DELETE FROM maquinas WHERE sap = ?", (sap,))
        c.execute("""
            INSERT INTO maquinas
            (modelo, sap, estoque_inicial_15, estoque_inicial_30, estoque_inicial_60)
            VALUES (?, ?, ?, ?, ?)
        """, (modelo, sap, int(e15), int(e30), int(e60)))

    # -------- SEM EXCEL --------
    if not os.path.exists(XLSX_PATH):
        print("Excel nao encontrado. Usando dados de exemplo.")

        exemplos = [
            ('4160D', '35F01190003B001', 0, 8, 57),
            ('6612E', '23F00700020B003', 15, 0, 0),
            ('6612E', '23F00700022B002', 39, 0, 0),
            ('818H', '60F01100006B002', 0, 0, 10),
            ('835T', '62F02200001B001', 8, 0, 117),
            ('835T', '62F02200002B001', 11, 0, 0),
            ('838T', '62F02310001B001', 5, 0, 0),
            ('848T', '64F08560014B001', 6, 0, 0),
            ('908E', '06F0187C032B001', 10, 18, 18),
            ('908E', '06F0187C049B001', 20, 0, 0),
        ]

        for m in exemplos:
            upsert_maquina(*m)

        conn.commit()
        return

    # -------- COM EXCEL --------
    wb = load_workbook(XLSX_PATH, keep_vba=True, data_only=False)
    ws = wb['Inicial']

    for row in ws.iter_rows(min_row=2, values_only=True):
        modelo, sap = row[0], row[1]

        if not modelo or not sap:
            continue

        e15 = row[2] or 0
        e30 = row[3] or 0
        e60 = row[4] or 0

        upsert_maquina(modelo, sap, e15, e30, e60)

    conn.commit()


# ---------------- MAIN ----------------
def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    criar_schema(conn)
    popular_dealers(conn)
    popular_maquinas(conn)

    total_m = conn.execute("SELECT COUNT(*) FROM maquinas").fetchone()[0]
    total_d = conn.execute("SELECT COUNT(*) FROM dealers").fetchone()[0]

    print(f"Banco atualizado: {total_m} maquinas | {total_d} dealers")

    conn.close()


if __name__ == '__main__':
    main()
