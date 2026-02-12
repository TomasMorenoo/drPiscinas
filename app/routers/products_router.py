from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app import db
from app.models.products import Product

products_bp = Blueprint("products", __name__, url_prefix="/products")

@products_bp.route("/")
@login_required
def listar_products():
    # Solo mostramos productos activos en la lista principal
    products = Product.query.filter_by(activo=True).order_by(Product.nombre).all()
    return render_template("products/list.html", products=products)

@products_bp.route("/create", methods=["GET", "POST"])
@login_required
def crear_product():
    if request.method == "POST":
        nombre = request.form.get("nombre")
        unidad = request.form.get("unidad")
        precio = request.form.get("precio")

        if not nombre or not precio:
            flash("Nombre y precio son obligatorios", "danger")
            return redirect(url_for("products.crear_product"))

        nuevo_p = Product(nombre=nombre, unidad=unidad, precio=float(precio))
        db.session.add(nuevo_p)
        db.session.commit()
        flash("Producto creado con éxito", "success")
        return redirect(url_for("products.listar_products"))
    
    return render_template("products/create.html")

@products_bp.route("/edit/<int:id>", methods=["POST"])
@login_required
def editar_product(id):
    producto = Product.query.get_or_404(id)
    producto.nombre = request.form.get("nombre")
    producto.unidad = request.form.get("unidad")
    producto.precio = float(request.form.get("precio"))
    
    db.session.commit()
    flash("Producto actualizado correctamente", "success")
    return redirect(url_for("products.listar_products"))

@products_bp.route("/delete/<int:id>", methods=["POST"])
@login_required
def eliminar_product(id):
    producto = Product.query.get_or_404(id)
    # En lugar de borrar, desactivamos para no romper el historial de visitas
    producto.activo = False 
    db.session.commit()
    flash("Producto eliminado de la lista", "success")
    return redirect(url_for("products.listar_products"))