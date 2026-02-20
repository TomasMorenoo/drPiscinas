from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Si no está logueado o no es admin, lo pateamos al inicio
        if not current_user.is_authenticated or not current_user.is_admin():
            flash("No tenés permisos para ver esta sección.", "error")
            return redirect(url_for('home.index'))
        return f(*args, **kwargs)
    return decorated_function