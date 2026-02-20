from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.decorators import admin_required
from app import db
from app.models.user import User

user_bp = Blueprint("users", __name__, url_prefix="/users")

@user_bp.route("/")
@login_required
@admin_required
def listar_usuarios():
    usuarios = User.query.order_by(User.username).all()
    return render_template("users/list.html", usuarios=usuarios)

@user_bp.route("/create", methods=["GET", "POST"])
@login_required
@admin_required
def crear_usuario():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        rol = request.form.get("rol", "empleado")

        if not username or not password:
            flash("Usuario y contraseña son obligatorios.", "error")
            return redirect(url_for("users.crear_usuario"))

        existe = User.query.filter_by(username=username).first()
        if existe:
            flash("El nombre de usuario ya está en uso.", "error")
            return redirect(url_for("users.crear_usuario"))

        nuevo_usuario = User(username=username, rol=rol)
        nuevo_usuario.set_password(password)
        db.session.add(nuevo_usuario)
        db.session.commit()
        
        flash("Usuario creado exitosamente.", "success")
        return redirect(url_for("users.listar_usuarios"))

    return render_template("users/create.html")

@user_bp.route("/reset_password/<int:id>", methods=["POST"])
@login_required
@admin_required
def reset_password(id):
    usuario = User.query.get_or_404(id)
    nueva_pass = request.form.get("nueva_password", "").strip()
    
    if not nueva_pass:
        flash("La contraseña no puede estar vacía.", "error")
        return redirect(url_for("users.listar_usuarios"))
    
    usuario.set_password(nueva_pass)
    db.session.commit()
    flash(f"Contraseña de {usuario.username} actualizada correctamente.", "success")
    return redirect(url_for("users.listar_usuarios"))

@user_bp.route("/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
def eliminar_usuario(id):
    usuario = User.query.get_or_404(id)
    
    if usuario.id == current_user.id:
        flash("Por seguridad, no podés eliminar tu propia cuenta.", "error")
        return redirect(url_for("users.listar_usuarios"))
    
    db.session.delete(usuario)
    db.session.commit()
    flash("Usuario eliminado del sistema.", "success")
    return redirect(url_for("users.listar_usuarios"))