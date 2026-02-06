from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from app.models.visit import Visit
from app.models.visit_product import VisitProduct
from app.models.casa import Casa
from app.models.products import Product
from app.models.promo import Promo


visit_bp = Blueprint(
    "visits",
    __name__,
    url_prefix="/visits"
)

@visit_bp.route("/")
def listar_visits():
    visits = Visit.query.order_by(Visit.fecha.desc()).all()
    return render_template("visits/list.html", visits=visits)

@visit_bp.route("/create", methods=["GET"])
def form_crear_visit():
    casas = Casa.query.filter_by(activo=True).order_by(Casa.numero).all()
    products = Product.query.filter_by(activo=True).order_by(Product.nombre).all()
    promos = Promo.query.filter_by(activo=True).order_by(Promo.nombre).all()
    

    return render_template(
        "visits/create.html",
        casas=casas,
        products=products,
        promos=promos
    )

@visit_bp.route("/create", methods=["POST"])
def crear_visit():
    casa_id = request.form.get("casa_id")
    fecha = request.form.get("fecha")
    observaciones = request.form.get("observaciones", "").strip()
    promo_id = request.form.get("promo_id")

    product_ids = request.form.getlist("product_id[]")
    cantidades = request.form.getlist("cantidad[]")

    # =========================
    # VALIDACIONES BÁSICAS
    # =========================
    if not casa_id or not fecha:
        flash("Casa y fecha son obligatorios", "error")
        return redirect(url_for("visits.form_crear_visit"))

    # =========================
    # CREAR VISITA
    # =========================
    visit = Visit(
        casa_id=casa_id,
        fecha=fecha,
        observaciones=observaciones,
        promo_id=promo_id if promo_id else None
    )

    db.session.add(visit)
    db.session.commit()  # necesario para visit.id

    # =========================
    # PRODUCTOS MANUALES
    # =========================
    for p_id, cant in zip(product_ids, cantidades):
        if not p_id or not cant:
            continue

        try:
            cantidad = float(cant)
        except ValueError:
            continue

        if cantidad > 0:
            vp = VisitProduct(
                visit_id=visit.id,
                product_id=p_id,
                cantidad=cantidad
            )
            db.session.add(vp)

    db.session.commit()

    flash("Visita creada correctamente", "success")
    return redirect(url_for("visits.listar_visits"))

