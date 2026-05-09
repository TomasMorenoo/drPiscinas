from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.decorators import admin_required
from app import db
from app.models.products import Product
from app.models.movimiento_stock import MovimientoStock

stock_bp = Blueprint("stock", __name__, url_prefix="/stock")


@stock_bp.route("/")
@login_required
@admin_required
def index():
    from app.models.configuracion import Configuracion
    products = Product.query.filter_by(activo=True).filter(db.func.lower(Product.nombre) != 'deuda').order_by(Product.nombre).all()
    movimientos = MovimientoStock.query.order_by(MovimientoStock.fecha.desc()).limit(30).all()
    stock_activo_desde = Configuracion.get("stock_activo_desde", None)
    return render_template("stock/index.html", products=products, movimientos=movimientos, stock_activo_desde=stock_activo_desde)


@stock_bp.route("/umbral/<int:id>", methods=["POST"])
@login_required
@admin_required
def set_umbral(id):
    prod = Product.query.get_or_404(id)
    val = request.form.get("stock_minimo", "").strip()
    prod.stock_minimo = float(val) if val else None
    db.session.commit()
    flash(f"Umbral de {prod.nombre} actualizado.", "success")
    return redirect(url_for("stock.index"))


@stock_bp.route("/ingreso", methods=["POST"])
@login_required
@admin_required
def ingreso():
    product_id = request.form.get("product_id", type=int)
    cantidad = request.form.get("cantidad", type=float)
    motivo = request.form.get("motivo", "").strip()

    if not product_id or not cantidad or cantidad <= 0:
        flash("Producto y cantidad positiva son obligatorios.", "error")
        return redirect(url_for("stock.index"))

    prod = Product.query.get_or_404(product_id)
    prod.stock_actual = float(prod.stock_actual) + cantidad

    mov = MovimientoStock(
        product_id=product_id,
        tipo="ingreso",
        cantidad=cantidad,
        motivo=motivo or None,
        usuario=current_user.username,
    )
    db.session.add(mov)
    db.session.commit()
    flash(f"Ingreso de {cantidad} {prod.unidad} de {prod.nombre} registrado.", "success")
    return redirect(url_for("stock.index"))


@stock_bp.route("/ajuste", methods=["POST"])
@login_required
@admin_required
def ajuste():
    product_id = request.form.get("product_id", type=int)
    cantidad = request.form.get("cantidad", type=float)
    motivo = request.form.get("motivo", "").strip()

    if not product_id or cantidad is None:
        flash("Producto y cantidad son obligatorios.", "error")
        return redirect(url_for("stock.index"))

    prod = Product.query.get_or_404(product_id)
    prod.stock_actual = float(prod.stock_actual) + cantidad

    mov = MovimientoStock(
        product_id=product_id,
        tipo="ajuste",
        cantidad=cantidad,
        motivo=motivo or None,
        usuario=current_user.username,
    )
    db.session.add(mov)
    db.session.commit()
    flash(f"Ajuste de {cantidad:+g} {prod.unidad} aplicado a {prod.nombre}.", "success")
    return redirect(url_for("stock.index"))
