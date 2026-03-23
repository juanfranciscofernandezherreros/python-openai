"""
notifications.py
----------------
Sistema de notificaciones y envío de emails para el generador de artículos.

Responsabilidades:
- Enviar emails HTML via SMTP con autenticación STARTTLS.
- Centralizar la impresión de mensajes de log en consola y el envío opcional
  de emails de notificación según el nivel (``info``, ``success``, ``warning``,
  ``error``) y la configuración de ``NOTIFY_VERBOSE``.

Dependencias de entorno (todas opcionales para el envío de emails):
    ``SEND_EMAILS``, ``SMTP_HOST``, ``SMTP_PORT``, ``SMTP_USER``,
    ``SMTP_PASS``, ``FROM_EMAIL``, ``NOTIFY_EMAIL``.

Si alguna de las variables SMTP no está configurada, las funciones de este
módulo simplemente imprimen en consola sin lanzar excepciones.
"""
from __future__ import annotations

import base64
import smtplib
import sys
from email import policy as _email_policy
from email.message import EmailMessage

import config
from utils import html_escape, now_utc


def send_notification_email(subject: str, html_body: str, text_body: str = None):
    """Envía un email de notificación via SMTP con soporte STARTTLS.

    El email se envía en formato multipart (texto plano + HTML). Usa
    :class:`~email.message.EmailMessage` con ``policy=email.policy.SMTP``
    para codificar automáticamente los encabezados no ASCII (RFC 2047).

    Para contraseñas con caracteres no ASCII, realiza un fallback a
    ``AUTH PLAIN`` con codificación Base64.

    Si ``SEND_EMAILS`` es ``False`` o falta alguna variable SMTP, la función
    imprime un aviso en consola y devuelve ``False`` sin lanzar excepciones.

    Args:
        subject:   Asunto del email.
        html_body: Cuerpo del email en formato HTML.
        text_body: Cuerpo alternativo en texto plano (por defecto: mensaje genérico).

    Returns:
        ``True`` si el email se envió correctamente; ``False`` en caso contrario.
    """
    if not config.SEND_EMAILS:
        print("ℹ️  Envío de emails desactivado (SEND_EMAILS=false). Se omite el envío.")
        return False
    if not all([config.SMTP_HOST, config.SMTP_PORT, config.SMTP_USER, config.SMTP_PASS, config.FROM_EMAIL, config.TO_EMAIL]):
        print("⚠️  Faltan variables SMTP para enviar el correo. Se omite el envío.")
        return False
    try:
        msg = EmailMessage(policy=_email_policy.SMTP)
        msg["Subject"] = subject
        msg["From"] = config.FROM_EMAIL
        msg["To"] = config.TO_EMAIL
        text_body = text_body or "Notificación del proceso."
        msg.set_content(text_body, charset="utf-8")
        msg.add_alternative(html_body, subtype="html", charset="utf-8")
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT,
                          local_hostname="localhost") as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            try:
                smtp.login(config.SMTP_USER, config.SMTP_PASS)
            except UnicodeEncodeError:
                auth = f"\0{config.SMTP_USER}\0{config.SMTP_PASS}".encode("utf-8")
                auth_b64 = base64.b64encode(auth).decode("ascii")
                code, resp = smtp.docmd("AUTH", f"PLAIN {auth_b64}")
                if code != 235:
                    raise smtplib.SMTPAuthenticationError(code, resp)
            smtp.send_message(msg)
        print(f"📧 Notificación enviada a {config.TO_EMAIL}: {subject}")
        return True
    except Exception as e:
        print(f"❌ Error enviando el correo: {e}", file=sys.stderr)
        return False

def notify(subject: str, message: str, level: str = "info", always_email: bool = True):
    """Centraliza la impresión de mensajes en consola y el envío de notificaciones por email.

    Imprime siempre el mensaje en consola con formato ``{emoji} [{timestamp_UTC}] {subject} :: {message}``.
    Envía un email si se cumple alguna de estas condiciones:

    - ``always_email=True`` (valor por defecto).
    - ``NOTIFY_VERBOSE=True`` (configuración global).
    - El nivel es ``"error"`` o ``"warning"`` (siempre se notifican los problemas).

    Prefijos de emoji por nivel:
        ``info`` → ℹ️  | ``success`` → ✅  | ``warning`` → ⚠️  | ``error`` → ❌

    Args:
        subject:      Asunto corto del evento (se usa también como asunto del email).
        message:      Descripción detallada del evento.
        level:        Nivel del mensaje: ``"info"``, ``"success"``, ``"warning"`` o ``"error"``.
        always_email: Si ``True``, siempre intenta enviar email independientemente de
                      ``NOTIFY_VERBOSE``. Por defecto ``True``.
    """
    stamp = now_utc().isoformat()
    prefix = {"info":"ℹ️","success":"✅","warning":"⚠️","error":"❌"}.get(level, "ℹ️")
    line = f"{prefix} [{stamp}] {subject} :: {message}"
    print(line)
    should_email = always_email or config.NOTIFY_VERBOSE or (level in ("error","warning"))
    if should_email:
        html = f"<p><b>{html_escape(subject)}</b></p><p>{html_escape(message)}</p><p><small>{stamp} UTC</small></p>"
        send_notification_email(subject=f"[{level.upper()}] {subject}", html_body=html, text_body=f"{subject}\n\n{message}\n\n{stamp} UTC")
