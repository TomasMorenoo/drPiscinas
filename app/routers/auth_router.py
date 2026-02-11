from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from app import db, limiter # Importamos el limitador de seguridad
from app.models.user import User

auth_bp = Blueprint('auth', __name__)

# ==========================================
# LOGIN (ACCESO)
# ==========================================
@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute") # 🛡️ SEGURIDAD: Bloquea si erran 5 veces en 1 minuto
def login():
    # Si ya está logueado, no tiene sentido estar acá, lo mandamos al dashboard
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # 1. Buscamos usuario
        user = User.query.filter_by(username=username).first()

        # 2. Verificamos contraseña encriptada
        if user and user.check_password(password):
            login_user(user)
            
            # 3. ACTIVAR RELOJ DE SESIÓN
            # Esto le avisa a Flask que use el timeout de 1 hora configurado en __init__.py
            session.permanent = True 
            
            flash('¡Bienvenido de nuevo!', 'success')
            
            # Redirección inteligente: Si venía de una página bloqueada, vuelve ahí.
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.home'))
        else:
            flash('Usuario o contraseña incorrectos.', 'danger')

    return render_template('auth/login.html')

# ==========================================
# LOGOUT (SALIDA)
# ==========================================
@auth_bp.route('/logout')
@login_required # Solo puede salir quien haya entrado
def logout():
    logout_user()
    flash('Sesión cerrada correctamente.', 'info')
    return redirect(url_for('auth.login'))