# 🚜 Agrishow — Sistema de Compra de Máquinas (versão Web Pública)

Aplicação Flask pronta para deploy no Render.com, acessível via QR Code. Baseada na versão local, com as mesmas funcionalidades (estoque em 15/30/60 dias, validação em tempo real, upload de assinatura, ID único) mas preparada para produção com Gunicorn.

---

## 🚀 Quick Start

### Para rodar LOCAL (teste):

```bash
pip install -r requirements.txt
python init_db.py
python app.py
# → http://localhost:5000
```

### Para publicar na web + gerar QR Code:

👉 Veja o guia completo em **[DEPLOY_RENDER.md](DEPLOY_RENDER.md)**

Resumo:
1. Subir o código para um repositório público no GitHub
2. No Render.com: **+ New → Web Service** → conectar o repositório → **Create**
3. Aguardar 3 minutos → copiar a URL gerada (`https://seu-app.onrender.com`)
4. Rodar `python gerar_qrcode.py https://seu-app.onrender.com`
5. Imprimir `qr_codes/qr_cartaz.png` em A4

---

## 📁 Estrutura

```
agrishow_app_prod/
├── app.py                 # Aplicação Flask (adaptada para produção)
├── init_db.py             # Inicializa SQLite com a base de máquinas
├── gerar_qrcode.py        # Gera QR Code + cartaz A4 imprimível
├── requirements.txt       # Dependências (inclui gunicorn e qrcode)
├── Procfile               # Comando de start para Render
├── render.yaml            # Blueprint do Render (deploy 1-clique)
├── .gitignore             # Ignora DB, uploads, caches
├── DEPLOY_RENDER.md       # Guia passo a passo de deploy
├── README.md              # Este arquivo
├── data/
│   ├── Agrishow_Machine_Control_Sheet.xlsm  # Planilha origem (21 máquinas)
│   └── agrishow.db        # (gerado) Banco SQLite
├── templates/             # HTML (Jinja2)
├── static/style.css       # Design responsivo
├── uploads/               # (gerado) Assinaturas anexadas
└── qr_codes/              # (gerado) QR simples + cartaz A4
```

---

## 🆕 O que mudou em relação à versão local

| Aspecto | Versão local | Versão produção |
|---|---|---|
| Servidor | `flask run` (debug) | `gunicorn` (2 workers) |
| Porta | Fixa `5000` | Vem da variável `$PORT` (Render define) |
| Secret Key | Hardcoded | Variável de ambiente `SECRET_KEY` |
| DB Init | Manual (`python init_db.py`) | Automático na 1ª execução |
| Debug | Ligado | Desligado (`FLASK_DEBUG=0`) |
| Blueprint Render | Não existia | `render.yaml` para deploy 1-clique |
| QR Code | Não existia | `gerar_qrcode.py` gera QR + cartaz A4 |

---

## 🛠️ Variáveis de ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `PORT` | `5000` | Porta de escuta (Render define automaticamente) |
| `SECRET_KEY` | `dev-key-change-me` | Chave da sessão Flask (gere uma aleatória em produção) |
| `FLASK_DEBUG` | `0` | `1` liga o modo debug |

---

## 📱 Como um Dealer acessa

1. Aponta a câmera do celular para o QR Code impresso
2. Toca na notificação que aparece
3. Navegador abre em `https://agrishow-pedidos.onrender.com`
4. Vê o Menu de Compra com estoque em tempo real
5. Clica em "+ Novo Pedido", preenche, anexa foto da assinatura
6. Recebe confirmação com ID único (`PED-AAAAMMDD-HHMMSS-XXX`)

---

## 🔐 Considerações de segurança

Para uso em produção real, considere:

- **Autenticação**: adicionar login por Dealer (Flask-Login) para evitar que qualquer pessoa com o QR faça pedidos
- **HTTPS**: já vem automático no Render
- **Rate limiting**: usar `Flask-Limiter` para evitar abuso
- **CSRF**: usar `Flask-WTF` em todos os formulários
- **Backup do DB**: exportar `agrishow.db` periodicamente
- **Revisão de pedidos**: adicionar fluxo de aprovação antes de baixar do estoque

Posso ajudar a implementar qualquer um desses em uma próxima iteração.

---

## ⚖️ Licença

Uso interno Agrishow.
