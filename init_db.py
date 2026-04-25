"""
init_db.py — Cria as tabelas e popula o banco PostgreSQL (Supabase).

Uso local (uma única vez, para criar as tabelas no Supabase):
    python init_db.py

O script lê a variável DATABASE_URL do arquivo .env ou do ambiente.
"""
import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DEALERS = [
    'CEQUIP', 'DAMAQ', 'JUMASA', 'JUMASA NORTE', 'MEVOS', 'MPM',
    'NORDESTE', 'PRIORI', 'RR', 'SARANDI', 'SERPEMA', 'TRACSUL', 'TRACTORBEL'
]

# Dados das máquinas (fallback caso não haja Excel)
MAQUINAS = [
    ('4160D', '35F01190003B001', 0,  8,  57),
    ('6612E', '23F00700020B003', 15, 0,   0),
    ('6612E', '23F00700022B002', 39, 0,   0),
    ('818H',  '60F01100006B002',  0, 0,  10),
    ('835T',  '62F02200001B001',  8, 0, 117),
    ('835T',  '62F02200002B001', 11, 0,   0),
    ('838T',  '62F02310001B001',  5, 0,   0),
    ('848T',  '64F08560014B001',  6, 0,   0),
    ('908E',  '06F0187C032B001', 10, 18,  18),
    ('908E',  '06F0187C049B001', 20, 0,   0),
    ('913E',  '08F00550010B002',  0, 5,  16),
    ('913E',  '08F00550011B002',  0, 25,  0),
    ('915E',  '08F00630020B001',  1, 0,  42),
    ('915E',  '08F00630021B001',  3, 2,  20),
    ('915E',  '08F00630022B001',  1, 2,   0),
    ('915E',  '08F00630023B001',  4, 1,  10),
    ('922E',  '10F0084C075B001',  0, 6,  26),
    ('922E',  '10F0084C076B001',  0, 6,   6),
    ('922E',  '10F0084C077B001',  0, 0,  35),
]

# ---------------- SCHEMA ----------------
def criar_schema(cur):
    """Cria as tabelas no PostgreSQL (não faz nada se já existirem)."""

    # DIFERENÇA DO SQLITE: PostgreSQL usa SERIAL em vez de INTEGER AUTOINCREMENT
    cur.execute("""
        CREATE TABLE IF NOT EXISTS maquinas (
            id                 SERIAL PRIMARY KEY,
            modelo             TEXT NOT NULL,
            sap                TEXT UNIQUE NOT NULL,
            estoque_inicial_15 INTEGER DEFAULT 0,
            estoque_inicial_30 INTEGER DEFAULT 0,
            estoque_inicial_60 INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS dealers (
            id   SERIAL PRIMARY KEY,
            nome TEXT UNIQUE NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id              TEXT PRIMARY KEY,
            data_hora       TEXT NOT NULL,
            dealer          TEXT NOT NULL,
            funcionario     TEXT NOT NULL,
            modelo          TEXT NOT NULL,
            sap             TEXT NOT NULL,
            quantidade      INTEGER NOT NULL,
            prazo           INTEGER NOT NULL,
            anexo_filename  TEXT NOT NULL,
            status          TEXT DEFAULT 'ACEITO'
        )
    """)

    print("✅ Tabelas criadas (ou já existiam)")

# ---------------- DEALERS ----------------
def popular_dealers(cur):
    """Insere dealers ignorando duplicatas."""
    for d in DEALERS:
        # DIFERENÇA DO SQLITE: PostgreSQL usa ON CONFLICT em vez de INSERT OR IGNORE
        cur.execute(
            "INSERT INTO dealers (nome) VALUES (%s) ON CONFLICT (nome) DO NOTHING",
            (d,)
        )
    print(f"✅ {len(DEALERS)} dealers inseridos (duplicatas ignoradas)")

# ---------------- MÁQUINAS ----------------
def popular_maquinas(cur):
    """Insere/atualiza máquinas com UPSERT nativo do PostgreSQL."""
    for modelo, sap, e15, e30, e60 in MAQUINAS:
        # DIFERENÇA DO SQLITE: PostgreSQL tem UPSERT nativo com ON CONFLICT DO UPDATE
        cur.execute("""
            INSERT INTO maquinas (modelo, sap, estoque_inicial_15, estoque_inicial_30, estoque_inicial_60)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (sap) DO UPDATE SET
                modelo             = EXCLUDED.modelo,
                estoque_inicial_15 = EXCLUDED.estoque_inicial_15,
                estoque_inicial_30 = EXCLUDED.estoque_inicial_30,
                estoque_inicial_60 = EXCLUDED.estoque_inicial_60
        """, (modelo, sap, e15, e30, e60))

    print(f"✅ {len(MAQUINAS)} máquinas inseridas/atualizadas")

# ---------------- MAIN ----------------
def main():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("❌ ERRO: variável DATABASE_URL não encontrada.")
        print("   Crie um arquivo .env com: DATABASE_URL=postgresql://...")
        return

    print(f"🔗 Conectando ao banco...")
    conn = psycopg2.connect(db_url, cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()

    criar_schema(cur)
    popular_dealers(cur)
    popular_maquinas(cur)

    conn.commit()

    # Confirma o que foi criado
    cur.execute("SELECT COUNT(*) AS total FROM maquinas")
    total_m = cur.fetchone()['total']
    cur.execute("SELECT COUNT(*) AS total FROM dealers")
    total_d = cur.fetchone()['total']

    print(f"\n🎉 Banco pronto: {total_m} máquinas | {total_d} dealers")
    conn.close()

if __name__ == '__main__':
    main()
