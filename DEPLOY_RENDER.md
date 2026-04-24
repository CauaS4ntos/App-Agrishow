# 🚀 Guia de Deploy no Render.com + QR Code

Este guia leva você do zero até um site público acessível via QR Code, **100% gratuito**.

---

## 📋 Visão geral (10 minutos)

1. Criar conta gratuita no GitHub (se ainda não tiver)
2. Criar conta gratuita no Render.com
3. Subir o código para um repositório GitHub
4. Conectar o Render ao repositório → deploy automático
5. Gerar o QR Code com a URL recebida
6. Imprimir e distribuir

---

## 🌐 PARTE 1 — Subir o código para o GitHub

### 1.1 Criar conta no GitHub

Vá em https://github.com/signup e crie uma conta (se já tiver, pule).

### 1.2 Criar um repositório

1. No canto superior direito: **+ → New repository**
2. Nome do repositório: `agrishow-pedidos` (pode ser qualquer nome)
3. Deixe **Public** (Render grátis exige isso)
4. **NÃO** marque "Add README", "Add .gitignore" ou "License" — já temos esses arquivos
5. Clique em **Create repository**

### 1.3 Subir os arquivos

**Opção fácil (sem linha de comando):**

1. Na página do repositório recém-criado, clique no link **"uploading an existing file"**
2. **Arraste TODA a pasta `agrishow_app_prod`** (sem a pasta, ou seja, os arquivos diretamente) para o GitHub
3. Arquivos que devem estar presentes:
   - `app.py`
   - `init_db.py`
   - `gerar_qrcode.py`
   - `requirements.txt`
   - `Procfile`
   - `render.yaml`
   - `.gitignore`
   - Pastas `templates/`, `static/`, `data/`, `uploads/`
4. Escreva uma mensagem como "Commit inicial" e clique em **Commit changes**

**Opção via linha de comando (se preferir):**

```bash
cd agrishow_app_prod
git init
git add .
git commit -m "Commit inicial"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/agrishow-pedidos.git
git push -u origin main
```

---

## ☁️ PARTE 2 — Deploy no Render

### 2.1 Criar conta

1. Vá em https://render.com
2. Clique em **Get Started** e entre com sua conta do GitHub (login mais rápido)
3. Autorize o Render a ver seus repositórios

### 2.2 Criar o serviço Web

1. No dashboard do Render, clique em **+ New → Web Service**
2. Em **Connect a repository**, localize `agrishow-pedidos` → clique em **Connect**
3. Preencha:

| Campo | Valor |
|---|---|
| **Name** | `agrishow-pedidos` (vira parte da URL) |
| **Region** | `Oregon (US West)` ou `Ohio (US East)` |
| **Branch** | `main` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120` |
| **Instance Type** | **Free** |

4. (Opcional) Em **Advanced** → **Environment Variables**:
   - `SECRET_KEY` = uma string longa aleatória (Render gera automaticamente se você criou via `render.yaml`)
   - `FLASK_DEBUG` = `0`
5. Clique em **Create Web Service**

### 2.3 Aguardar o deploy (~3-5 minutos)

O Render vai:
- Baixar o código
- Instalar dependências
- Iniciar o Gunicorn
- Mostrar os logs em tempo real

Quando aparecer **"Your service is live 🎉"** no topo, acesse a URL mostrada (ex: `https://agrishow-pedidos.onrender.com`).

---

## 📱 PARTE 3 — Gerar o QR Code

Depois que o site estiver no ar com a URL pública, gere o QR Code localmente:

### 3.1 Instalar dependência (se ainda não fez)

```bash
pip install "qrcode[pil]"
```

### 3.2 Rodar o script

```bash
python gerar_qrcode.py https://agrishow-pedidos.onrender.com
```

Isso cria 2 arquivos em `qr_codes/`:

- **`qr_simples.png`** — só o QR Code, para embutir em e-mails, slides ou sites
- **`qr_cartaz.png`** — cartaz A4 pronto para imprimir (título Agrishow, QR grande, URL embaixo, passo a passo)

### 3.3 Modo interativo

