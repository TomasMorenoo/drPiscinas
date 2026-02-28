from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from app.decorators import admin_required
from app import db
from app.models.user import User

user_bp = Blueprint("users", __name__, url_prefix="/users")

@user_bp.route("/")
@login_required
@admin_required
def listar_usuarios():
    usuarios = User.query.all()
    return render_template("users/list.html", usuarios=usuarios)

@user_bp.route("/create", methods=["GET", "POST"])
@login_required
@admin_required
def crear_usuario():
    if request.method == "POST":
        username = request.form.get("username").strip()
        password = request.form.get("password").strip()
        rol = request.form.get("rol").strip()
        
        if not username or not password:
            flash("Usuario y contraseña son obligatorios.", "error")
            return redirect(url_for("users.crear_usuario"))
            
        if User.query.filter_by(username=username).first():
            flash("El nombre de usuario ya existe.", "error")
            return redirect(url_for("users.crear_usuario"))
            
        nuevo_user = User(username=username, rol=rol)
        nuevo_user.set_password(password)
        
        db.session.add(nuevo_user)
        db.session.commit()
        flash("Usuario creado con éxito.", "success")
        return redirect(url_for("users.listar_usuarios"))
        
    return render_template("users/create.html")

@user_bp.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def editar_usuario(id):
    usuario = User.query.get_or_404(id)
    
    if request.method == "POST":
        username = request.form.get("username").strip()
        rol = request.form.get("rol").strip()
        new_password = request.form.get("new_password").strip()
        
        if not username:
            flash("El nombre de usuario no puede estar vacío.", "error")
            return redirect(url_for("users.editar_usuario", id=id))
            
        check_user = User.query.filter(User.id != id, User.username == username).first()
        if check_user:
            flash("El nombre de usuario ya está en uso.", "error")
            return redirect(url_for("users.editar_usuario", id=id))
            
        usuario.username = username
        usuario.rol = rol
        
        if new_password:
            usuario.set_password(new_password)
            
        db.session.commit()
        flash("Usuario actualizado con éxito.", "success")
        return redirect(url_for("users.listar_usuarios"))
        
    return render_template("users/create.html", usuario=usuario)

@user_bp.route("/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
def eliminar_usuario(id):
    usuario = User.query.get_or_404(id)
    
    if usuario.id == current_user.id:
        flash("No podés eliminar tu propio usuario mientras estás logueado.", "error")
        return redirect(url_for("users.listar_usuarios"))
        
    db.session.delete(usuario)
    db.session.commit()
    flash("Usuario eliminado correctamente.", "success")
    return redirect(url_for("users.listar_usuarios"))

@user_bp.route("/reset_password/<int:id>", methods=["POST"])
@login_required
@admin_required
def reset_password(id):
    usuario = User.query.get_or_404(id)
    nueva_password = request.form.get("nueva_password", "").strip()
    
    if not nueva_password:
        flash("La contraseña no puede estar vacía.", "error")
    else:
        usuario.set_password(nueva_password)
        db.session.commit()
        flash(f"Contraseña actualizada con éxito para {usuario.username}.", "success")
        
    return redirect(url_for("users.listar_usuarios"))