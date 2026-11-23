"""Password-reset delivery through authenticated TLS SMTP."""
import os
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlparse


def configured():
    return bool(os.environ.get('RESISTMAP_SMTP_USER') and os.environ.get('RESISTMAP_SMTP_PASSWORD'))


def send_reset(recipient, token):
    base = os.environ.get('RESISTMAP_PUBLIC_URL', 'http://127.0.0.1:8011').rstrip('/')
    url = urlparse(base)
    if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in {'localhost', '127.0.0.1'}):
        raise ValueError('Use HTTPS for a public reset URL.')
    message = EmailMessage()
    message['Subject'] = 'Reset your ResistMap AI password'
    message['From'] = os.environ['RESISTMAP_SMTP_USER']
    message['To'] = recipient
    message.set_content(f'Open this link to choose a new password:\n{base}/#reset-password={token}\n\nThis link expires in 30 minutes and works once. If you did not request it, ignore this email.')
    with smtplib.SMTP(os.environ.get('RESISTMAP_SMTP_HOST', 'smtp.gmail.com'), int(os.environ.get('RESISTMAP_SMTP_PORT', '587')), timeout=15) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(os.environ['RESISTMAP_SMTP_USER'], os.environ['RESISTMAP_SMTP_PASSWORD'])
        smtp.send_message(message)
