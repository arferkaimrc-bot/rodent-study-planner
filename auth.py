"""
Authentication & access control for Rodent Study Planner.

Phase 1 (small known group):
  - Email + password login (hashed passwords).
  - NO open self-registration — the admin creates accounts via /admin.
  - New accounts get a temporary password and must change it on first login.
  - Admin can enable/disable users and reset passwords.
  - Every page is protected behind login (guard in init_auth).

Uses Flask-Login (sessions) + Flask-SQLAlchemy (SQLite by default; set
DATABASE_URL for Postgres in production).
"""
import os
import secrets
import logging
from datetime import datetime

from flask import (Blueprint, request, redirect, url_for, flash,
                   render_template_string, abort)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger(__name__)

db = SQLAlchemy()
login_manager = LoginManager()
auth_bp = Blueprint('auth', __name__)

# Simple, human-friendly password: an easy word + 3 digits (e.g. "maple482").
_PW_WORDS = ['tiger', 'river', 'maple', 'solar', 'delta', 'falcon', 'cedar',
             'coral', 'amber', 'onyx', 'quartz', 'lotus', 'comet', 'zephyr',
             'pixel', 'mango', 'indigo', 'cobalt', 'willow', 'orbit']


def simple_password():
    return f"{secrets.choice(_PW_WORDS)}{secrets.randbelow(900) + 100}"


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255))
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)  # overrides UserMixin
    must_change_password = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    def set_password(self, raw):
        # pbkdf2:sha256 works everywhere; werkzeug's newer 'scrypt' default
        # requires OpenSSL scrypt support that some Python builds lack.
        self.password_hash = generate_password_hash(raw, method='pbkdf2:sha256')

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ---------------------------------------------------------------------------
# Minimal styled pages (kept inline to avoid extra template files)
# ---------------------------------------------------------------------------
_BASE = """
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} · Rodent Study Planner</title>
<style>
  :root{--green:#16a34a;--green-d:#15803d;--muted:#64748b;--bg:#f4f6f8;--red:#ef4444;}
  *{box-sizing:border-box}
  body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);margin:0;color:#0f172a}
  .wrap{max-width:{{ wide and '860px' or '400px' }};margin:6vh auto;padding:0 16px}
  .card{background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:28px;box-shadow:0 4px 20px rgba(0,0,0,.05)}
  h1{color:var(--green-d);font-size:1.4rem;margin:0 0 4px}
  .sub{color:var(--muted);font-size:.85rem;margin:0 0 20px}
  label{display:block;font-size:.85rem;font-weight:600;margin:12px 0 4px}
  input,select{width:100%;padding:10px 12px;border:1px solid #cbd5e1;border-radius:9px;font-size:.95rem}
  button{width:100%;margin-top:18px;padding:11px;background:var(--green);color:#fff;border:0;border-radius:9px;font-weight:700;font-size:.95rem;cursor:pointer}
  button:hover{background:var(--green-d)}
  .flash{padding:10px 12px;border-radius:9px;font-size:.85rem;margin-bottom:14px}
  .flash.error{background:#fee2e2;color:#991b1b}
  .flash.ok{background:#dcfce7;color:#166534}
  table{width:100%;border-collapse:collapse;font-size:.85rem;margin-top:16px}
  th,td{text-align:left;padding:8px 10px;border-bottom:1px solid #e2e8f0}
  th{color:var(--muted);font-weight:600}
  .badge{padding:2px 8px;border-radius:6px;font-size:.72rem;font-weight:700}
  .on{background:#dcfce7;color:#166534}.off{background:#fee2e2;color:#991b1b}.adm{background:#e0e7ff;color:#3730a3}
  .btn-sm{width:auto;margin:0;padding:5px 10px;font-size:.75rem;background:#e2e8f0;color:#0f172a}
  .btn-sm.danger{background:#fee2e2;color:#991b1b}
  .row{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}
  .row>div{flex:1;min-width:140px}
  a{color:var(--green-d)}
  .topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
</style></head><body><div class="wrap"><div class="card">
{% with msgs = get_flashed_messages(with_categories=true) %}
  {% for cat,msg in msgs %}<div class="flash {{ 'error' if cat=='error' else 'ok' }}">{{ msg }}</div>{% endfor %}
{% endwith %}
{{ body }}
</div></div></body></html>
"""


