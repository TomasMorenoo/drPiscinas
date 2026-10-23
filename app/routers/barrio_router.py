from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.decorators import admin_required
from app import db
from app.models.barrio import Barrio
from app.models.country import Country
from app.models.configuracion import Configuracion
from app.greenville import es_greenville
from app.utils import registrar_auditoria
import re

barrio_bp = Blueprint("barrio", __name__, url_prefix="/barrios")


def _nombre_barrio(nombre, country):
    nombre = (nombre or "").strip()
    if es_greenville(country.nombre):
        nombre = nombre.upper()
        if not re.fullmatch(r"[A-Z]", nombre):
            return None, "En Greenville el barrio debe ser una sola letra, por ejemplo A."
    return nombre, None

@barrio_bp.route("/")
@login_required
@admin_required
def listar_barrios():
    barrios = Barrio.query.join(Country).order_by(Country.nombre, Barrio.nombre).all()
    editar_activo = Configuracion.get("editar_countries", False)
    return render_template("barrios/list.html", barrios=barrios, editar_activo=editar_activo)

@barrio_bp.route("/create", methods=["GET", "POST"])
@login_required
@admin_required
def crear_barrio():
    if request.method == "POST":
        nombre = request.form.get("nombre")
        country_id = request.form.get("country_id")
        
        if not nombre or not country_id:
            flash("Todos los campos son obligatorios", "error")
            return redirect(url_for("barrio.crear_barrio"))
            
        country = Country.query.get(country_id)
        if not country:
            flash("El country seleccionado no es válido.", "error")
            return redirect(url_for("barrio.crear_barrio"))

        nombre, error = _nombre_barrio(nombre, country)
        if error:
            flash(error, "error")
            return redirect(url_for("barrio.crear_barrio"))

        if Barrio.query.filter_by(nombre=nombre, country_id=country.id).first():
            flash("Ese barrio ya existe en el country seleccionado.", "error")
            return redirect(url_for("barrio.crear_barrio"))

        nuevo = Barrio(nombre=nombre, country_id=country.id)
        db.session.add(nuevo)
        db.session.flush()
        registrar_auditoria(
            current_user.username,
            "CREAR_BARRIO",
            f"Barrio ID {nuevo.id}: {country.nombre} {nombre}.",
        )
        db.session.commit()
        flash("Barrio creado exitosamente", "success")
        return redirect(url_for("barrio.listar_barrios"))
        
    countries = Country.query.filter_by(activo=True).order_by(Country.nombre).all()
    return render_template("barrios/create.html", countries=countries)

@barrio_bp.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def editar_barrio(id):
    barrio = Barrio.query.get_or_404(id)
    if request.method == "POST":
        country = Country.query.get(request.form.get("country_id"))
        if not country:
            flash("El country seleccionado no es válido.", "error")
            return redirect(url_for("barrio.editar_barrio", id=id))

        nombre, error = _nombre_barrio(request.form.get("nombre"), country)
        if error:
            flash(error, "error")
            return redirect(url_for("barrio.editar_barrio", id=id))

        duplicado = Barrio.query.filter(
            Barrio.id != barrio.id,
            Barrio.nombre == nombre,
            Barrio.country_id == country.id,
        ).first()
        if duplicado:
            flash("Ese barrio ya existe en el country seleccionado.", "error")
            return redirect(url_for("barrio.editar_barrio", id=id))

        anterior = f"{barrio.country.nombre} {barrio.nombre}"
        barrio.nombre = nombre
        barrio.country = country
        registrar_auditoria(
            current_user.username,
            "EDITAR_BARRIO",
            f"Barrio ID {barrio.id}: {anterior} → {country.nombre} {nombre}.",
        )
        db.session.commit()
        flash("Barrio actualizado", "success")
        return redirect(url_for("barrio.listar_barrios"))
        
    countries = Country.query.filter_by(activo=True).order_by(Country.nombre).all()
    return render_template("barrios/create.html", barrio=barrio, countries=countries)

@barrio_bp.route("/toggle/<int:id>")
@login_required
@admin_required
def toggle_barrio(id):
    barrio = Barrio.query.get_or_404(id)
    barrio.activo = not barrio.activo
    db.session.commit()
    return redirect(url_for("barrio.listar_barrios"))

@barrio_bp.route("/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
def eliminar_barrio(id):
    barrio = Barrio.query.get_or_404(id)
    next_url = request.form.get("next") or url_for("barrio.listar_barrios")
    try:
        registrar_auditoria(current_user.username, "ELIMINAR_BARRIO", f"Barrio ID {barrio.id}: {barrio.country.nombre} {barrio.nombre}.")
        db.session.delete(barrio)
        db.session.commit()
        flash("Barrio eliminado definitivamente.", "success")
    except Exception as e:
        db.session.rollback()
        flash("No se puede eliminar porque hay propiedades asociadas a este barrio.", "error")
    return redirect(next_url)
