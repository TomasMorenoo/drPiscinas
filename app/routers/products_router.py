from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app import db
from app.models.products import Product

product_bp = Blueprint(
    "products",
    __name__,
    url_prefix="/products"
)

@product_bp.route("/")
@login_required
def listar_products():
    # Traemos todos los productos (activos o pausados) para poder gestionarlos
    # pero filtramos los que fueron "eliminados" (borrado lógico)
    products = Product.query.order_by(Product.nombre).all()
    return render_template("products/list.html", products=products)

@product_bp.route("/create", methods=["GET", "POST"])
@login_required
def crear_product():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        unidad = request.form.get("unidad", "").strip()
        precio = request.form.get("precio", "").strip()
        
        if not nombre or not precio:
            flash("Nombre y precio son obligatorios", "error")
            return redirect(url_for("products.listar_products"))

        product = Product(nombre=nombre, unidad=unidad, precio=float(precio))
        db.session.add(product)
        db.session.commit()
        flash("Producto creado correctamente", "success")
        return redirect(url_for("products.listar_products"))
    return render_template("products/create.html")

@product_bp.route("/edit/<int:id>", methods=["POST"])
@login_required
def editar_product(id):
    producto = Product.query.get_or_404(id)
    producto.nombre = request.form.get("nombre", "").strip()
    producto.unidad = request.form.get("unidad", "").strip()
    producto.precio = float(request.form.get("precio", 0))
    db.session.commit()
    flash("Producto actualizado", "success")
    return redirect(url_for("products.listar_products"))

@product_bp.route("/toggle/<int:id>", methods=["POST"])
@login_required
def toggle_product(id):
    producto = Product.query.get_or_404(id)
    producto.activo = not producto.activo  # Cambia entre True/False
    db.session.commit()
    estado = "activado" if producto.activo else "pausado"
    flash(f"Producto {estado} correctamente", "info")
    return redirect(url_for("products.listar_products"))

@product_bp.route("/delete/<int:id>", methods=["POST"])
@login_required
def eliminar_product(id):
    producto = Product.query.get_or_404(id)
    # Si preferís borrarlo de la base de datos: db.session.delete(producto)
    # Pero si tiene visitas asociadas, mejor es ocultarlo con un flag de 'borrado'
    db.session.delete(producto) 
    db.session.commit()
    flash("Producto eliminado", "success")
    return redirect(url_for("products.listar_products"))