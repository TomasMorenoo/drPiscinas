from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.decorators import admin_required
from app import db
from app.models.country import Country

country_bp = Blueprint("country", __name__, url_prefix="/countries")

@country_bp.route("/")
@login_required
@admin_required
def listar_countries():
    countries = Country.query.order_by(Country.nombre).all()
    return render_template("countries/list.html", countries=countries)

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
            country.nombre = nombre
            db.session.commit()
            flash("Country actualizado", "success")
            return redirect(url_for("country.listar_countries"))
    return render_template("countries/create.html", country=country)

@country_bp.route("/toggle/<int:id>")
@login_required
@admin_required
def toggle_country(id):
    country = Country.query.get_or_404(id)
    country.activo = not country.activo
    db.session.commit()
    return redirect(url_for("country.listar_countries"))

@country_bp.route("/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
def eliminar_country(id):
    country = Country.query.get_or_404(id)
    try:
        db.session.delete(country)
        db.session.commit()
        flash("Country eliminado definitivamente.", "success")
    except Exception as e:
        db.session.rollback()
        flash("No se puede eliminar porque hay propiedades o barrios asociados.", "error")
    return redirect(url_for("country.listar_countries"))