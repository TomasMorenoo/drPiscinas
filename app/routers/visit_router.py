from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db, csrf
from app.models.visit import Visit
from app.models.visit_product import VisitProduct
from app.utils import registrar_auditoria, mover_stock
from app.models.casa import Casa
from app.models.products import Product
from app.models.promo import Promo
from app.models.abono_historico import AbonoHistorico 
from app.models.cierre_mes import CierreMes  # <-- IMPORTAMOS EL CANDADO
from app.models.movimiento_stock import MovimientoStock
from app.models.visit_media import VisitMedia
from sqlalchemy import extract, func, case
from sqlalchemy.orm import selectinload
from datetime import datetime

visit_bp = Blueprint(
    "visits",
    __name__,
    url_prefix="/visits"
)

def is_mes_cerrado(mes, anio):
    # AHORA MIRA EL CANDADO NUEVO
    return CierreMes.query.filter_by(mes=mes, anio=anio).first() is not None

@visit_bp.route("/")
@login_required
def listar_visits():
    ahora = datetime.now()
    mes_sel = request.args.get('mes', ahora.month, type=int)
    anio_sel = request.args.get('anio', ahora.year, type=int)

    mes_congelado = is_mes_cerrado(mes_sel, anio_sel)

    # --- 1. OCULTAMOS LOS EXTRAS DE LA LISTA PRINCIPAL ---
    visits = Visit.query.filter(
        extract('month', Visit.fecha) == mes_sel,
        extract('year', Visit.fecha) == anio_sel,
        db.or_(Visit.observaciones != '[EXTRA_MANUAL]', Visit.observaciones.is_(None))
    ).order_by(Visit.id.desc()).all()

    total_mes = sum(v.calcular_total() for v in visits)
    total_visitas = len(visits)

    from collections import defaultdict
    _vpd = defaultdict(int)
    for v in visits:
        _vpd[v.fecha.day] += 1
    visitas_por_dia = sorted(_vpd.items())
    max_vpd = max(_vpd.values()) if _vpd else 1

    # --- 2. OCULTAMOS LOS EXTRAS DEL TOP PRODUCTOS ---
    top_productos = db.session.query(
        Product.nombre, 
        Product.unidad,
        func.sum(VisitProduct.cantidad).label('total_cantidad')
    ).join(VisitProduct, Product.id == VisitProduct.product_id)\
     .join(Visit, Visit.id == VisitProduct.visit_id)\
     .filter(extract('month', Visit.fecha) == mes_sel)\
     .filter(extract('year', Visit.fecha) == anio_sel)\
     .filter(db.or_(Visit.observaciones != '[EXTRA_MANUAL]', Visit.observaciones.is_(None)))\
     .group_by(Product.nombre, Product.unidad)\
     .order_by(func.sum(VisitProduct.cantidad).desc())\
     .limit(5).all()

    return render_template(
        "visits/list.html",
        visits=visits,
        total_mes=total_mes,
        total_visitas=total_visitas,
        visitas_por_dia=visitas_por_dia,
        max_vpd=max_vpd,
        top_productos=top_productos,
        mes_sel=mes_sel,
        anio_sel=anio_sel,
        mes_congelado=mes_congelado
    )
    
    
@visit_bp.route("/novedades")
@login_required
def historial_novedades():
    from datetime import date
    desde_fecha = date(2026, 3, 1)
    page = request.args.get('page', 1, type=int)
    per_page = 50

    paginacion = Visit.query.filter(
        Visit.observaciones != None,
        Visit.observaciones != '',
        ~Visit.observaciones.in_(['[EXTRA_MANUAL]', '[DEUDA_ANTERIOR]']),
        Visit.fecha >= desde_fecha
    ).order_by(Visit.fecha.desc()).paginate(page=page, per_page=per_page, error_out=False)

    return render_template("visits/novedades.html", paginacion=paginacion)


