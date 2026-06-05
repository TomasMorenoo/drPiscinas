from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.decorators import admin_required
from app import db
from app.models.barrio import Barrio
from app.models.country import Country

barrio_bp = Blueprint("barrio", __name__, url_prefix="/barrios")

@barrio_bp.route("/")
@login_required
@admin_required
def listar_barrios():
    barrios = Barrio.query.join(Country).order_by(Country.nombre, Barrio.nombre).all()
    return render_template("barrios/list.html", barrios=barrios)

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
            
        nuevo = Barrio(nombre=nombre, country_id=country_id)
        db.session.add(nuevo)
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
        barrio.nombre = request.form.get("nombre")
        barrio.country_id = request.form.get("country_id")
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
    try:
        db.session.delete(barrio)
        db.session.commit()
        flash("Barrio eliminado definitivamente.", "success")
    except Exception as e:
        db.session.rollback()
        flash("No se puede eliminar porque hay propiedades asociadas a este barrio.", "error")
    return redirect(url_for("barrio.listar_barrios"))