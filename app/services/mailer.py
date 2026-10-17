"""Envío de correo por SMTP (RF-028). Configuración en Config.MAIL_*."""
import logging
import smtplib
from email.message import EmailMessage

from flask import current_app

log = logging.getLogger(__name__)


def send_mail(to, subject, body):
    """Envía un correo de texto. Devuelve True si se envió (o se mostró en consola en desarrollo)."""
    cfg = current_app.config
    if not cfg.get('MAIL_SERVER'):
        if cfg.get('APP_ENV') == 'development' or cfg.get('TESTING'):
            print(f"[MAIL] (sin MAIL_SERVER, solo consola) Para: {to}\nAsunto: {subject}\n{body}")
            return True
        log.warning('No se envió el correo "%s": falta configurar MAIL_SERVER.', subject)
        return False
    msg = EmailMessage()
    msg['From'] = cfg.get('MAIL_FROM')
    msg['To'] = to
    msg['Subject'] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(cfg['MAIL_SERVER'], cfg.get('MAIL_PORT', 587), timeout=15) as smtp:
            if cfg.get('MAIL_USE_TLS', True):
                smtp.starttls()
            if cfg.get('MAIL_USERNAME'):
                smtp.login(cfg['MAIL_USERNAME'], cfg.get('MAIL_PASSWORD') or '')
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError):
        log.exception('Error enviando correo "%s"', subject)
        return False
