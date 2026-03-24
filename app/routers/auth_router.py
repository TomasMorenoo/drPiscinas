from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from app import db, limiter 
from app.models.user import User

auth_bp = Blueprint('auth', __name__)

# ==========================================
# LOGIN (ACCESO)
# ==========================================
@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute") # Máximo 5 intentos por minuto para evitar ataques
def login():
    # Si ya está logueado, lo mandamos al Home
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    if request.method == 'POST':
        # Le quitamos los espacios en blanco al principio y al final por las dudas con .strip()
        username = request.form.get('username').strip()
        password = request.form.get('password')
        
        # CAMBIO CLAVE: Usamos .ilike() para que ignore mayúsculas y minúsculas
        user = User.query.filter(User.username.ilike(username)).first()

        # Verificamos credenciales
        if user and user.check_password(password):
            # remember=False asegura que la cookie muera al cerrar el navegador
            login_user(user, remember=False)
            
            # Marcamos la sesión como NO permanente para respetar el cierre de pestaña
            session.permanent = False 
            
            flash('¡Bienvenido de nuevo!', 'success')
            
            # Redirección inteligente
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.home'))
        else:
            flash('Usuario o contraseña incorrectos.', 'danger')

    return render_template('auth/login.html')

# ==========================================
# LOGOUT (SALIDA)
# ==========================================
@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    # Limpiamos explícitamente la sesión por seguridad
    session.clear()
    flash('Sesión cerrada correctamente.', 'info')
    return redirect(url_for('auth.login'))