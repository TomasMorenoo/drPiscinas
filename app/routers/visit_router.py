from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from app import db
from app.models.visit import Visit
from app.models.visit_product import VisitProduct
from app.models.casa import Casa
from app.models.products import Product
from app.models.promo import Promo
from sqlalchemy import extract, func
from datetime import datetime

visit_bp = Blueprint(
    "visits",
    __name__,
    url_prefix="/visits"
)

@visit_bp.route("/")
@login_required
def listar_visits():
    ahora = datetime.now()
    mes_sel = request.args.get('mes', ahora.month, type=int)
    anio_sel = request.args.get('anio', ahora.year, type=int)

    # Filtrado por mes y año
    visits = Visit.query.filter(
        extract('month', Visit.fecha) == mes_sel,
        extract('year', Visit.fecha) == anio_sel
    ).order_by(Visit.fecha.desc()).all()

    # Cálculo de facturación mensual usando los precios capturados
    total_mes = sum(v.calcular_total() for v in visits)

    # Top 5 productos usados
    top_productos = db.session.query(
        Product.nombre, 
        Product.unidad,
        func.sum(VisitProduct.cantidad).label('total_cantidad')
    ).join(VisitProduct, Product.id == VisitProduct.product_id)\
     .join(Visit, Visit.id == VisitProduct.visit_id)\
     .filter(extract('month', Visit.fecha) == mes_sel)\
     .filter(extract('year', Visit.fecha) == anio_sel)\
     .group_by(Product.nombre, Product.unidad)\
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

@visit_bp.route("/sync-prices", methods=["POST"])
@login_required
def sync_prices():
    mes = request.form.get('mes', type=int)
    anio = request.form.get('anio', type=int)

    if not mes or not anio:
        flash("Período no válido", "error")
        return redirect(url_for('visits.listar_visits'))

    visits = Visit.query.filter(
        extract('month', Visit.fecha) == mes,
        extract('year', Visit.fecha) == anio
    ).all()

    for v in visits:
        for vp in v.productos:
            prod_actual = Product.query.get(vp.product_id)
            if prod_actual:
                vp.precio_unitario = prod_actual.precio
    
    db.session.commit()
    flash(f"Precios actualizados para todo el mes {mes}/{anio}", "success")
    return redirect(url_for('visits.listar_visits', mes=mes, anio=anio))

@visit_bp.route("/create", methods=["GET", "POST"])
@login_required
def crear_visit():
    if request.method == "POST":
        casa_id = request.form.get("casa_id")
        fecha_str = request.form.get("fecha")
        promo_id = request.form.get("promo_id")
        product_ids = request.form.getlist("product_id[]")
        cantidades = request.form.getlist("cantidad[]")

        if not casa_id or not fecha_str:
            flash("Casa y fecha son obligatorios", "error")
            return redirect(url_for("visits.crear_visit"))

        visit = Visit(
            casa_id=casa_id,
            fecha=datetime.strptime(fecha_str, '%Y-%m-%d'),
            observaciones=request.form.get("observaciones", "").strip(),
            promo_id=promo_id if promo_id else None
        )
        db.session.add(visit)
        db.session.commit()

        for p_id, cant in zip(product_ids, cantidades):
            if p_id and cant:
                prod = Product.query.get(p_id)
                if prod:
                    vp = VisitProduct(
                        visit_id=visit.id, 
                        product_id=p_id, 
                        cantidad=float(cant),
                        precio_unitario=prod.precio
                    )
                    db.session.add(vp)
        
        db.session.commit()
        flash("Visita registrada correctamente", "success")
        return redirect(url_for("visits.listar_visits"))
        
    casas = Casa.query.filter_by(activo=True).all()
    products = Product.query.filter_by(activo=True).order_by(Product.nombre).all()
    promos = Promo.query.filter_by(activo=True).order_by(Promo.nombre).all()
    return render_template("visits/create.html", casas=casas, products=products, promos=promos)

@visit_bp.route("/delete/<int:id>", methods=["POST"])
@login_required
def eliminar_visit(id):
    visit = Visit.query.get_or_404(id)
    VisitProduct.query.filter_by(visit_id=id).delete()
    db.session.delete(visit)
    db.session.commit()
    flash("Visita eliminada", "success")
    return redirect(url_for("visits.listar_visits"))

@visit_bp.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def editar_visit(id):
    visit = Visit.query.get_or_404(id)
    if request.method == "POST":
        visit.casa_id = request.form.get("casa_id")
        visit.fecha = datetime.strptime(request.form.get("fecha"), '%Y-%m-%d')
        visit.observaciones = request.form.get("observaciones", "").strip()
        visit.promo_id = request.form.get("promo_id") or None
        
        VisitProduct.query.filter_by(visit_id=id).delete()
        product_ids = request.form.getlist("product_id[]")
        cantidades = request.form.getlist("cantidad[]")
        
        for p_id, cant in zip(product_ids, cantidades):
            if p_id and cant:
                prod = Product.query.get(p_id)
                if prod:
                    vp = VisitProduct(visit_id=id, product_id=p_id, cantidad=float(cant), precio_unitario=prod.precio)
                    db.session.add(vp)
        
        db.session.commit()
        flash("Visita actualizada", "success")
        return redirect(url_for("visits.listar_visits"))
        
    casas = Casa.query.filter_by(activo=True).all()
    products = Product.query.filter_by(activo=True).all()
    promos = Promo.query.filter_by(activo=True).all()
    return render_template("visits/create.html", visit=visit, casas=casas, products=products, promos=promos)