import os
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.decorators import root_required
from app.models.user import User
from app.models.casa import Casa, HistorialAumento
from app.models.abono_historico import AbonoHistorico
from app.models.configuracion import Configuracion
from app import db
from datetime import datetime

root_bp = Blueprint("root", __name__, url_prefix="/root")

FLAG_PATH = os.path.join(os.getcwd(), 'mantenimiento.flag')
LOG_AUMENTOS = os.path.join(os.getcwd(), 'registro_aumentos.txt')


# ================================================
# PANEL PRINCIPAL
# ================================================
@root_bp.route("/")
@login_required
@root_required
def panel():
    # ── Estado del sistema ───────────────────────────────────────────────────
    modo_mantenimiento = os.path.exists(FLAG_PATH)

    total_clientes = Casa.query.filter_by(activo=True).count()
    total_inactivos = Casa.query.filter_by(activo=False).count()
    total_usuarios = User.query.filter(User.username != 'root').count()
    total_admins = User.query.filter(User.username != 'root', User.rol == 'admin').count()

    # ── Usuarios (sin root) ──────────────────────────────────────────────────
    usuarios = User.query.filter(User.username != 'root').order_by(User.rol, User.username).all()

    # ── Últimos 20 aumentos ──────────────────────────────────────────────────
    ultimos_aumentos = HistorialAumento.query.order_by(
        HistorialAumento.fecha.desc()
    ).limit(20).all()

    # ── Log de aumentos desde archivo ────────────────────────────────────────
    lineas_log = []
    if os.path.exists(LOG_AUMENTOS):
        with open(LOG_AUMENTOS, encoding='utf-8') as f:
            lineas = f.readlines()
        # Mostramos las últimas 50 líneas, sin el encabezado repetido
        lineas_log = [l.strip() for l in lineas if l.strip() and 'CLIENTE' not in l][-50:]
        lineas_log.reverse()

    return render_template(
        "root/panel.html",
        modo_mantenimiento=modo_mantenimiento,
        total_clientes=total_clientes,
        total_inactivos=total_inactivos,
        total_usuarios=total_usuarios,
        total_admins=total_admins,
        usuarios=usuarios,
        ultimos_aumentos=ultimos_aumentos,
        lineas_log=lineas_log,
    )


# ================================================
# TOGGLE MODO MANTENIMIENTO
# ================================================
@root_bp.route("/toggle-mantenimiento", methods=["POST"])
@login_required
@root_required
def toggle_mantenimiento():
    if os.path.exists(FLAG_PATH):
        os.remove(FLAG_PATH)
        flash("✅ Modo mantenimiento desactivado. El sistema está en línea.", "success")
    else:
        with open(FLAG_PATH, 'w') as f:
            f.write(f"Mantenimiento activado por root el {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
        flash("🔧 Modo mantenimiento activado. Solo root puede navegar.", "warning")
    return redirect(url_for('root.panel'))


# ================================================
# CAMBIO DE ROL DE USUARIO
# ================================================
@root_bp.route("/usuario/<int:id>/toggle-rol", methods=["POST"])
@login_required
@root_required
def toggle_rol(id):
    usuario = User.query.get_or_404(id)
    if usuario.username == 'root':
        flash("No podés modificar al usuario root.", "error")
        return redirect(url_for('root.panel'))

    usuario.rol = 'empleado' if usuario.rol == 'admin' else 'admin'
    db.session.commit()
    nuevo = "Administrador" if usuario.rol == 'admin' else "Empleado"
    flash(f"Rol actualizado: {usuario.username} ahora es {nuevo}.", "success")
    return redirect(url_for('root.panel'))


# ================================================
# RESET DE CONTRASEÑA DE USUARIO
# ================================================
@root_bp.route("/usuario/<int:id>/reset-password", methods=["POST"])
@login_required
@root_required
def reset_password(id):
    usuario = User.query.get_or_404(id)
    if usuario.username == 'root':
        flash("No podés modificar al usuario root desde aquí.", "error")
        return redirect(url_for('root.panel'))

    nueva = request.form.get("nueva_password", "").strip()
    if not nueva:
        flash("La contraseña no puede estar vacía.", "error")
        return redirect(url_for('root.panel'))

    usuario.set_password(nueva)
    db.session.commit()
    flash(f"🔑 Contraseña actualizada para {usuario.username}.", "success")
    return redirect(url_for('root.panel'))


# ================================================
# CREAR USUARIO DESDE EL PANEL ROOT
# ================================================
@root_bp.route("/usuario/crear", methods=["POST"])
@login_required
@root_required
def crear_usuario():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    rol = request.form.get("rol", "empleado").strip()

    if not username or not password:
        flash("Usuario y contraseña son obligatorios.", "error")
        return redirect(url_for('root.panel'))

    if User.query.filter_by(username=username).first():
        flash(f"El usuario '{username}' ya existe.", "error")
        return redirect(url_for('root.panel'))

    nuevo = User(username=username, rol=rol)
    nuevo.set_password(password)
    db.session.add(nuevo)
    db.session.commit()
    flash(f"✅ Usuario '{username}' creado como {rol}.", "success")
    return redirect(url_for('root.panel'))


# ================================================
# ELIMINAR USUARIO
# ================================================
@root_bp.route("/usuario/<int:id>/eliminar", methods=["POST"])
@login_required
@root_required
def eliminar_usuario(id):
    usuario = User.query.get_or_404(id)
    if usuario.username == 'root':
        flash("No podés eliminar al usuario root.", "error")
        return redirect(url_for('root.panel'))

    nombre = usuario.username
    db.session.delete(usuario)
    db.session.commit()
    flash(f"Usuario '{nombre}' eliminado.", "info")
    return redirect(url_for('root.panel'))


# ================================================
# LIMPIAR LOG DE AUMENTOS
# ================================================
@root_bp.route("/limpiar-log", methods=["POST"])
@login_required
@root_required
def limpiar_log():
    if os.path.exists(LOG_AUMENTOS):
        os.remove(LOG_AUMENTOS)
        flash("Log de aumentos limpiado.", "info")
    return redirect(url_for('root.panel'))
