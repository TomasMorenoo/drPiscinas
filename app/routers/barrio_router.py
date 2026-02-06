from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import Barrio, Country

barrio_bp = Blueprint(
    "barrio",
    __name__,
    url_prefix="/barrios"
)

# Listado
@barrio_bp.route("/")
def listar_barrios():
    barrios = Barrio.query.order_by(Barrio.nombre).all()
    return render_template("barrios/list.html", barrios=barrios)

# Formulario GET
@barrio_bp.route("/create", methods=["GET"])
def form_crear_barrio():
    countries = Country.query.filter_by(activo=True).order_by(Country.nombre).all()
    return render_template("barrios/create.html", countries=countries)

# Crear POST
@barrio_bp.route("/create", methods=["POST"])
def crear_barrio():
    nombre = request.form.get("nombre", "").strip()
    country_id = request.form.get("country_id")

    if not nombre:
        flash("El nombre no puede estar vacío", "error")
        return redirect(url_for("barrio.listar_barrios"))

    if not country_id:
        flash("Debe seleccionar un country", "error")
        return redirect(url_for("barrio.listar_barrios"))

    existe = Barrio.query.filter_by(nombre=nombre, country_id=country_id).first()
    if existe:
        flash("Ese barrio ya existe para el country seleccionado", "error")
        return redirect(url_for("barrio.listar_barrios"))

    barrio = Barrio(nombre=nombre, country_id=country_id)
    db.session.add(barrio)
    db.session.commit()
    flash("Barrio creado correctamente", "success")
    return redirect(url_for("barrio.listar_barrios"))

# Activar / desactivar
@barrio_bp.route("/toggle/<int:id>")
def toggle_barrio(id):
    barrio = Barrio.query.get_or_404(id)
    barrio.activo = not barrio.activo
    db.session.commit()
    return redirect(url_for("barrio.listar_barrios"))
