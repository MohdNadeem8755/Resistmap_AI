"""Local accounts with salted password hashes and revocable opaque sessions."""
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
import time
from contextlib import contextmanager
from backend.dashboard import ROOT

DB = Path(os.environ.get('RESISTMAP_AUTH_DB', ROOT/'data/app/accounts.sqlite3'))
COOKIE = 'resistmap_session'


@contextmanager
def connect():
    DB.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(DB,timeout=10)
    db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires REAL NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS password_resets (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires REAL NOT NULL)')
    try:
        with db:
            yield db
    finally:
        db.close()


def password_hash(password,salt):
    return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600_000).hex()


def register(name,email,password):
    email=email.strip().lower()
    if not name.strip() or len(name)>80 or '@' not in email or len(email)>254:
        raise ValueError('Enter your name and a valid email address.')
    if len(password)<8 or len(password)>256:
        raise ValueError('Use a password between 8 and 256 characters.')
    salt=secrets.token_hex(16)
    digest=password_hash(password,salt)
    try:
        with connect() as db:
            cursor=db.execute('INSERT INTO users(name,email,salt,password_hash) VALUES(?,?,?,?)',
                              (name.strip(),email,salt,digest))
            return {'id':cursor.lastrowid,'name':name.strip(),'email':email}
    except sqlite3.IntegrityError as exc:
        raise ValueError('An account with this email already exists. Sign in instead.') from exc


def login(email,password):
    with connect() as db:
        row=db.execute('SELECT * FROM users WHERE email=?',(email.strip().lower(),)).fetchone()
    salt=row['salt'] if row else '00'*16
    digest=password_hash(password,salt)
    if not row or not hmac.compare_digest(digest,row['password_hash']):
        raise ValueError('Email or password is incorrect.')
    return {k:row[k] for k in ('id','name','email')}


def session(user_id,remember):
    token=secrets.token_urlsafe(32)
    lifetime=7*86400 if remember else 12*3600
    with connect() as db:
        db.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
        db.execute('INSERT INTO sessions VALUES(?,?,?)',
                   (hashlib.sha256(token.encode()).hexdigest(),user_id,time.time()+lifetime))
    return token,lifetime


def current(token):
    if not token:
        return None
    with connect() as db:
        row=db.execute('SELECT users.id,name,email FROM sessions JOIN users ON users.id=sessions.user_id WHERE token_hash=? AND expires>?',
                       (hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
    return dict(row) if row else None


def logout(token):
    if token:
        with connect() as db:
            db.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))


def request_reset(email):
    from backend.mailer import send_reset, configured
    if not configured():
        raise RuntimeError('Email reset is not configured. Contact the workspace administrator.')
    with connect() as db:
        user = db.execute('SELECT id,email FROM users WHERE email=?', (email.strip().lower(),)).fetchone()
        if not user:
            return
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        db.execute('DELETE FROM password_resets WHERE user_id=? OR expires<?', (user['id'], time.time()))
        db.execute('INSERT INTO password_resets VALUES(?,?,?)', (digest, user['id'], time.time()+1800))
    try:
        send_reset(user['email'], token)
    except Exception:
        with connect() as db:
            db.execute('DELETE FROM password_resets WHERE token_hash=?', (digest,))
        # Do not expose account existence or mail-server details to the requester.
        import logging
        logging.getLogger(__name__).warning('Password reset email delivery failed')


def reset_password(token, password):
    if not 8 <= len(password) <= 256:
        raise ValueError('Use a password between 8 and 256 characters.')
    digest = hashlib.sha256(token.encode()).hexdigest()
    salt = secrets.token_hex(16)
    hashed = password_hash(password, salt)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT user_id FROM password_resets WHERE token_hash=? AND expires>?', (digest, time.time())).fetchone()
        if not row:
            raise ValueError('Reset link is invalid or expired. Request a new link.')
        db.execute('UPDATE users SET salt=?,password_hash=? WHERE id=?', (salt, hashed, row['user_id']))
        db.execute('DELETE FROM password_resets WHERE user_id=?', (row['user_id'],))
        db.execute('DELETE FROM sessions WHERE user_id=?', (row['user_id'],))
