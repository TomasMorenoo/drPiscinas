from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models.promo import Promo
from app.models.products import Product
from app.models.promo_product import PromoProduct

promo_bp = Blueprint(
    "promo",
    __name__,
    url_prefix="/promos"
)

# =========================
# LISTAR PROMOS
# =========================
@promo_bp.route("/")
def listar_promos():
    promos = Promo.query.order_by(Promo.nombre).all()
    return render_template("promos/list.html", promos=promos)


# =========================
# CREAR PROMO
# =========================
@promo_bp.route("/create", methods=["GET", "POST"])
def crear_promo():
    productos = Product.query.filter_by(activo=True).order_by(Product.nombre).all()

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        precio = request.form.get("precio", "").strip()

        if not nombre or not precio:
            flash("Nombre y precio son obligatorios", "error")
            return redirect(url_for("promo.crear_promo"))

        existe = Promo.query.filter_by(nombre=nombre).first()
        if existe:
            flash("Ya existe una promo con ese nombre", "error")
            return redirect(url_for("promo.crear_promo"))

        promo = Promo(nombre=nombre, precio=precio)
        db.session.add(promo)
        db.session.commit()  # necesario para tener promo.id

        productos_agregados = 0

        for producto in productos:
            valor = request.form.get(f"producto_{producto.id}")

            if not valor:
                continue

            try:
                cantidad = float(valor)
            except ValueError:
                continue

            if cantidad > 0.1:
                db.session.add(PromoProduct(
                    promo_id=promo.id,
                    product_id=producto.id,
                    cantidad=cantidad
                ))
                productos_agregados += 1

        # ❌ NO permitir promos vacías
        if productos_agregados == 0:
            db.session.delete(promo)
            db.session.commit()
            flash("La promo debe tener al menos un producto con cantidad mayor a 0", "error")
            return redirect(url_for("promo.crear_promo"))

        db.session.commit()
        flash("Promoción creada correctamente", "success")
        return redirect(url_for("promo.listar_promos"))

    return render_template(
        "promos/form.html",
        promo=None,
        productos=productos
    )


# =========================
# EDITAR PROMO
# =========================
@promo_bp.route("/<int:id>/edit", methods=["GET", "POST"])
def editar_promo(id):
    promo = Promo.query.get_or_404(id)
    productos = Product.query.filter_by(activo=True).order_by(Product.nombre).all()

    if request.method == "POST":
        promo.nombre = request.form.get("nombre", "").strip()
        promo.precio = request.form.get("precio")

        # borrar relaciones anteriores
        PromoProduct.query.filter_by(promo_id=promo.id).delete()

        productos_agregados = 0

        for producto in productos:
            valor = request.form.get(f"producto_{producto.id}")

            if not valor:
                continue

            try:
                cantidad = float(valor)
            except ValueError:
                continue

            if cantidad > 0.1:
                db.session.add(PromoProduct(
                    promo_id=promo.id,
                    product_id=producto.id,
                    cantidad=cantidad
                ))
                productos_agregados += 1

        # ❌ NO permitir promos sin productos
        if productos_agregados == 0:
            flash("La promo debe tener al menos un producto", "error")
            return redirect(url_for("promo.editar_promo", id=promo.id))

        db.session.commit()
        flash("Promo actualizada correctamente", "success")
        return redirect(url_for("promo.listar_promos"))

    return render_template(
        "promos/form.html",
        promo=promo,
        productos=productos
    )


# =========================
# ACTIVAR / DESACTIVAR PROMO
# =========================
@promo_bp.route("/toggle/<int:id>")
def toggle_promo(id):
    promo = Promo.query.get_or_404(id)
    promo.activo = not promo.activo
    db.session.commit()
    return redirect(url_for("promo.listar_promos"))
