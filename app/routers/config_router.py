from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime
import calendar
from app import db
from app.decorators import admin_required, root_required
from app.models.plantilla_mensaje import PlantillaMensaje, DEFAULT_TEMPLATE_INDIVIDUAL, DEFAULT_TEMPLATE_GRUPO, DEFAULT_TEMPLATE_RECORDATORIO
from app.models.configuracion import Configuracion
from app.models.casa import Casa
from app.models.products import Product
from app.models.visit import Visit
from app.models.visit_product import VisitProduct
from app.utils import mover_stock
from app.routers.dashboard_router import natural_sort_key

config_bp = Blueprint("config", __name__, url_prefix="/config")


@config_bp.route("/mensajes")
@login_required
@admin_required
def listar_plantillas():
    plantillas = PlantillaMensaje.query.order_by(PlantillaMensaje.activa.desc(), PlantillaMensaje.creada_en.desc()).all()
    return render_template("config/mensajes.html", plantillas=plantillas)


@config_bp.route("/mensajes/nueva", methods=["GET", "POST"])
@login_required
@admin_required
def crear_plantilla():
    if request.method == "POST":
        p = PlantillaMensaje(
            nombre                = request.form.get("nombre", "").strip(),
            template_individual   = request.form.get("template_individual", "").strip() or None,
            template_grupo        = request.form.get("template_grupo", "").strip() or None,
            template_recordatorio = request.form.get("template_recordatorio", "").strip() or None,
        )
        if not p.nombre:
            flash("El nombre es obligatorio.", "error")
            return render_template("config/mensajes_form.html", plantilla=p,
                                   default_individual=DEFAULT_TEMPLATE_INDIVIDUAL,
                                   default_grupo=DEFAULT_TEMPLATE_GRUPO,
                                   default_recordatorio=DEFAULT_TEMPLATE_RECORDATORIO, accion="nueva")
        db.session.add(p)
        db.session.commit()
        flash(f"Plantilla '{p.nombre}' creada.", "success")
        return redirect(url_for("config.listar_plantillas"))

    defaults = PlantillaMensaje()
    return render_template("config/mensajes_form.html", plantilla=defaults,
                           default_individual=DEFAULT_TEMPLATE_INDIVIDUAL,
                           default_grupo=DEFAULT_TEMPLATE_GRUPO,
                           default_recordatorio=DEFAULT_TEMPLATE_RECORDATORIO, accion="nueva")


