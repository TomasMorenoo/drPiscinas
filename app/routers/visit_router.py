from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from app import db
from app.models.visit import Visit
from app.models.visit_product import VisitProduct
from app.models.casa import Casa
from app.models.products import Product
from app.models.promo import Promo
from sqlalchemy import extract, func # <--- Para filtros y estadísticas
from datetime import datetime

visit_bp = Blueprint(
    "visits",
    __name__,
    url_prefix="/visits"
)

@visit_bp.route("/")
@login_required
def listar_visits():
    # 1. Obtener parámetros de filtrado (por defecto mes y año actual)
    ahora = datetime.now()
    mes_sel = request.args.get('mes', ahora.month, type=int)
    anio_sel = request.args.get('anio', ahora.year, type=int)

    # 2. Query de visitas filtrada
    visits = Visit.query.filter(
        extract('month', Visit.fecha) == mes_sel,
        extract('year', Visit.fecha) == anio_sel
    ).order_by(Visit.fecha.desc()).all()

    # 3. Calcular total facturado en el mes seleccionado
    total_mes = sum(v.calcular_total() for v in visits)

    # 4. Top 5 productos más usados en el mes
    top_productos = db.session.query(
        Product.nombre, 
        func.sum(VisitProduct.cantidad).label('total_cantidad')
    ).join(VisitProduct, Product.id == VisitProduct.product_id)\
     .join(Visit, Visit.id == VisitProduct.visit_id)\
     .filter(extract('month', Visit.fecha) == mes_sel)\
     .filter(extract('year', Visit.fecha) == anio_sel)\
     .group_by(Product.nombre)\
     .order_by(func.sum(VisitProduct.cantidad).desc())\
     .limit(5).all()

    return render_template(
        "visits/list.html", 
        visits=visits,
        total_mes=total_mes,
        top_productos=top_productos,
        mes_sel=mes_sel,
        anio_sel=anio_sel
    )

@visit_bp.route("/create", methods=["GET"])
@login_required
def form_crear_visit():
    casas = Casa.query.filter_by(activo=True).all()
    products = Product.query.filter_by(activo=True).order_by(Product.nombre).all()
    promos = Promo.query.filter_by(activo=True).order_by(Promo.nombre).all()
    
    return render_template(
        "visits/create.html",
        casas=casas,
        products=products,
        promos=promos
    )

@visit_bp.route("/create", methods=["POST"])
@login_required
def crear_visit():
    casa_id = request.form.get("casa_id")
    fecha = request.form.get("fecha")
    observaciones = request.form.get("observaciones", "").strip()
    promo_id = request.form.get("promo_id")

    product_ids = request.form.getlist("product_id[]")
    cantidades = request.form.getlist("cantidad[]")

    if not casa_id or not fecha:
        flash("Casa y fecha son obligatorios", "error")
        return redirect(url_for("visits.form_crear_visit"))

    visit = Visit(
        casa_id=casa_id,
        fecha=fecha,
        observaciones=observaciones,
        promo_id=promo_id if promo_id else None
    )

    db.session.add(visit)
    db.session.commit()

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