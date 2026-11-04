from flask import Blueprint, render_template, send_from_directory, current_app, make_response, redirect, url_for, abort
from flask_login import login_required, current_user
from app import db
from app.decorators import admin_required

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
@login_required
def home():
    from app.models.products import Product
    from app.models.visit import Visit
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

    novedades = []
    if current_user.is_admin() or current_user.username == 'root':
        novedades = Visit.query.filter(
            Visit.observaciones != None,
            Visit.observaciones != '',
            ~Visit.observaciones.in_(['[EXTRA_MANUAL]', '[DEUDA_ANTERIOR]']),
            Visit.novedad_vista == False
        ).order_by(Visit.fecha.desc()).all()

    return render_template("home.html", sin_stock=sin_stock, stock_bajo=stock_bajo, novedades=novedades)


@main_bp.route("/marcar-novedad-vista/<int:visit_id>", methods=["POST"])
@login_required
def marcar_novedad_vista(visit_id):
    if not (current_user.is_admin() or current_user.username == 'root'):
        abort(403)
    from app.models.visit import Visit
    visit = Visit.query.get_or_404(visit_id)
    visit.novedad_vista = True
    db.session.commit()
    return redirect(url_for("main.home"))

# NUEVA RUTA PARA LA APP INSTALABLE
@main_bp.route('/sw.js')
def sw():
    response = make_response(send_from_directory(current_app.static_folder, 'sw.js'))
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Cache-Control'] = 'no-cache'
    return response