@config_bp.route("/mensajes/<int:id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def editar_plantilla(id):
    p = PlantillaMensaje.query.get_or_404(id)

    if request.method == "POST":
        p.nombre                = request.form.get("nombre", "").strip()
        p.template_individual   = request.form.get("template_individual", "").strip() or None
        p.template_grupo        = request.form.get("template_grupo", "").strip() or None
        p.template_recordatorio = request.form.get("template_recordatorio", "").strip() or None

        if not p.nombre:
            flash("El nombre es obligatorio.", "error")
            return render_template("config/mensajes_form.html", plantilla=p,
                                   default_individual=DEFAULT_TEMPLATE_INDIVIDUAL,
                                   default_grupo=DEFAULT_TEMPLATE_GRUPO,
                                   default_recordatorio=DEFAULT_TEMPLATE_RECORDATORIO, accion="editar")
        db.session.commit()
        flash(f"Plantilla '{p.nombre}' guardada.", "success")
        return redirect(url_for("config.listar_plantillas"))

    return render_template("config/mensajes_form.html", plantilla=p,
                           default_individual=DEFAULT_TEMPLATE_INDIVIDUAL,
                           default_grupo=DEFAULT_TEMPLATE_GRUPO,
                           default_recordatorio=DEFAULT_TEMPLATE_RECORDATORIO, accion="editar")


@config_bp.route("/mensajes/<int:id>/activar", methods=["POST"])
@login_required
@admin_required
def activar_plantilla(id):
    p = PlantillaMensaje.query.get_or_404(id)
    p.activar()
    db.session.commit()
    flash(f"Plantilla '{p.nombre}' activada.", "success")
    return redirect(url_for("config.listar_plantillas"))


@config_bp.route("/mensajes/<int:id>/eliminar", methods=["POST"])
@login_required
@admin_required
def eliminar_plantilla(id):
    p = PlantillaMensaje.query.get_or_404(id)
    if p.activa:
        flash("No podés eliminar la plantilla activa.", "error")
        return redirect(url_for("config.listar_plantillas"))
    nombre = p.nombre
    db.session.delete(p)
    db.session.commit()
    flash(f"Plantilla '{nombre}' eliminada.", "success")
    return redirect(url_for("config.listar_plantillas"))


@config_bp.route("/proporcional", methods=["GET", "POST"])
@login_required
@root_required
def config_proporcional():
    if request.method == "POST":
        accion = request.form.get("accion")
        if accion == "desactivar":
            Configuracion.set('proporcional_desde', None)
            db.session.commit()
            flash("Sistema proporcional desactivado.", "success")
        elif accion == "guardar":
            mes = request.form.get("mes", type=int)
            anio = request.form.get("anio", type=int)
            if mes and anio and 1 <= mes <= 12 and anio >= 2020:
                Configuracion.set('proporcional_desde', {'mes': mes, 'anio': anio})
                db.session.commit()
                flash(f"Sistema proporcional activo desde {mes}/{anio}.", "success")
            else:
                flash("Mes o año inválido.", "error")
        return redirect(url_for("config.config_proporcional"))

    cfg = Configuracion.get('proporcional_desde')
    return render_template("config/proporcional.html", cfg=cfg)


@config_bp.route("/extras-masivos", methods=["GET", "POST"])
@login_required
@admin_required
def extras_masivos():
    _trim = db.func.trim(Product.nombre)
    _priority = db.case(
        (_trim.ilike('pastilla de cloro'), 0),
        (_trim.ilike('clarificador'), 1),
        (_trim.ilike('granulado lento'), 2),
        (_trim.ilike('granulado rapido'), 3),
        else_=4
    )
    productos = Product.query.filter(
        Product.activo == True,
        db.func.lower(Product.nombre) != 'deuda'
    ).order_by(_priority, Product.nombre).all()
    casas = sorted(Casa.query.filter_by(activo=True).all(), key=natural_sort_key)
    now = datetime.now()

    if request.method == "POST":
        product_ids = request.form.getlist("product_id", type=int)
        cantidad = request.form.get("cantidad", type=float)
        mes = request.form.get("mes", type=int)
        anio = request.form.get("anio", type=int)
        casa_ids = request.form.getlist("casa_ids", type=int)

        if not product_ids or not cantidad or not mes or not anio or not casa_ids:
            flash("Completá todos los campos y seleccioná al menos una casa y un producto.", "error")
            return render_template("config/extras_masivos.html", productos=productos, casas=casas, now=now)

        ultimo_dia = calendar.monthrange(anio, mes)[1]
        fecha_fantasma = datetime(anio, mes, ultimo_dia, 12, 0, 0)
        productos_obj = {p.id: p for p in Product.query.filter(Product.id.in_(product_ids)).all()}

        ya_tienen = []
        agregadas = 0

        for casa_id in casa_ids:
            for product_id in product_ids:
                existente = (
                    Visit.query
                    .join(VisitProduct)
                    .filter(
                        Visit.casa_id == casa_id,
                        Visit.observaciones == "[EXTRA_MANUAL]",
                        db.extract("month", Visit.fecha) == mes,
                        db.extract("year", Visit.fecha) == anio,
                        VisitProduct.product_id == product_id,
                    )
                    .first()
                )
                if existente:
                    casa = Casa.query.get(casa_id)
                    producto = productos_obj[product_id]
                    ya_tienen.append(f"{casa.nombre_formateado()} ({producto.nombre})")
                    continue

                producto = productos_obj[product_id]
                nueva_visita = Visit(
                    casa_id=casa_id,
                    usuario_id=current_user.id,
                    fecha=fecha_fantasma,
                    observaciones="[EXTRA_MANUAL]"
                )
                db.session.add(nueva_visita)
                db.session.flush()

                nuevo_vp = VisitProduct(
                    visit_id=nueva_visita.id,
                    product_id=product_id,
                    cantidad=cantidad,
                    precio_unitario=producto.precio
                )
                db.session.add(nuevo_vp)
                mover_stock(product_id, -cantidad, 'visita', current_user.username, visit_id=nueva_visita.id, motivo='extra masivo')
                agregadas += 1

        db.session.commit()

        if agregadas:
            flash(f"{agregadas} extra(s) agregado(s) correctamente.", "success")
        if ya_tienen:
            flash(f"Ya existían: {', '.join(ya_tienen)}.", "warning")

        return redirect(url_for("config.extras_masivos"))

    return render_template("config/extras_masivos.html", productos=productos, casas=casas, now=now)


@config_bp.route("/extras-masivos/check")
@login_required
@admin_required
def extras_masivos_check():
    casa_id = request.args.get("casa_id", type=int)
    mes = request.args.get("mes", type=int)
    anio = request.args.get("anio", type=int)
    product_ids = request.args.getlist("product_ids", type=int)

    if not casa_id or not mes or not anio or not product_ids:
        return jsonify([])

    conflictos = []
    for product_id in product_ids:
        existente = (
            Visit.query
            .join(VisitProduct)
            .filter(
                Visit.casa_id == casa_id,
                Visit.observaciones == "[EXTRA_MANUAL]",
                db.extract("month", Visit.fecha) == mes,
                db.extract("year", Visit.fecha) == anio,
                VisitProduct.product_id == product_id,
            )
            .first()
        )
        if existente:
            producto = Product.query.get(product_id)
            conflictos.append(producto.nombre if producto else str(product_id))

    return jsonify(conflictos)
