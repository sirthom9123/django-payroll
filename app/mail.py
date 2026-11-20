from django.core.exceptions import ImproperlyConfigured

RESEND_SMTP_HOST = "smtp.resend.com"
RESEND_SMTP_PORT = 587
RESEND_SMTP_USER = "resend"


def mail_config(debug, resend_api_key, from_email):
    if debug:
        return {
            "EMAIL_BACKEND": "django.core.mail.backends.console.EmailBackend",
            "DEFAULT_FROM_EMAIL": from_email or "webmaster@localhost",
        }
    if not resend_api_key:
        raise ImproperlyConfigured("RESEND_API_KEY is required when DEBUG is False.")
    if not from_email:
        raise ImproperlyConfigured("DEFAULT_FROM_EMAIL is required when DEBUG is False.")
    return {
        "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "EMAIL_HOST": RESEND_SMTP_HOST,
        "EMAIL_PORT": RESEND_SMTP_PORT,
        "EMAIL_USE_TLS": True,
        "EMAIL_HOST_USER": RESEND_SMTP_USER,
        "EMAIL_HOST_PASSWORD": resend_api_key,
        "DEFAULT_FROM_EMAIL": from_email,
    }
