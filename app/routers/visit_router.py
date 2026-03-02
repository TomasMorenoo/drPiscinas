from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.visit import Visit
from app.models.visit_product import VisitProduct
from app.models.casa import Casa
from app.models.products import Product
from app.models.promo import Promo
from app.models.abono_historico import AbonoHistorico 
from app.models.cierre_mes import CierreMes  # <-- IMPORTAMOS EL CANDADO
from sqlalchemy import extract, func
from datetime import datetime

visit_bp = Blueprint(
    "visits",
    __name__,
    url_prefix="/visits"
)

# --- FUNCIÓN DE AYUDA PARA SABER SI EL MES ESTÁ CERRADO ---
def is_mes_cerrado(mes, anio):
    # AHORA MIRA EL CANDADO NUEVO
    return CierreMes.query.filter_by(mes=mes, anio=anio).first() is not None

@visit_bp.route("/")
@login_required
def listar_visits():
    ahora = datetime.now()
    mes_sel = request.args.get('mes', ahora.month, type=int)
    anio_sel = request.args.get('anio', ahora.year, type=int)

    mes_congelado = is_mes_cerrado(mes_sel, anio_sel)

    visits = Visit.query.filter(
        extract('month', Visit.fecha) == mes_sel,
        extract('year', Visit.fecha) == anio_sel
    ).order_by(Visit.fecha.desc()).all()

    total_mes = sum(v.calcular_total() for v in visits)

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
        anio_sel=anio_sel,
        mes_congelado=mes_congelado 
    )

@visit_bp.route("/create", methods=["GET", "POST"])
@login_required
def crear_visit():
    if request.method == "POST":
        fecha_str = request.form.get("fecha")
        fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d')

        if is_mes_cerrado(fecha_obj.month, fecha_obj.year):
            flash("❌ No podés cargar una visita en un mes que ya está cerrado y facturado. Descongelalo desde el Dashboard primero.", "error")
            return redirect(url_for("visits.listar_visits"))

        casa_id = request.form.get("casa_id")
        promo_id = request.form.get("promo_id")
        product_ids = request.form.getlist("product_id[]")
        cantidades = request.form.getlist("cantidad[]")

        if not casa_id or not fecha_str:
            flash("Casa y fecha son obligatorios", "error")
            return redirect(url_for("visits.crear_visit"))

        visit = Visit(
            casa_id=casa_id,
            fecha=fecha_obj,
            observaciones=request.form.get("observaciones", "").strip(),
            promo_id=promo_id if promo_id else None,
            usuario_id=current_user.id 
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
    
    if is_mes_cerrado(visit.fecha.month, visit.fecha.year):
        flash("❌ No podés eliminar una visita de un mes cerrado.", "error")
        return redirect(url_for("visits.listar_visits"))

    VisitProduct.query.filter_by(visit_id=id).delete()
    db.session.delete(visit)
    db.session.commit()
    flash("Visita eliminada", "success")
    return redirect(url_for("visits.listar_visits"))

@visit_bp.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def editar_visit(id):
    visit = Visit.query.get_or_404(id)
    
    if is_mes_cerrado(visit.fecha.month, visit.fecha.year):
        flash("🔒 Este mes está cerrado. No se puede editar la visita.", "warning")
        return redirect(url_for("visits.listar_visits"))

    if request.method == "POST":
        nueva_fecha = datetime.strptime(request.form.get("fecha"), '%Y-%m-%d')
        
        if is_mes_cerrado(nueva_fecha.month, nueva_fecha.year):
            flash("❌ No podés mover la visita a un mes que ya está cerrado.", "error")
            return redirect(url_for("visits.listar_visits"))

        visit.casa_id = request.form.get("casa_id")
        visit.fecha = nueva_fecha
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

@visit_bp.route("/detalle/<int:id>")
@login_required
def detalle_visit(id):
    visit = Visit.query.get_or_404(id)
    return render_template("visits/detalle.html", visit=visit)