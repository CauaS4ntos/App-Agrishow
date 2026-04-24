# 🚀 Deploy no Render com Login Admin + Emails

Versão **v3** do sistema, com:
- Histórico protegido por login de admin
- Notificações por email (Gmail SMTP) ao criar/cancelar pedidos
- Auditoria de cancelamento (quem cancelou, quando)
- Rate limit no login

---

## 1. Preparar conta Gmail para envio de emails

### 1.1 Criar ou usar uma conta Gmail dedicada

Recomendação: use uma conta exclusiva para o sistema, tipo `agrishow.sistema@gmail.com`. **Não use sua conta pessoal** — a senha de app dá acesso total ao envio.

### 1.2 Ativar 2FA (obrigatório para gerar senha de app)

1. Vá em https://myaccount.google.com/security
2. Em "Como fazer login no Google" → ative **Verificação em duas etapas**
3. Siga o passo a passo (precisa de um celular)

### 1.3 Gerar senha de app

1. Acesse https://myaccount.google.com/apppasswords
2. Em "Nome do app", digite: `Agrishow Render`
3. Clique em **Criar**
4. O Google vai gerar uma senha de 16 caracteres (tipo `abcd efgh ijkl mnop`)
5. **Copie essa senha SEM os espaços** → ficará `abcdefghijklmnop`
6. Guarde com segurança — você não vai conseguir vê-la de novo

---

## 2. Atualizar o código no GitHub

1. Substitua no seu repositório os arquivos:
   - `app.py`
   - `email_utils.py` (novo)
   - `init_db.py`
   - `templates/base.html`
   - `templates/login.html` (novo)
   - `templates/pedidos.html`
   - `static/style.css` (ou adicione `style_admin.css` ao final do existente)

2. Commit message sugerida:
   ```
   feat: sistema de login admin + notificações por email
   ```

---

## 3. Configurar variáveis de ambiente no Render

No painel do Render → seu serviço → **Environment** → adicione:

| Variável | Valor | Observação |
|---|---|---|
| `ADMIN_USERS` | `joao@agrishow.com:SenhaForte123\|maria@agrishow.com:Outra456` | Pares email:senha separados por `\|` (pipe). Sem espaços |
| `SMTP_SERVER` | `smtp.gmail.com` | Fixo |
| `SMTP_PORT` | `587` | Fixo |
| `SMTP_USER` | `agrishow.sistema@gmail.com` | Email da conta Gmail criada no passo 1 |
| `SMTP_PASSWORD` | `abcdefghijklmnop` | Senha de app de 16 chars, sem espaços |
| `EMAIL_FROM` | `Agrishow Sistema <agrishow.sistema@gmail.com>` | Como aparece no remetente |
| `APP_URL` | `https://agrishow-pedidos.onrender.com` | URL pública do seu app |
| `SESSION_HOURS` | `8` | (opcional) Timeout da sessão em horas |

**Importante sobre a senha do admin:**
- Cada admin no `ADMIN_USERS` é `email:senha` sem espaços
- Separador entre admins é `|` (pipe, NÃO vírgula)
- Exemplo com 3 admins:
  ```
  admin@agrishow.com:Sen@123|gestor@agrishow.com:G35t0r!|diretor@agrishow.com:D1retor#
  ```
- Use senhas fortes e únicas para o sistema — NÃO reutilize senhas pessoais

Após configurar, clique em **Save** no Render. Ele redeploya automaticamente em ~2 minutos.

---

## 4. Testar após o deploy

### 4.1 Teste público (sem login)

1. Acesse `https://agrishow-pedidos.onrender.com`
2. Deve ver o Menu de Compra normalmente
3. Tente acessar `/pedidos` — deve redirecionar para `/login`

### 4.2 Teste de login

1. Clique em **🔐 Admin** no canto superior direito
2. Entre com um dos emails e senhas configurados em `ADMIN_USERS`
3. Deve redirecionar para o Histórico

### 4.3 Teste de criação + email

1. **Faça logout** (clique em Sair)
2. Crie um pedido normal (simulando um Dealer)
3. Dentro de ~10 segundos, **todos os admins** devem receber um email com os dados do pedido

### 4.4 Teste de cancelamento + email

1. Logue como admin
2. Vá em Histórico, clique **Cancelar** em um pedido
3. Todos os admins recebem email de cancelamento
4. O estoque é liberado automaticamente

---

## 5. Gerenciar admins depois

### Adicionar novo admin
1. No Render → Environment → `ADMIN_USERS`
2. Edite para adicionar `|novo@email.com:SenhaNova`
3. Save → espera redeploy (2 min)
4. Novo admin já pode fazer login

### Remover admin
1. Edite `ADMIN_USERS` e retire o par `email:senha`
2. Save → espera redeploy

### Trocar senha de admin
Mesmo processo: edita a senha na env var, save.

---

## 6. Diagnóstico de problemas

| Problema | Causa provável | Solução |
|---|---|---|
| Email não chega | `SMTP_PASSWORD` errada | Regenere a senha de app no Gmail e atualize |
| Email vai para spam | Gmail marcando conta nova | Adicione `agrishow.sistema@gmail.com` nos contatos dos admins |
| Login funciona mas `/pedidos` dá erro | Banco sem colunas `cancelado_por`/`cancelado_em` | Apague `data/agrishow.db` no Render Shell e redeploya |
| "Muitas tentativas falhas" e eu sou admin legítimo | Rate limit bloqueou | Espera 5 minutos ou redeploya (reseta a memória) |
| Emails chegam duplicados | Múltiplos workers do Gunicorn | Normal — cada worker tenta enviar. Pode reduzir para 1 worker se for crítico |
| Admin vê "SMTP nao configurado" no log | Esqueceu de setar `SMTP_USER` | Confira as env vars no Render |

---

## 7. Segurança — avisos importantes

- **As senhas dos admins ficam em texto puro no Render**. Qualquer pessoa com acesso ao painel pode vê-las. Se isso for problema, migre para Opção B (tabela no banco com bcrypt).
- **Rate limit é por processo**: se o Render tiver múltiplos workers, cada um conta separadamente. Para rate limit global, precisaria Redis.
- **Sessões duram 8h**: depois disso o admin precisa logar de novo. Configurável via `SESSION_HOURS`.
- **HTTPS automático** no Render — tudo trafega criptografado.

---

## 8. Próximos passos possíveis

Melhorias futuras que o sistema já está preparado para receber:
- Migrar `ADMIN_USERS` para tabela `admins` com bcrypt (Opção B)
- Adicionar filtros no histórico (por dealer, período, status)
- Exportar histórico para Excel
- Assinatura desenhada no celular (canvas)
- Identidade visual LiuGong/Agrishow quando você enviar o PowerPoint
