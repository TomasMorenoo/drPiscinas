from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import Casa, Country, Barrio
from flask import jsonify

casa_bp = Blueprint(
    "casas",
    __name__,
    url_prefix="/casas"
)

# Listado
@casa_bp.route("/")
def listar_casas():
    casas = Casa.query.order_by(Casa.numero).all()
    return render_template("casas/list.html", casas=casas)

# Formulario GET
@casa_bp.route("/create", methods=["GET"])
def form_crear_casa():
    countries = Country.query.filter_by(activo=True).order_by(Country.nombre).all()
    barrios = Barrio.query.filter_by(activo=True).order_by(Barrio.nombre).all()
    return render_template("casas/create.html", countries=countries, barrios=barrios)

@casa_bp.route("/barrios/<int:country_id>")
def barrios_por_country(country_id):
    barrios = Barrio.query.filter_by(country_id=country_id, activo=True).order_by(Barrio.nombre).all()
    lista = [{"id": b.id, "nombre": b.nombre} for b in barrios]
    return jsonify(lista)

# Crear POST
@casa_bp.route("/create", methods=["POST"])
def crear_casa():
    numero = request.form.get("numero", "").strip()
    precio_base = request.form.get("precio_base", "").strip()
    country_id = request.form.get("country_id")
    barrio_id = request.form.get("barrio_id") or None

    if not numero or not precio_base or not country_id:
        flash("Todos los campos obligatorios deben completarse", "error")
        return redirect(url_for("casas.listar_casas"))

    existe = Casa.query.filter_by(numero=numero, country_id=country_id).first()
    if existe:
        flash("Esa casa ya existe para el country seleccionado", "error")
        return redirect(url_for("casas.listar_casas"))

    casa = Casa(numero=numero, precio_base=precio_base, country_id=country_id, barrio_id=barrio_id)
    db.session.add(casa)
    db.session.commit()
    flash("Casa creada correctamente", "success")
    return redirect(url_for("casas.listar_casas"))

# Toggle activo
@casa_bp.route("/toggle/<int:id>")
def toggle_casa(id):
    casa = Casa.query.get_or_404(id)
    casa.activo = not casa.activo
    db.session.commit()
    return redirect(url_for("casas.listar_casas"))