def _page(title, body_html, wide=False):
    return render_template_string(
        _BASE.replace("{{ body }}", body_html),
        title=title, wide=wide)


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            if not user.is_active:
                flash('This account is disabled. Contact the administrator.', 'error')
            else:
                login_user(user)
                user.last_login = datetime.utcnow()
                db.session.commit()
                nxt = request.args.get('next')
                if user.must_change_password:
                    return redirect(url_for('auth.change_password'))
                return redirect(nxt or url_for('home'))
        else:
            flash('Invalid email or password.', 'error')
    body = """
      <h1>🐭 Rodent Study Planner</h1>
      <p class="sub">Sign in to access the drug study planner</p>
      <form method="post">
        <label>Email</label>
        <input type="email" name="email" required autofocus autocomplete="username">
        <label>Password</label>
        <input type="password" name="password" required autocomplete="current-password">
        <button type="submit">Sign in</button>
      </form>
      <p class="sub" style="margin-top:16px">Accounts are created by the administrator.</p>
    """
    return _page('Sign in', body)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been signed out.', 'ok')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        cur = request.form.get('current') or ''
        new = request.form.get('new') or ''
        confirm = request.form.get('confirm') or ''
        if not current_user.check_password(cur):
            flash('Current password is incorrect.', 'error')
        elif len(new) < 8:
            flash('New password must be at least 8 characters.', 'error')
        elif new != confirm:
            flash('New passwords do not match.', 'error')
        else:
            current_user.set_password(new)
            current_user.must_change_password = False
            db.session.commit()
            flash('Password updated.', 'ok')
            return redirect(url_for('home'))
    note = ('<p class="sub">You must set a new password before continuing.</p>'
            if current_user.must_change_password else
            '<p class="sub">Update your account password.</p>')
    body = f"""
      <h1>Change password</h1>{note}
      <form method="post">
        <label>Current password</label>
        <input type="password" name="current" required autocomplete="current-password">
        <label>New password (min 8 chars)</label>
        <input type="password" name="new" required autocomplete="new-password">
        <label>Confirm new password</label>
        <input type="password" name="confirm" required autocomplete="new-password">
        <button type="submit">Update password</button>
      </form>
    """
    return _page('Change password', body)


# ---------------------------------------------------------------------------
# Admin routes (admin only)
# ---------------------------------------------------------------------------
def _admin_only():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


@auth_bp.route('/admin')
@login_required
def admin():
    _admin_only()
    users = User.query.order_by(User.created_at.desc()).all()
    rows = ""
    for u in users:
        status = ('<span class="badge on">active</span>' if u.is_active
                  else '<span class="badge off">disabled</span>')
        adm = ' <span class="badge adm">admin</span>' if u.is_admin else ''
        pend = ' <span class="badge off">temp pw</span>' if u.must_change_password else ''
        toggle_label = 'Disable' if u.is_active else 'Enable'
        rows += f"""
          <tr>
            <td>{u.email}{adm}</td>
            <td>{u.name or '—'}</td>
            <td>{status}{pend}</td>
            <td>{u.last_login.strftime('%Y-%m-%d %H:%M') if u.last_login else '—'}</td>
            <td>
              <form method="post" action="{url_for('auth.admin_toggle', user_id=u.id)}" style="display:inline">
                <button class="btn-sm" type="submit">{toggle_label}</button></form>
              <form method="post" action="{url_for('auth.admin_reset', user_id=u.id)}" style="display:inline">
                <button class="btn-sm danger" type="submit">Reset pw</button></form>
            </td>
          </tr>"""
    body = f"""
      <div class="topbar">
        <h1>👥 User administration</h1>
        <div><a href="{url_for('home')}">← App</a> &nbsp; <a href="{url_for('auth.logout')}">Sign out</a></div>
      </div>
      <p class="sub">Create accounts for researchers. Each account gets a simple password shown once — the user signs in with it directly (no password change required).</p>
      <form method="post" action="{url_for('auth.admin_create')}">
        <div class="row">
          <div><label>Email</label><input type="email" name="email" required></div>
          <div><label>Name</label><input type="text" name="name"></div>
          <div style="flex:0 0 auto"><label>Role</label>
            <select name="role"><option value="user">Researcher</option><option value="admin">Admin</option></select></div>
        </div>
        <button type="submit" style="width:auto;padding:9px 18px">Create account</button>
      </form>
      <table>
        <tr><th>Email</th><th>Name</th><th>Status</th><th>Last login</th><th>Actions</th></tr>
        {rows}
      </table>
    """
    return _page('User administration', body, wide=True)


