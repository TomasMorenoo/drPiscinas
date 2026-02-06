from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import Country

country_bp = Blueprint(
    "country",
    __name__,
    url_prefix="/countries"
)

@country_bp.route("/")
def listar_countries():
    countries = Country.query.order_by(Country.nombre).all()
    return render_template("countries/list.html", countries=countries)

@country_bp.route("/create", methods=["GET"])
def form_crear_country():
    return render_template("countries/create.html")

@country_bp.route("/create", methods=["POST"])
def crear_country():
    nombre = request.form.get("nombre", "").strip()

    if not nombre:
        flash("El nombre no puede estar vacío", "error")
        return redirect(url_for("country.listar_countries"))

    existe = Country.query.filter_by(nombre=nombre).first()
    if existe:
        flash("Ese country ya existe", "error")
        return redirect(url_for("country.listar_countries"))

    country = Country(nombre=nombre)
    db.session.add(country)
    db.session.commit()

    flash("Country creado correctamente", "success")
    return redirect(url_for("country.listar_countries"))

@country_bp.route("/toggle/<int:id>")
def toggle_country(id):
    country = Country.query.get_or_404(id)
    country.activo = not country.activo
    db.session.commit()
    return redirect(url_for("country.listar_countries"))
