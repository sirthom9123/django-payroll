from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from app.mail import mail_config


class MailConfigTests(SimpleTestCase):
    def test_debug_writes_email_to_the_log(self):
        config = mail_config(debug=True, resend_api_key="", from_email="")
        self.assertEqual(
            config["EMAIL_BACKEND"],
            "django.core.mail.backends.console.EmailBackend",
        )
        self.assertNotIn("EMAIL_HOST", config)

    def test_production_sends_through_resend(self):
        config = mail_config(debug=False, resend_api_key="re_test", from_email="payroll@example.com")
        self.assertEqual(
            config["EMAIL_BACKEND"],
            "django.core.mail.backends.smtp.EmailBackend",
        )
        self.assertEqual(config["EMAIL_HOST"], "smtp.resend.com")
        self.assertEqual(config["EMAIL_PORT"], 587)
        self.assertIs(config["EMAIL_USE_TLS"], True)
        self.assertEqual(config["EMAIL_HOST_USER"], "resend")
        self.assertEqual(config["EMAIL_HOST_PASSWORD"], "re_test")
        self.assertEqual(config["DEFAULT_FROM_EMAIL"], "payroll@example.com")

    def test_production_requires_the_api_key_and_sender(self):
        with self.assertRaises(ImproperlyConfigured):
            mail_config(debug=False, resend_api_key="", from_email="payroll@example.com")
        with self.assertRaises(ImproperlyConfigured):
            mail_config(debug=False, resend_api_key="re_test", from_email="")
