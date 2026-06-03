from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.decorators import admin_required
from app import db
from app.models.products import Product
from app.utils import registrar_auditoria
from sqlalchemy import case

product_bp = Blueprint("products", __name__, url_prefix="/products")

def _parse_precio(value):
    if not value:
        return 0.0
    v = value.strip()
    if ',' in v:
        v = v.replace('.', '').replace(',', '.')
    return float(v)

@product_bp.route("/")
@login_required
@admin_required
def listar_products():
    _trim = db.func.trim(Product.nombre)
    _priority = case(
        (_trim.ilike('pastilla de cloro'), 0),
        (_trim.ilike('clarificador'), 1),
        (_trim.ilike('granulado lento'), 2),
        (_trim.ilike('granulado rapido'), 3),
        else_=4
    )
    products = Product.query.filter(db.func.lower(Product.nombre) != 'deuda').order_by(_priority, Product.nombre).all()
    return render_template("products/list.html", products=products)

@product_bp.route("/create", methods=["GET", "POST"])
@login_required
@admin_required
def crear_product():
    if request.method == "POST":
        nombre = request.form.get("nombre")
        precio = request.form.get("precio")
        unidad = request.form.get("unidad")

        if not nombre or not precio or not unidad:
            flash("Todos los campos son obligatorios", "error")
            return redirect(url_for("products.crear_product"))

        nuevo = Product(nombre=nombre, precio=_parse_precio(precio), unidad=unidad)
        db.session.add(nuevo)
        db.session.commit()
        registrar_auditoria(current_user.username, 'CREAR_PRODUCTO', f"{nombre} — ${precio} / {unidad}")
        db.session.commit()
        flash("Producto creado", "success")
        return redirect(url_for("products.listar_products"))
        
    return render_template("products/create.html")

@product_bp.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def editar_product(id):
    prod = Product.query.get_or_404(id)
    if request.method == "POST":
        prod.nombre = request.form.get("nombre")
        prod.precio = _parse_precio(request.form.get("precio"))
        prod.unidad = request.form.get("unidad")
        db.session.commit()
        registrar_auditoria(current_user.username, 'EDITAR_PRODUCTO', f"{prod.nombre} — ${prod.precio} / {prod.unidad}")
        db.session.commit()
        flash("Producto actualizado", "success")
        return redirect(url_for("products.listar_products"))
    return render_template("products/create.html", product=prod)

@product_bp.route("/toggle/<int:id>")
@login_required
@admin_required
def toggle_product(id):
    prod = Product.query.get_or_404(id)
    prod.activo = not prod.activo
    db.session.commit()
    return redirect(url_for("products.listar_products"))

@product_bp.route("/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
def eliminar_product(id):
    prod = Product.query.get_or_404(id)
    try:
        nombre_prod = prod.nombre
        registrar_auditoria(current_user.username, 'ELIMINAR_PRODUCTO', nombre_prod)
        db.session.delete(prod)
        db.session.commit()
        flash("Producto eliminado correctamente.", "success")
    except Exception as e:
        db.session.rollback()
        flash("No se puede eliminar el producto porque ya fue usado en visitas o promociones. Te sugerimos pausarlo.", "error")
    return redirect(url_for("products.listar_products"))