@visit_bp.route("/create", methods=["GET", "POST"])
@login_required
def crear_visit():
    if request.method == "POST":
        fecha_str = request.form.get("fecha")
        fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d')

        # Verificación de seguridad: No cargar visitas en meses ya cerrados
        if is_mes_cerrado(fecha_obj.month, fecha_obj.year):
            flash("❌ No podés cargar una visita en un mes que ya está cerrado y facturado. Descongelalo desde el Dashboard primero.", "error")
            return redirect(url_for("visits.listar_visits"))

        casa_id = request.form.get("casa_id")
        promo_id = request.form.get("promo_id")
        product_ids = request.form.getlist("product_id[]")
        cantidades = request.form.getlist("cantidad[]")

        if not casa_id or not fecha_str:
            flash("Casa y fecha son obligatorios", "error")
            return redirect(url_for("visits.crear_visit"))

        # Validar que la visita no sea anterior al inicio del cliente
        if casa_id:
            casa_check = Casa.query.get(casa_id)
            if casa_check and casa_check.fecha_creacion:
                inicio = casa_check.fecha_creacion.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                visita_inicio_mes = fecha_obj.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                if visita_inicio_mes < inicio:
                    meses = ['enero','febrero','marzo','abril','mayo','junio',
                             'julio','agosto','septiembre','octubre','noviembre','diciembre']
                    desde = f"{meses[casa_check.fecha_creacion.month-1].capitalize()} {casa_check.fecha_creacion.year}"
                    flash(f"❌ No podés cargar visitas anteriores al inicio del cliente ({desde}).", "error")
                    return redirect(url_for("visits.crear_visit"))

        # Crear la visita principal
        visit = Visit(
            casa_id=casa_id,
            fecha=fecha_obj,
            observaciones=request.form.get("observaciones", "").strip(),
            promo_id=promo_id if promo_id else None,
            usuario_id=current_user.id 
        )
        db.session.add(visit)
        db.session.commit()

        # Cargar los productos asociados (VisitProduct)
        for p_id, cant in zip(product_ids, cantidades):
            if p_id and cant:
                prod = Product.query.get(p_id)
                if prod:
                    vp = VisitProduct(
                        visit_id=visit.id,
                        product_id=p_id,
                        cantidad=float(cant),
                        precio_unitario=prod.precio  # Congelamos el precio actual aquí
                    )
                    db.session.add(vp)
                    mover_stock(prod.id, -float(cant), 'visita', current_user.username, visit_id=visit.id)

        registrar_auditoria(
            current_user.username, 'CREAR_VISITA',
            f"{visit.casa.nombre_formateado()} — {fecha_obj.strftime('%d/%m/%Y')}"
        )
        db.session.commit()

        archivos_subidos = [f for f in request.files.getlist('archivos') if f and f.filename]
        _guardar_media_visita(visit.id, archivos_subidos, current_user.username)

        if visit.observaciones:
            from app.push_utils import enviar_push_novedades
            fotos = [f for f in archivos_subidos if f.content_type and f.content_type.startswith('image/')]
            videos = [f for f in archivos_subidos if f.content_type and f.content_type.startswith('video/')]
            sufijo = ""
            if fotos and videos:
                sufijo = " [foto · video]"
            elif fotos:
                sufijo = " [foto]"
            elif videos:
                sufijo = " [video]"
            enviar_push_novedades(
                f"Nueva novedad: {visit.casa.nombre_formateado()}",
                visit.observaciones + sufijo
            )

        flash("Visita registrada correctamente", "success")
        return redirect(url_for("visits.listar_visits"))
        
    # --- MÉTODO GET: CARGA DE FORMULARIO ---
    # Mostramos todas las casas activas. El POST ya valida que la fecha de visita
    # no sea anterior al inicio del cliente (fecha_creacion).
    casas = Casa.query.filter_by(activo=True).options(
        selectinload(Casa.historial_pausas)
    ).order_by(Casa.numero).all()

    q = Product.query.filter_by(activo=True)
    if current_user.username != 'root':
        q = q.filter(db.func.lower(Product.nombre) != 'deuda')
    _trim = db.func.trim(Product.nombre)
    _priority = case(
        (db.or_(_trim.ilike('pastilla de cloro'), _trim.ilike('pastillas de cloro')), 0),
        (_trim.ilike('clarificador'), 1),
        (_trim.ilike('granulado'), 2),
        (_trim.ilike('granulado lento'), 3),
        (_trim.ilike('granulado rapido'), 4),
        else_=5
    )
    products = q.order_by(_priority, Product.nombre).all()
    promos = Promo.query.filter_by(activo=True).order_by(Promo.nombre).all()

    ultima_visita = Visit.query.filter_by(usuario_id=current_user.id).order_by(Visit.id.desc()).first()

    return render_template("visits/create.html", casas=casas, products=products, promos=promos, ultima_visita=ultima_visita)

@visit_bp.route("/delete/<int:id>", methods=["POST"])
@login_required
def eliminar_visit(id):
    visit = Visit.query.get_or_404(id)
    
    if is_mes_cerrado(visit.fecha.month, visit.fecha.year):
        flash("❌ No podés eliminar una visita de un mes cerrado.", "error")
        return redirect(url_for("visits.listar_visits"))

    detalle_elim = f"{visit.casa.nombre_formateado()} — {visit.fecha.strftime('%d/%m/%Y')}"
    vps_elim = VisitProduct.query.filter_by(visit_id=id).all()
    for vp in vps_elim:
        mover_stock(vp.product_id, float(vp.cantidad), 'ajuste', current_user.username, motivo='visita eliminada')
        db.session.delete(vp)
    MovimientoStock.query.filter_by(visit_id=id).delete()
    VisitMedia.query.filter_by(visit_id=id).delete()
    db.session.delete(visit)
    registrar_auditoria(current_user.username, 'ELIMINAR_VISITA', detalle_elim)
    db.session.commit()
    flash("Visita eliminada", "success")
    return redirect(url_for("visits.listar_visits"))

