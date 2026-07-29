# =====================================================================
# services/email_service.py
# Nouveau fichier — à placer dans le dossier services/ de votre projet
# =====================================================================

import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger("email_service")

BREVO_SMTP_SERVER = os.getenv("BREVO_SMTP_SERVER", "smtp-relay.brevo.com")
BREVO_SMTP_PORT = int(os.getenv("BREVO_SMTP_PORT", "587"))
BREVO_SMTP_LOGIN = os.getenv("BREVO_SMTP_LOGIN")
BREVO_SMTP_PASSWORD = os.getenv("BREVO_SMTP_PASSWORD")
MAIL_FROM = os.getenv("MAIL_FROM", "noreply@cabinet.com")


class EmailSendingError(Exception):
    """Levée quand l'envoi SMTP échoue, pour que les routes puissent
    répondre proprement au lieu de planter avec une 500 brute."""
    pass


def _build_verification_email_html(full_name: str, code: str) -> str:
    safe_name = full_name or "Client"
    return f"""\
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#FFF4E1;font-family:'Public Sans',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#FFF4E1;padding:32px 0;">
    <tr>
      <td align="center">
        <table width="480" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 4px 16px rgba(26,49,44,.08);">
          <tr>
            <td style="background:#1A312C;padding:24px 32px;">
              <span style="color:#FFF4E1;font-size:19px;font-weight:600;">Cabinet Ben Said Belgacem</span>
            </td>
          </tr>
          <tr>
            <td style="padding:32px;">
              <p style="font-size:15px;color:#213A34;margin:0 0 16px;">Bonjour {safe_name},</p>
              <p style="font-size:14.5px;color:#5A6E67;line-height:1.6;margin:0 0 24px;">
                Merci pour votre inscription au Cabinet Ben Said Belgacem.
                Voici votre code de vérification :
              </p>
              <div style="text-align:center;margin:0 0 24px;">
                <span style="display:inline-block;background:#EFE3C9;color:#1A312C;font-family:'IBM Plex Mono',monospace;font-size:28px;font-weight:600;letter-spacing:6px;padding:14px 24px;border-radius:6px;">
                  {code}
                </span>
              </div>
              <p style="font-size:13px;color:#8A9A93;margin:0 0 8px;">
                Ce code expire dans 10 minutes.
              </p>
              <p style="font-size:13px;color:#8A9A93;margin:0;">
                Si vous n'êtes pas à l'origine de cette demande, vous pouvez ignorer cet email.
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 32px;background:#EFE3C9;">
              <span style="font-size:11.5px;color:#5A6E67;">Cabinet Ben Said Belgacem — Kébili, Tunisie</span>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def send_verification_email(email: str, full_name: str, code: str) -> None:
    """
    Envoie l'email de vérification contenant le code OTP via Brevo SMTP.
    Lève EmailSendingError en cas d'échec (SMTP down, auth invalide, etc.)
    pour que l'appelant puisse répondre proprement au client.
    """
    if not BREVO_SMTP_LOGIN or not BREVO_SMTP_PASSWORD:
        logger.error("Identifiants Brevo SMTP manquants dans les variables d'environnement.")
        raise EmailSendingError("Configuration SMTP manquante.")

    message = MIMEMultipart("alternative")
    message["Subject"] = "Vérification de votre adresse email"
    message["From"] = MAIL_FROM
    message["To"] = email

    text_part = (
        f"Bonjour {full_name},\n\n"
        f"Merci pour votre inscription au Cabinet Comptable.\n"
        f"Votre code de vérification est : {code}\n\n"
        f"Ce code expire dans 10 minutes.\n\n"
        f"Cordialement,\nL'équipe Cabinet Comptable"
    )
    html_part = _build_verification_email_html(full_name, code)

    message.attach(MIMEText(text_part, "plain"))
    message.attach(MIMEText(html_part, "html"))

    try:
        with smtplib.SMTP(BREVO_SMTP_SERVER, BREVO_SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(BREVO_SMTP_LOGIN, BREVO_SMTP_PASSWORD)
            server.sendmail(MAIL_FROM, [email], message.as_string())
    except smtplib.SMTPAuthenticationError as exc:
        logger.error("Échec d'authentification Brevo SMTP : %s", exc)
        raise EmailSendingError("Échec d'authentification auprès du serveur d'envoi.") from exc
    except smtplib.SMTPException as exc:
        logger.error("Erreur SMTP lors de l'envoi à %s : %s", email, exc)
        raise EmailSendingError("Impossible d'envoyer l'email de vérification pour le moment.") from exc
    except OSError as exc:
        # Timeout réseau, DNS, connexion refusée...
        logger.error("Erreur réseau lors de l'envoi SMTP à %s : %s", email, exc)
        raise EmailSendingError("Le service d'envoi d'email est temporairement indisponible.") from exc