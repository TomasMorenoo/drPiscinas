from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app import db
from app.models.products import Product

# Se define como product_bp para coincidir con la importación en __init__.py
product_bp = Blueprint(
    "products",
    __name__,
    url_prefix="/products"
)

# Listado de productos
@product_bp.route("/")
@login_required
def listar_products():
    # Mostramos productos activos para la gestión diaria
    products = Product.query.filter_by(activo=True).order_by(Product.nombre).all()
    return render_template("products/list.html", products=products)

# Formulario GET (Opcional si usas modales, pero lo mantenemos por compatibilidad)
@product_bp.route("/create", methods=["GET"])
@login_required
def form_crear_product():
    return render_template("products/create.html")

# Crear POST
@product_bp.route("/create", methods=["POST"])
@login_required
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

    product = Product(nombre=nombre, unidad=unidad, precio=float(precio))
    db.session.add(product)
    db.session.commit()
    flash("Producto creado correctamente", "success")
    return redirect(url_for("products.listar_products"))

# Editar Producto (POST desde el Modal)
@product_bp.route("/edit/<int:id>", methods=["POST"])
@login_required
def editar_product(id):
    producto = Product.query.get_or_404(id)
    producto.nombre = request.form.get("nombre", "").strip()
    producto.unidad = request.form.get("unidad", "").strip()
    producto.precio = float(request.form.get("precio", 0))
    
    db.session.commit()
    flash("Producto actualizado correctamente", "success")
    return redirect(url_for("products.listar_products"))

# Eliminación Lógica (Desactivar)
@product_bp.route("/delete/<int:id>", methods=["POST"])
@login_required
def eliminar_product(id):
    producto = Product.query.get_or_404(id)
    # Cambiamos el estado a inactivo para no borrar el historial de visitas
    producto.activo = False 
    db.session.commit()
    flash("Producto eliminado de la lista", "success")
    return redirect(url_for("products.listar_products"))