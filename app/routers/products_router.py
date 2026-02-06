from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import Product

product_bp = Blueprint(
    "products",
    __name__,
    url_prefix="/products"
)

# Listado de productos
@product_bp.route("/")
def listar_products():
    products = Product.query.order_by(Product.nombre).all()
    return render_template("products/list.html", products=products)

# Formulario GET
@product_bp.route("/create", methods=["GET"])
def form_crear_product():
    return render_template("products/create.html")

# Crear POST
@product_bp.route("/create", methods=["POST"])
def crear_product():
    nombre = request.form.get("nombre", "").strip()
    unidad = request.form.get("unidad", "").strip()
    precio = request.form.get("precio", "").strip()

    if not nombre or not unidad or not precio:
        flash("Todos los campos son obligatorios", "error")
        return redirect(url_for("products.listar_products"))

    existe = Product.query.filter_by(nombre=nombre).first()
    if existe:
        flash("Ese producto ya existe", "error")
        return redirect(url_for("products.listar_products"))

    product = Product(nombre=nombre, unidad=unidad, precio=precio)
    db.session.add(product)
    db.session.commit()
    flash("Producto creado correctamente", "success")
    return redirect(url_for("products.listar_products"))

# Activar / desactivar
@product_bp.route("/toggle/<int:id>")
def toggle_product(id):
    product = Product.query.get_or_404(id)
    product.activo = not product.activo
    db.session.commit()
    return redirect(url_for("products.listar_products"))
