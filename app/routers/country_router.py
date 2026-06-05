from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.decorators import admin_required
from app import db
from app.models.country import Country
from app.models.configuracion import Configuracion
from app.utils import registrar_auditoria

country_bp = Blueprint("country", __name__, url_prefix="/countries")

@country_bp.route("/")
@login_required
@admin_required
def listar_countries():
    countries = Country.query.order_by(Country.nombre).all()
    editar_activo = Configuracion.get("editar_countries", False)
    return render_template("countries/list.html", countries=countries, editar_activo=editar_activo)


@country_bp.route("/create", methods=["GET", "POST"])
@login_required
@admin_required
def crear_country():
    if request.method == "POST":
        nombre = request.form.get("nombre")
        if not nombre:
            flash("El nombre es obligatorio", "error")
            return redirect(url_for("country.crear_country"))
        
        nuevo = Country(nombre=nombre)
        db.session.add(nuevo)
        db.session.commit()
        registrar_auditoria(current_user.username, 'CREAR_COUNTRY', f"{nombre}")
        db.session.commit()
        flash("Country creado exitosamente", "success")
        return redirect(url_for("country.listar_countries"))
    return render_template("countries/create.html")

@country_bp.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def editar_country(id):
    country = Country.query.get_or_404(id)
    if request.method == "POST":
        nombre = request.form.get("nombre")
        if nombre:
            nombre_anterior = country.nombre
            country.nombre = nombre
            db.session.commit()
            registrar_auditoria(current_user.username, 'EDITAR_COUNTRY', f"{nombre_anterior} → {nombre}")
            db.session.commit()
            flash("Country actualizado", "success")
            return redirect(url_for("country.listar_countries"))
    return render_template("countries/create.html", country=country)

@country_bp.route("/toggle/<int:id>")
@login_required
@admin_required
def toggle_country(id):
    country = Country.query.get_or_404(id)
    accion = 'INACTIVAR_COUNTRY' if country.activo else 'ACTIVAR_COUNTRY'
    country.activo = not country.activo
    db.session.commit()
    registrar_auditoria(current_user.username, accion, f"{country.nombre}")
    db.session.commit()
    return redirect(url_for("country.listar_countries"))

@country_bp.route("/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
def eliminar_country(id):
    country = Country.query.get_or_404(id)
    try:
        nombre = country.nombre
        db.session.delete(country)
        db.session.commit()
        registrar_auditoria(current_user.username, 'ELIMINAR_COUNTRY', f"{nombre}")
        db.session.commit()
        flash("Country eliminado definitivamente.", "success")
    except Exception as e:
        db.session.rollback()
        flash("No se puede eliminar porque hay propiedades o barrios asociados.", "error")
    return redirect(url_for("country.listar_countries"))