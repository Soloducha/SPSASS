"""Envio del email de invitacion a un tenant (T2).

No es un canal de alerta: `EmailChannel` esta atado a `Alert`/`AlertRule`, asi
que aqui va un sender independiente que reutiliza la misma configuracion SMTP de
`Settings`. Se manda en un thread (`asyncio.to_thread`) porque smtplib es
bloqueante y el caller vive en el event loop de FastAPI.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.models.tenant_member import MemberRole

logger = get_logger(__name__)


class InvitationEmailError(RuntimeError):
    """Fallo al enviar el email de invitacion (SMTP no configurado o caido)."""


async def send_invitation_email(
    *,
    to_email: str,
    tenant_name: str,
    accept_url: str,
    role: MemberRole,
    inviter_name: str | None = None,
) -> None:
    """Envia la invitacion por SMTP.

    Args:
        to_email: Destinatario de la invitacion.
        tenant_name: Nombre del tenant al que se invita.
        accept_url: Link de aceptacion ya construido (`${WEB_URL}/accept-invitation/{token}`).
        role: Rol con el que la persona entra al tenant.
        inviter_name: Nombre de quien invita, si se conoce.

    Raises:
        InvitationEmailError: Si SMTP no esta configurado o el envio falla.
    """
    settings = get_settings()
    if not settings.smtp_enabled:
        raise InvitationEmailError(
            "SMTP no configurado (SMTP_HOST y SMTP_FROM requeridos)"
        )

    msg = _build_message(
        to_email=to_email,
        tenant_name=tenant_name,
        accept_url=accept_url,
        role=role,
        inviter_name=inviter_name,
    )

    try:
        await asyncio.to_thread(_send_smtp, msg, settings)
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning(
            "invitation_email_failed",
            to=to_email,
            tenant_name=tenant_name,
            error=str(exc),
        )
        raise InvitationEmailError(f"Error SMTP enviando invitacion: {exc}") from exc

    logger.info("invitation_email_sent", to=to_email, tenant_name=tenant_name)


def _build_message(
    *,
    to_email: str,
    tenant_name: str,
    accept_url: str,
    role: MemberRole,
    inviter_name: str | None,
) -> EmailMessage:
    """Arma el EmailMessage de la invitacion."""
    settings = get_settings()
    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to_email
    msg["Subject"] = f"Invitacion para unirte a {tenant_name} en SPSAAS"

    greeting = f"Hola {inviter_name}," if inviter_name else "Hola,"
    body_lines = [
        greeting,
        "",
        f"Te invitaron a unirte al tenant '{tenant_name}' de SPSAAS "
        f"con el rol '{role.value}'.",
        "",
        "Para aceptar la invitacion y crear tu acceso:",
        accept_url,
        "",
        "El enlace es de un solo uso y expira en breve. Si no esperabas esta",
        "invitacion, podes ignorar este mensaje.",
        "",
        "—",
        "Este es un mensaje automático de SPSAAS.",
    ]
    msg.set_content("\n".join(body_lines))
    return msg


def _send_smtp(msg: EmailMessage, settings: Settings) -> None:
    """Envia el email via SMTP (bloqueante, corre en thread)."""
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
        if settings.SMTP_STARTTLS:
            smtp.starttls()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)