Sem argumentos, o script pergunta a URL:

```bash
python gerar_qrcode.py
```

### 3.4 Gerar somente um tipo

```bash
python gerar_qrcode.py https://agrishow-pedidos.onrender.com --apenas cartaz
python gerar_qrcode.py https://agrishow-pedidos.onrender.com --apenas simples
```

---

## ⚠️ Observações importantes sobre o plano Free do Render

- O serviço **hiberna após 15 minutos sem acessos**. O primeiro acesso depois disso demora ~30 segundos para "acordar" (chamado *cold start*).
- Depois de acordado, fica rápido normalmente.
- **Solução para demonstrações ao vivo**: 1-2 minutos antes do evento, abra a URL no navegador para "pré-aquecer".
- **Solução permanente**: upgrade para o plano Starter (US$ 7/mês) — não hiberna.

### Armazenamento de dados

- O SQLite (`data/agrishow.db`) e os anexos (`uploads/`) ficam em disco persistente graças ao bloco `disk:` no `render.yaml` (1 GB grátis).
- Se criar o serviço manualmente SEM o `render.yaml`, precisa adicionar um disco em **Settings → Disks** → **Add Disk** → mount path `/opt/render/project/src/data` e outro em `/opt/render/project/src/uploads`.
- **Atenção**: o plano Free não oferece disco persistente em alguns casos novos. Se isso for limitação, os dados resetam a cada deploy. Para persistência garantida, migre para o plano Starter OU use um banco externo (Render oferece PostgreSQL free tier).

---

## 🔄 Atualizar a aplicação depois

Qualquer `git push` para o branch `main` dispara deploy automático no Render. Fluxo típico:

```bash
# Editar código localmente
git add .
git commit -m "Adicionado campo X"
git push
# → Render detecta e faz redeploy automaticamente em ~3 minutos
```

---

## 🐞 Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| Build falha com "ModuleNotFoundError" | Dependência faltando | Verifique `requirements.txt` — ela deve listar todos os `import` do código |
| "Application failed to respond" | Porta errada | Confirme que `Procfile` usa `$PORT` (variável do Render) |
| Dados somem a cada deploy | Disco não persistente | Use `render.yaml` com bloco `disk:` OU migre para Postgres |
| Upload falha (413 Payload too large) | Arquivo > 10 MB | Render aceita até 100 MB, mas nossa app limita a 10 MB em `app.py` (MAX_MB) |
| Primeiro acesso lento | Cold start do plano Free | Normal — 15-30s na primeira requisição após hibernação |

---

## 📊 Alternativa: PythonAnywhere

Se preferir PythonAnywhere (também gratuito):

1. Crie conta em https://www.pythonanywhere.com
2. **Web → Add new web app → Flask → Python 3.10**
3. Faça upload dos arquivos via **Files** ou clone do GitHub via console
4. Em **Web → Code**: aponte "Source code" para a pasta do projeto
5. Edite `wsgi.py` (gerado automaticamente) para importar seu `app`:
   ```python
   import sys
   path = '/home/SEU_USUARIO/agrishow_app_prod'
   if path not in sys.path:
       sys.path.insert(0, path)
   from app import app as application
   ```
6. Clique em **Reload** no topo da aba Web
7. Sua URL será `https://SEU_USUARIO.pythonanywhere.com`
8. Rode `python gerar_qrcode.py https://SEU_USUARIO.pythonanywhere.com`

**Limitação do plano free:** somente o domínio `.pythonanywhere.com` (não aceita domínio customizado no plano gratuito), e o app hiberna após 3 meses de inatividade (renovável com 1 clique).

---

## 🎯 Checklist final

- [ ] Código no GitHub
- [ ] Serviço Web criado no Render
- [ ] Deploy concluído com sucesso (status "Live")
- [ ] URL pública testada no celular (conexão 4G, não Wi-Fi do escritório — para confirmar que é realmente pública)
- [ ] Formulário de pedido testado ponta a ponta via celular
- [ ] QR Code gerado com a URL correta
- [ ] Cartaz A4 impresso e afixado no local de uso
