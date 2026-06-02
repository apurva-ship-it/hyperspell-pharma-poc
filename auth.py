"""Keycloak OIDC integration for the pharma POC Flask app."""

import os
from functools import wraps
from flask import session, redirect, url_for, jsonify, request
from authlib.integrations.flask_client import OAuth

oauth = OAuth()

# Demo mode: skip Keycloak entirely and treat every visitor as a demo admin.
# Enable by setting DEMO_MODE=1 (used for the public Vercel demo with no IdP).
DEMO_MODE = os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes", "on")
DEMO_USER = {
    "email": "demo@hyperspell.poc",
    "name": "Demo User",
    "roles": ["admin"],
    "sub": "demo-user",
}


def init_auth(app):
    app.secret_key = os.environ["FLASK_SECRET_KEY"]
    oauth.init_app(app)
    oauth.register(
        name="keycloak",
        client_id=os.environ["KEYCLOAK_CLIENT_ID"],
        client_secret=os.environ["KEYCLOAK_CLIENT_SECRET"],
        server_metadata_url=(
            f"{os.environ['KEYCLOAK_URL']}/realms/"
            f"{os.environ['KEYCLOAK_REALM']}/.well-known/openid-configuration"
        ),
        client_kwargs={"scope": "openid email profile"},
    )


def current_user():
    user = session.get("user")
    if user:
        return user
    if DEMO_MODE:
        return DEMO_USER
    return None


def has_role(role):
    u = current_user()
    return bool(u and role in u.get("roles", []))


def _wants_json():
    if request.path.startswith("/api/"):
        return True
    if request.is_json:
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept and "text/html" not in accept


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user():
            if _wants_json():
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


def role_required(role):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not current_user():
                if _wants_json():
                    return jsonify({"error": "unauthorized"}), 401
                return redirect(url_for("login", next=request.path))
            if not has_role(role):
                if _wants_json():
                    return jsonify({"error": "forbidden", "required_role": role}), 403
                return ("Forbidden — admin role required.", 403)
            return f(*args, **kwargs)
        return wrapper
    return decorator
