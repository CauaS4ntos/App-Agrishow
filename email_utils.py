"""
email_utils.py - Envio de notificacoes via Gmail SMTP.
Roda em thread separada para nao bloquear requests do usuario.
"""
import os
import smtplib
import ssl
import threading
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
EMAIL_FROM = os.environ.get('EMAIL_FROM', SMTP_USER)
APP_URL = os.environ.get('APP_URL', '')


def _formatar_data(iso_str):
    """Converte '2026-04-24T14:30:22' em '24/04/2026 14:30:22'."""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime('%d/%m/%Y %H:%M:%S')
    except (ValueError, TypeError):
        return iso_str


def _template_html(titulo, cor_header, corpo, link_texto, link_url):
    """Template HTML comum para todos os emails."""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:Arial,sans-serif;background:#f1f5f9;">
  <table cellpadding="0" cellspacing="0" width="100%" style="background:#f1f5f9;padding:20px 0;">
    <tr><td align="center">
      <table cellpadding="0" cellspacing="0" width="600" style="background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.05);">
        <tr><td style="background:{cor_header};padding:24px 32px;color:white;">
          <div style="font-size:20px;font-weight:700;">Agrishow - Sistema de Pedidos</div>
          <div style="font-size:14px;opacity:0.9;margin-top:4px;">{titulo}</div>
        </td></tr>
        <tr><td style="padding:32px;">
          {corpo}
          <div style="margin-top:28px;text-align:center;">
            <a href="{link_url}" style="display:inline-block;background:#1e40af;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;">{link_texto}</a>
          </div>
        </td></tr>
        <tr><td style="background:#f8fafc;padding:16px 32px;color:#64748b;font-size:12px;text-align:center;border-top:1px solid #e2e8f0;">
          Enviado automaticamente pelo Sistema Agrishow.<br>
          Nao responda este email.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _corpo_pedido(pedido_dict):
    """Tabela HTML com os dados do pedido."""
    p = pedido_dict
    linhas = [
        ('ID', p.get('id', '—')),
        ('Data/Hora', _formatar_data(p.get('data_hora', ''))),
        ('Dealer', p.get('dealer', '—')),
        ('Funcionário', p.get('funcionario', '—')),
        ('Máquina', f"{p.get('modelo', '—')} — {p.get('sap', '—')}"),
        ('Quantidade', str(p.get('quantidade', '—'))),
        ('Prazo', f"{p.get('prazo', '—')} dias"),
    ]
    rows = ''.join(
        f'<tr><td style="padding:8px 0;color:#64748b;font-size:13px;">{k}</td>'
        f'<td style="padding:8px 0;text-align:right;font-weight:600;font-size:14px;">{v}</td></tr>'
        for k, v in linhas
    )
    return f"""<table cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;">
{rows}
</table>"""


def _enviar_sync(destinatarios, assunto, html):
    """Envio sincrono via SMTP. Chamado dentro da thread."""
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("SMTP nao configurado (SMTP_USER/SMTP_PASSWORD vazios). Email nao sera enviado.")
        return False
    if not destinatarios:
        logger.warning("Lista de destinatarios vazia. Email nao enviado.")
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = assunto
    msg['From'] = EMAIL_FROM
    msg['To'] = ', '.join(destinatarios)
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15) as server:
            server.starttls(context=ctx)
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        logger.info(f"Email enviado para {len(destinatarios)} destinatarios: {assunto}")
        return True
    except Exception as e:
        logger.error(f"Falha ao enviar email: {e}")
        return False


def _enviar_async(destinatarios, assunto, html):
    """Dispara envio em thread separada. Nao bloqueia o caller."""
    t = threading.Thread(
        target=_enviar_sync,
        args=(destinatarios, assunto, html),
        daemon=True
    )
    t.start()


def notificar_pedido_criado(pedido_dict, admins_emails):
    """Dispara email avisando que um novo pedido foi criado."""
    pid = pedido_dict.get('id', '???')
    dealer = pedido_dict.get('dealer', '???')
    assunto = f"[Agrishow] Novo pedido {pid} - {dealer}"
    link_url = f"{APP_URL}/pedidos" if APP_URL else "#"
    corpo = (
        '<div style="font-size:15px;color:#1e293b;margin-bottom:20px;">'
        'Um <strong style="color:#16a34a;">novo pedido</strong> foi registrado no sistema.'
        '</div>' + _corpo_pedido(pedido_dict)
    )
    html = _template_html(
        titulo='Novo pedido registrado',
        cor_header='#16a34a',
        corpo=corpo,
        link_texto='Ver no sistema',
        link_url=link_url,
    )
    _enviar_async(admins_emails, assunto, html)


def notificar_pedido_cancelado(pedido_dict, cancelado_por, admins_emails):
    """Dispara email avisando que um pedido foi cancelado."""
    pid = pedido_dict.get('id', '???')
    dealer = pedido_dict.get('dealer', '???')
    assunto = f"[Agrishow] Pedido {pid} cancelado - {dealer}"
    link_url = f"{APP_URL}/pedidos" if APP_URL else "#"
    corpo = (
        '<div style="font-size:15px;color:#1e293b;margin-bottom:20px;">'
        f'O pedido abaixo foi <strong style="color:#dc2626;">cancelado</strong> por '
        f'<strong>{cancelado_por}</strong>.'
        '</div>' + _corpo_pedido(pedido_dict) +
        '<div style="margin-top:16px;padding:12px;background:#fef2f2;border-left:4px solid #dc2626;'
        'color:#991b1b;font-size:13px;">'
        'O estoque da maquina foi liberado automaticamente.'
        '</div>'
    )
    html = _template_html(
        titulo='Pedido cancelado',
        cor_header='#dc2626',
        corpo=corpo,
        link_texto='Ver no sistema',
        link_url=link_url,
    )
    _enviar_async(admins_emails, assunto, html)
