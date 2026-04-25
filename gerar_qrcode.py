"""
gerar_qrcode.py - Gera QR Code apontando para a URL publica do sistema.

Uso:
    python gerar_qrcode.py https://seu-app.onrender.com
    python gerar_qrcode.py https://seu-app.onrender.com --saida meu_qr.png
    python gerar_qrcode.py   (modo interativo: pergunta a URL)
"""
import argparse
import os
import sys
import qrcode
from qrcode.constants import ERROR_CORRECT_H
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'qr_codes')


def gerar_qr_simples(url, saida):
    """QR Code minimalista, sem molduras."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=12,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='#1e3a8a', back_color='white').convert('RGB')
    img.save(saida, 'PNG', quality=95)


def gerar_qr_cartaz(url, saida, titulo='AGRISHOW', subtitulo='Sistema de Compra de Maquinas'):
    """QR Code dentro de um cartaz A4 com logo/titulo para imprimir e afixar."""
    # Gera o QR base
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=18,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color='#1e3a8a', back_color='white').convert('RGB')

    # Cartaz A4 proporcao (A4 = 210x297mm, aqui 1200x1697px)
    W, H = 1200, 1697
    cartaz = Image.new('RGB', (W, H), 'white')
    draw = ImageDraw.Draw(cartaz)

    # Faixa superior azul
    draw.rectangle([0, 0, W, 200], fill='#1e3a8a')

    # Tenta carregar fonte padrao do sistema
    try:
        font_titulo = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 80)
        font_sub = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 36)
        font_cta = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 52)
        font_url = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 26)
        font_step = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 30)
    except (OSError, IOError):
        # Fallback para fonte padrao
        font_titulo = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_cta = ImageFont.load_default()
        font_url = ImageFont.load_default()
        font_step = ImageFont.load_default()

    # Cabecalho
    draw.text((W // 2, 70), titulo, font=font_titulo, fill='white', anchor='mm')
    draw.text((W // 2, 150), subtitulo, font=font_sub, fill='#bfdbfe', anchor='mm')

    # Call-to-action
    draw.text((W // 2, 300), 'Escaneie para fazer um pedido', font=font_cta, fill='#1e3a8a', anchor='mm')
    draw.text((W // 2, 360), 'Use a camera do seu celular', font=font_step, fill='#64748b', anchor='mm')

    # QR Code centralizado
    qr_size = 750
    qr_img = qr_img.resize((qr_size, qr_size), Image.LANCZOS)
    qr_x = (W - qr_size) // 2
    qr_y = 430
    # Moldura leve ao redor do QR
    draw.rectangle([qr_x - 20, qr_y - 20, qr_x + qr_size + 20, qr_y + qr_size + 20],
                   outline='#e2e8f0', width=4)
    cartaz.paste(qr_img, (qr_x, qr_y))

    # URL em texto embaixo do QR
    draw.text((W // 2, qr_y + qr_size + 70), url, font=font_url, fill='#475569', anchor='mm')

    # Passos
    passos = [
        '1. Abra a camera do seu celular',
        '2. Aponte para o QR Code acima',
        '3. Toque na notificacao que aparecer',
    ]
    y = qr_y + qr_size + 180
    for p in passos:
        draw.text((W // 2, y), p, font=font_step, fill='#334155', anchor='mm')
        y += 50

    # Rodape
    draw.rectangle([0, H - 80, W, H], fill='#f1f5f9')
    draw.text((W // 2, H - 40), 'Agrishow - Sistema de Compra de Maquinas',
              font=font_sub, fill='#64748b', anchor='mm')

    cartaz.save(saida, 'PNG', quality=95)


def main():
    parser = argparse.ArgumentParser(description='Gera QR Code para o sistema Agrishow')
    parser.add_argument('url', nargs='?', help='URL publica do app (ex: https://agrishow.onrender.com)')
    parser.add_argument('--saida', default=None, help='Nome do arquivo PNG (padrao: qr_simples.png e qr_cartaz.png)')
    parser.add_argument('--apenas', choices=['simples', 'cartaz'], help='Gerar somente um tipo')
    args = parser.parse_args()

    url = args.url
    if not url:
        url = input("Cole a URL publica do seu app (ex: https://agrishow.onrender.com): ").strip()
    if not url:
        print("URL vazia. Abortando.")
        sys.exit(1)
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if args.apenas != 'cartaz':
        saida_simples = args.saida or os.path.join(OUTPUT_DIR, 'qr_simples.png')
        gerar_qr_simples(url, saida_simples)
        print(f"QR simples gerado: {saida_simples}")

    if args.apenas != 'simples':
        saida_cartaz = args.saida or os.path.join(OUTPUT_DIR, 'qr_cartaz.png')
        if args.apenas == 'cartaz' and args.saida:
            saida_cartaz = args.saida
        gerar_qr_cartaz(url, saida_cartaz)
        print(f"QR cartaz A4 gerado: {saida_cartaz}")

    print(f"\nURL codificada: {url}")
    print("Imprima o cartaz e afixe onde os Dealers possam escanear.")


if __name__ == '__main__':
    main()