@visit_bp.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def editar_visit(id):
    visit = Visit.query.get_or_404(id)
    
    if is_mes_cerrado(visit.fecha.month, visit.fecha.year):
        flash("🔒 Este mes está cerrado. No se puede editar la visita.", "warning")
        return redirect(url_for("visits.listar_visits"))

    if request.method == "POST":
        nueva_fecha = datetime.strptime(request.form.get("fecha"), '%Y-%m-%d')
        
        if is_mes_cerrado(nueva_fecha.month, nueva_fecha.year):
            flash("❌ No podés mover la visita a un mes que ya está cerrado.", "error")
            return redirect(url_for("visits.listar_visits"))

        nueva_casa_id = request.form.get("casa_id")
        casa_edit = Casa.query.get(nueva_casa_id) if nueva_casa_id else None
        if casa_edit and casa_edit.fecha_creacion:
            inicio_e = casa_edit.fecha_creacion.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            visita_inicio_mes_e = nueva_fecha.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if visita_inicio_mes_e < inicio_e:
                meses_e = ['enero','febrero','marzo','abril','mayo','junio',
                           'julio','agosto','septiembre','octubre','noviembre','diciembre']
                desde_e = f"{meses_e[casa_edit.fecha_creacion.month-1].capitalize()} {casa_edit.fecha_creacion.year}"
                flash(f"❌ No podés mover la visita a antes del inicio del cliente ({desde_e}).", "error")
                return redirect(url_for("visits.listar_visits"))

        visit.casa_id = nueva_casa_id
        visit.fecha = nueva_fecha
        visit.observaciones = request.form.get("observaciones", "").strip()
        visit.promo_id = request.form.get("promo_id") or None
        
        vps_old = VisitProduct.query.filter_by(visit_id=id).all()
        for vp in vps_old:
            mover_stock(vp.product_id, float(vp.cantidad), 'ajuste', current_user.username, motivo='edición visita')
            db.session.delete(vp)

        product_ids = request.form.getlist("product_id[]")
        cantidades = request.form.getlist("cantidad[]")

        for p_id, cant in zip(product_ids, cantidades):
            if p_id and cant:
                prod = Product.query.get(p_id)
                if prod:
                    vp = VisitProduct(visit_id=id, product_id=p_id, cantidad=float(cant), precio_unitario=prod.precio)
                    db.session.add(vp)
                    mover_stock(prod.id, -float(cant), 'visita', current_user.username, visit_id=id)
        
        registrar_auditoria(
            current_user.username, 'EDITAR_VISITA',
            f"{visit.casa.nombre_formateado()} — {nueva_fecha.strftime('%d/%m/%Y')}"
        )
        db.session.commit()
        _guardar_media_visita(id, request.files.getlist('archivos'), current_user.username)
        flash("Visita actualizada", "success")
        return redirect(url_for("visits.listar_visits"))
        
    casas = Casa.query.filter_by(activo=True).all()
    q_edit = Product.query.filter_by(activo=True)
    if current_user.username != 'root':
        q_edit = q_edit.filter(db.func.lower(Product.nombre) != 'deuda')
    products = q_edit.all()
    promos = Promo.query.filter_by(activo=True).all()
    return render_template("visits/edit.html", visit=visit, casas=casas, products=products, promos=promos)

@visit_bp.route("/detalle/<int:id>")
@login_required
def detalle_visit(id):
    visit = Visit.query.get_or_404(id)
    return render_template("visits/detalle.html", visit=visit)


ALLOWED_FOTO = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'heic'}
ALLOWED_VIDEO = {'mp4', 'mov', 'avi', 'webm', 'mkv'}

def _ext(filename):
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