@auth_bp.route('/admin/create', methods=['POST'])
@login_required
def admin_create():
    _admin_only()
    email = (request.form.get('email') or '').strip().lower()
    name = (request.form.get('name') or '').strip()
    role = request.form.get('role') or 'user'
    if not email:
        flash('Email is required.', 'error')
        return redirect(url_for('auth.admin'))
    if User.query.filter_by(email=email).first():
        flash(f'An account for {email} already exists.', 'error')
        return redirect(url_for('auth.admin'))
    pw = simple_password()
    u = User(email=email, name=name, is_admin=(role == 'admin'),
             is_active=True, must_change_password=False)  # no forced change
    u.set_password(pw)
    db.session.add(u)
    db.session.commit()
    # Show the password ONCE to the admin to relay to the researcher.
    flash(f'Account created for {email}. Password: {pw} '
          f'(share it securely — the user can sign in with it directly).', 'ok')
    return redirect(url_for('auth.admin'))


@auth_bp.route('/admin/toggle/<int:user_id>', methods=['POST'])
@login_required
def admin_toggle(user_id):
    _admin_only()
    u = db.session.get(User, user_id)
    if not u:
        abort(404)
    if u.id == current_user.id:
        flash('You cannot disable your own account.', 'error')
        return redirect(url_for('auth.admin'))
    u.is_active = not u.is_active
    db.session.commit()
    flash(f'{u.email} is now {"active" if u.is_active else "disabled"}.', 'ok')
    return redirect(url_for('auth.admin'))


@auth_bp.route('/admin/reset/<int:user_id>', methods=['POST'])
@login_required
def admin_reset(user_id):
    _admin_only()
    u = db.session.get(User, user_id)
    if not u:
        abort(404)
    pw = simple_password()
    u.set_password(pw)
    u.must_change_password = False
    db.session.commit()
    flash(f'Password for {u.email} reset. New password: {pw} '
          f'(the user can sign in with it directly).', 'ok')
    return redirect(url_for('auth.admin'))


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------
# Paths that never require authentication.
_EXEMPT_PREFIXES = ('/static',)
_EXEMPT_PATHS = {'/login', '/logout', '/health'}


def init_auth(app):
    """Configure DB, login manager, routes and the global auth guard."""
    db_url = os.getenv('DATABASE_URL', 'sqlite:///' + os.path.join(app.root_path, 'rodent_planner.db'))
    # SQLAlchemy needs postgresql:// not postgres://
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please sign in to continue.'
    app.register_blueprint(auth_bp)

    with app.app_context():
        db.create_all()
        _seed_admin(app)

    @app.before_request
    def _require_login():
        p = request.path
        if p in _EXEMPT_PATHS or any(p.startswith(x) for x in _EXEMPT_PREFIXES):
            return
        if request.endpoint and request.endpoint.startswith('auth.'):
            return
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login', next=p))
        # Force temp-password holders to change it before using the app.
        if current_user.must_change_password and p != '/change-password':
            return redirect(url_for('auth.change_password'))


def _seed_admin(app):
    """Create the first admin from env vars, or a random one logged once."""
    if User.query.first():
        return
    email = (os.getenv('ADMIN_EMAIL') or 'admin@rodentplanner.local').strip().lower()
    password = os.getenv('ADMIN_PASSWORD')
    generated = False
    if not password:
        password = secrets.token_urlsafe(10)
        generated = True
    admin = User(email=email, name='Administrator', is_admin=True,
                 is_active=True, must_change_password=generated)
    admin.set_password(password)
    db.session.add(admin)
    try:
        db.session.commit()
    except Exception as e:
        # Another instance seeded first (concurrent cold start) — that's fine.
        db.session.rollback()
        logger.info("Admin seed skipped (already exists): %s", e)
        return
    logger.warning("=" * 60)
    logger.warning("INITIAL ADMIN ACCOUNT CREATED")
    logger.warning("  email:    %s", email)
    if generated:
        logger.warning("  password: %s  (change it on first sign-in)", password)
    else:
        logger.warning("  password: (from ADMIN_PASSWORD env var)")
    logger.warning("=" * 60)
