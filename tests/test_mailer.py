"""Envío de correo por SMTP (RF-028) sin red: smtplib.SMTP se reemplaza por un doble."""
import smtplib
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support import TEST_PASSWORD  # noqa: E402
from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.services import mailer  # noqa: E402


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.calls, self.sent = host, port, [], []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.calls.append('starttls')

    def login(self, user, password):
        self.calls.append(('login', user, password))

    def send_message(self, msg):
        self.sent.append(msg)


@pytest.fixture()
def app(tmp_path, monkeypatch):
    Config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path/'test_mail.db'}"
    app = create_app()
    app.config.update(TESTING=True)
    FakeSMTP.instances = []
    monkeypatch.setattr(mailer.smtplib, 'SMTP', FakeSMTP)
    return app


def test_without_server_only_console_in_dev_or_tests(app):
    with app.app_context():
        app.config.update(MAIL_SERVER=None)
        assert mailer.send_mail('a@example.com', 'Hola', 'cuerpo') is True
        app.config.update(TESTING=False, APP_ENV='production')
        assert mailer.send_mail('a@example.com', 'Hola', 'cuerpo') is False
    assert FakeSMTP.instances == []


def test_sends_with_tls_and_login(app):
    with app.app_context():
        app.config.update(MAIL_SERVER='smtp.example.com', MAIL_PORT=2525, MAIL_FROM='no-reply@example.com',
                          MAIL_USE_TLS=True, MAIL_USERNAME='bot', MAIL_PASSWORD=TEST_PASSWORD)
        assert mailer.send_mail('a@example.com', 'Asunto', 'Texto') is True
    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ('smtp.example.com', 2525)
    assert smtp.calls == ['starttls', ('login', 'bot', TEST_PASSWORD)]
    msg = smtp.sent[0]
    assert msg['To'] == 'a@example.com' and msg['Subject'] == 'Asunto' and 'Texto' in msg.get_content()


def test_no_tls_no_login_and_errors_return_false(app, monkeypatch):
    with app.app_context():
        app.config.update(MAIL_SERVER='smtp.example.com', MAIL_USE_TLS=False, MAIL_USERNAME=None)
        assert mailer.send_mail('a@example.com', 'S', 'B') is True
        assert FakeSMTP.instances[0].calls == []

        def boom(*a, **k):
            raise smtplib.SMTPConnectError(421, 'no')
        monkeypatch.setattr(mailer.smtplib, 'SMTP', boom)
        assert mailer.send_mail('a@example.com', 'S', 'B') is False
