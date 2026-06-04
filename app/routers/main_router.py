from flask import Blueprint, render_template, send_from_directory, current_app, make_response
from flask_login import login_required
from app import db

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
@login_required
def home():
    from app.models.products import Product
    sin_stock = Product.query.filter(
        Product.activo == True,
        Product.stock_actual <= 0,
        db.func.lower(Product.nombre) != 'deuda'
    ).order_by(Product.nombre).all()
    stock_bajo = Product.query.filter(
        Product.activo == True,
        Product.stock_minimo != None,
        Product.stock_actual > 0,
        Product.stock_actual <= Product.stock_minimo,
        db.func.lower(Product.nombre) != 'deuda'
    ).order_by(Product.nombre).all()
    return render_template("home.html", sin_stock=sin_stock, stock_bajo=stock_bajo)

# NUEVA RUTA PARA LA APP INSTALABLE
@main_bp.route('/sw.js')
def sw():
    response = make_response(send_from_directory(current_app.static_folder, 'sw.js'))
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Cache-Control'] = 'no-cache'
    return response