def _guardar_media_visita(visit_id, files, username):
    import uuid, os
    from flask import current_app
    from app.models.visit_media import VisitMedia
    for f in files:
        if not f or not f.filename:
            continue
        ext = _ext(f.filename)
        if ext in ALLOWED_FOTO:
            tipo = 'foto'
        elif ext in ALLOWED_VIDEO:
            tipo = 'video'
        else:
            continue
        upload_dir = os.path.join(current_app.static_folder, 'uploads', 'visits', str(visit_id))
        os.makedirs(upload_dir, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.{ext}"
        f.save(os.path.join(upload_dir, filename))
        db.session.add(VisitMedia(visit_id=visit_id, filename=filename, tipo=tipo, subido_por=username))
    db.session.commit()

@visit_bp.route("/detalle/<int:id>/media/upload", methods=["POST"])
@login_required
def upload_media(id):
    Visit.query.get_or_404(id)
    _guardar_media_visita(id, request.files.getlist('archivos'), current_user.username)
    return redirect(url_for("visits.detalle_visit", id=id))


@visit_bp.route("/detalle/<int:visit_id>/media/<int:media_id>/delete", methods=["POST"])
@login_required
def delete_media(visit_id, media_id):
    import os
    from flask import current_app
    from app.models.visit_media import VisitMedia

    media = VisitMedia.query.get_or_404(media_id)
    filepath = os.path.join(current_app.static_folder, 'uploads', 'visits', str(visit_id), media.filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    db.session.delete(media)
    db.session.commit()
    return redirect(url_for("visits.detalle_visit", id=visit_id))

@visit_bp.route("/sync-offline", methods=["POST"])
@csrf.exempt
@login_required
def sync_offline():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"ok": False, "error": "no data"}), 400

    fecha_str = data.get("fecha")
    casa_id = data.get("casa_id")
    if not fecha_str or not casa_id:
        return jsonify({"ok": False, "error": "missing fields"}), 400

    try:
        fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({"ok": False, "error": "invalid date"}), 400

    if is_mes_cerrado(fecha_obj.month, fecha_obj.year):
        return jsonify({"ok": False, "error": "mes_cerrado"}), 409

    # Idempotency: si ya existe una visita para esta casa/fecha/usuario, la devolvemos
    existente = Visit.query.filter_by(
        casa_id=casa_id,
        fecha=fecha_obj,
        usuario_id=current_user.id
    ).filter(
        db.or_(Visit.observaciones == None, ~Visit.observaciones.in_(['[EXTRA_MANUAL]', '[DEUDA_ANTERIOR]']))
    ).first()
    if existente:
        return jsonify({"ok": True, "visit_id": existente.id, "duplicate": True})

    visit = Visit(
        casa_id=casa_id,
        fecha=fecha_obj,
        observaciones=data.get("observaciones", "").strip(),
        promo_id=data.get("promo_id") or None,
        usuario_id=current_user.id
    )
    db.session.add(visit)
    db.session.commit()

    for prod in data.get("productos", []):
        p_id = prod.get("product_id")
        cant = prod.get("cantidad")
        if p_id and cant:
            product = Product.query.get(p_id)
            if product:
                vp = VisitProduct(
                    visit_id=visit.id,
                    product_id=p_id,
                    cantidad=float(cant),
                    precio_unitario=product.precio
                )
                db.session.add(vp)
                mover_stock(product.id, -float(cant), 'visita', current_user.username, visit_id=visit.id)

    db.session.commit()
    registrar_auditoria(current_user.username, 'CREAR_VISITA_OFFLINE',
        f"{visit.casa.nombre_formateado()} — {fecha_obj.strftime('%d/%m/%Y')}")

    if visit.observaciones:
        from app.push_utils import enviar_push_novedades
        enviar_push_novedades(
            f"Nueva novedad: {visit.casa.nombre_formateado()}",
            visit.observaciones
        )

    return jsonify({"ok": True, "visit_id": visit.id})


@visit_bp.route("/check_duplicate")
@login_required
def check_duplicate():
    casa_id = request.args.get('casa_id')
    fecha = request.args.get('fecha')
    
    if not casa_id or not fecha:
        return jsonify({"exists": False})

    # Buscamos si existe una visita para esa casa en esa fecha exacta
    # Nota: Filtramos para que NO tome como duplicado un [EXTRA_MANUAL] o [DEUDA_ANTERIOR] 
    # ya que eso sí podría convivir con una visita real.
    existente = Visit.query.filter_by(casa_id=casa_id, fecha=fecha).filter(
        db.or_(Visit.observaciones == None, ~Visit.observaciones.in_(['[EXTRA_MANUAL]', '[DEUDA_ANTERIOR]']))
    ).first()

    if existente:
        # Preparamos el detalle de lo que ya se cargó para el cartel
        detalles_prod = ", ".join([f"{vp.cantidad} {vp.product.nombre}" for vp in existente.productos])
        return jsonify({
            "exists": True,
            "detalles": f"Observaciones: {existente.observaciones or 'Ninguna'}. Productos: {detalles_prod or 'Sin productos'}."
        })
    
    return jsonify({"exists": False})