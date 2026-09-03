from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required
from app.decorators import admin_required
from app import db
from app.models.casa import Casa
from app.models.grupo import GrupoCliente
from app.models.visit import Visit
from app.models.visit_product import VisitProduct
from sqlalchemy.orm import selectinload
from app.utils import nombre_mes

grupo_bp = Blueprint("grupos", __name__, url_prefix="/grupos")


def estado_cuenta_grupo(grupo, casas):
    from app.routers.dashboard_router import _casa_pausada_en_mes, _saldo_grupo_para_mes

    historiales = {
        c.id: {(h.anio, h.mes): h for h in c.historial_abonos
               if not c.fecha_creacion or (h.anio, h.mes) >= (c.fecha_creacion.year, c.fecha_creacion.month)}
        for c in casas
    }
    periodos = sorted({p for registros in historiales.values() for p in registros}, reverse=True)
    filas = []
    for anio, mes in periodos:
        abono = productos = recibido = saldo_anterior = 0.0
        pausas = []
        detalle_casas = []
        for c in casas:
            if c.fecha_creacion and (anio, mes) < (c.fecha_creacion.year, c.fecha_creacion.month):
                continue
            anterior_casa = c.obtener_saldo_anterior(mes, anio)
            saldo_anterior += anterior_casa
            h = historiales[c.id].get((anio, mes))
            pausada = _casa_pausada_en_mes(c, mes, anio)
            abono_casa = productos_casa = recibido_casa = 0.0
            if h is not None:
                pausas.append(pausada)
                gastos = c.obtener_gastos_mensuales(mes, anio, hist=h)
                abono_casa = 0.0 if pausada else float(h.monto or 0)
                productos_casa = float(gastos['extras'])
                recibido_casa = float(h.monto_pagado or 0)
            elif abs(anterior_casa) <= 0.01:
                continue
            abono += abono_casa
            productos += productos_casa
            recibido += recibido_casa
            saldo_casa = round(anterior_casa + abono_casa + productos_casa - recibido_casa, 2)
            if saldo_casa > 0.01:
                estado_casa, color_casa = 'Pendiente', 'danger'
            elif saldo_casa < -0.01:
                estado_casa, color_casa = 'A favor', 'info'
            elif pausada:
                estado_casa, color_casa = 'Pausada', 'secondary'
            else:
                estado_casa, color_casa = 'Al día', 'success'
            detalle_casas.append(dict(casa=c, abono=abono_casa, producto=productos_casa,
                                     recibido=recibido_casa, saldo_anterior=anterior_casa,
                                     saldo=saldo_casa, estado=estado_casa, color=color_casa,
                                     marcada_pagada=bool(h and h.pagado), sin_historial=h is None))
        credito = _saldo_grupo_para_mes(grupo, mes, anio)
        saldo = round(saldo_anterior + abono + productos - recibido - credito, 2)
        if saldo > 0.01:
            estado, color = 'Pendiente', 'danger'
        elif saldo < -0.01:
            estado, color = 'A favor', 'info'
        elif pausas and all(pausas):
            estado, color = 'Pausado', 'secondary'
        else:
            estado, color = 'Al día', 'success'
        filas.append(dict(anio=anio, mes=mes, periodo=f'{nombre_mes(mes)} {anio}',
                          abono=abono, producto=productos, recibido=recibido,
                          saldo_anterior=round(saldo_anterior - credito, 2),
                          saldo=saldo, credito=credito, estado=estado, color=color,
                          casas=detalle_casas))
    return filas


@grupo_bp.route('/perfil/<int:id>')
@login_required
@admin_required
def perfil(id):
    grupo = GrupoCliente.query.get_or_404(id)
    casas = Casa.query.filter_by(grupo_id=id).options(
        selectinload(Casa.country), selectinload(Casa.barrio),
        selectinload(Casa.historial_abonos), selectinload(Casa.historial_pausas),
        selectinload(Casa.visitas).selectinload(Visit.productos).joinedload(VisitProduct.product),
        selectinload(Casa.visitas).joinedload(Visit.promo)
    ).all()
    casas.sort(key=lambda c: c.nombre_formateado().lower())
    filas = estado_cuenta_grupo(grupo, casas)
    anios = sorted({f['anio'] for f in filas}, reverse=True)
    anio = request.args.get('anio', type=int)
    if anio not in anios:
        anio = anios[0] if anios else None
    return render_template('grupos/perfil.html', grupo=grupo, casas=casas,
                           filas=[f for f in filas if f['anio'] == anio],
                           anios=anios, anio=anio)

@grupo_bp.route("/")
@login_required
@admin_required
def listar_grupos():
    grupos = GrupoCliente.query.all()
    return render_template("grupos/list.html", grupos=grupos)

@grupo_bp.route("/create", methods=["GET", "POST"])
@login_required
@admin_required
def crear_grupo():
    if request.method == "POST":
        nombre_grupo = request.form.get("nombre")
        nombre_id = request.form.get("nombre_identificador", "").strip() or None
        casas_seleccionadas = request.form.getlist("casas_ids[]")

        if not nombre_grupo or not casas_seleccionadas:
            flash("Debes ingresar un nombre y seleccionar al menos una casa.", "error")
            return redirect(url_for("grupos.crear_grupo"))

        nuevo_grupo = GrupoCliente(nombre=nombre_grupo, nombre_identificador=nombre_id)
        db.session.add(nuevo_grupo)
        db.session.commit()
        
        for casa_id in casas_seleccionadas:
            casa = Casa.query.get(casa_id)
            if casa:
                casa.grupo_id = nuevo_grupo.id
                
        db.session.commit()
        flash(f"Grupo '{nombre_grupo}' creado exitosamente.", "success")
        return redirect(url_for("grupos.listar_grupos"))
        
    # ESTO ES LO NUEVO: Le pasamos las casas sueltas al HTML para el select manual
    casas_libres = Casa.query.filter_by(grupo_id=None, activo=True).order_by(Casa.country_id).all()
    return render_template("grupos/create.html", casas_libres=casas_libres)

@grupo_bp.route("/editar/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def editar_grupo(id):
    grupo = GrupoCliente.query.get_or_404(id)
    if request.method == "POST":
        nuevo_nombre = request.form.get("nombre")
        nombre_id = request.form.get("nombre_identificador", "").strip() or None
        if nuevo_nombre:
            grupo.nombre = nuevo_nombre
            grupo.nombre_identificador = nombre_id
            db.session.commit()
            flash("Nombres del grupo actualizados.", "success")
        return redirect(url_for("grupos.editar_grupo", id=grupo.id))
        
    casas_libres = Casa.query.filter_by(grupo_id=None, activo=True).order_by(Casa.country_id).all()
    return render_template("grupos/edit.html", grupo=grupo, casas_libres=casas_libres)

@grupo_bp.route("/agregar_casa/<int:grupo_id>", methods=["POST"])
@login_required
@admin_required
def agregar_casa(grupo_id):
    casa_id = request.form.get("casa_id")
    casa = Casa.query.get(casa_id)
    if casa:
        casa.grupo_id = grupo_id
        db.session.commit()
        flash("Casa incorporada al grupo.", "success")
    return redirect(url_for("grupos.editar_grupo", id=grupo_id))

@grupo_bp.route("/quitar_casa/<int:casa_id>", methods=["POST"])
@login_required
@admin_required
def quitar_casa(casa_id):
    casa = Casa.query.get_or_404(casa_id)
    grupo_id = casa.grupo_id
    casa.grupo_id = None
    db.session.commit()
    flash("Casa removida del grupo.", "info")
    return redirect(url_for("grupos.editar_grupo", id=grupo_id))

@grupo_bp.route("/eliminar/<int:id>", methods=["POST"])
@login_required
@admin_required
def eliminar_grupo(id):
    grupo = GrupoCliente.query.get_or_404(id)
    # Liberamos a las casas primero
    for c in grupo.casas:
        c.grupo_id = None
    db.session.delete(grupo)
    db.session.commit()
    flash("Grupo desarmado. Las casas pasaron a ser individuales.", "success")
    return redirect(url_for("grupos.listar_grupos"))

@grupo_bp.route("/api/buscar_por_telefono")
@login_required
def buscar_por_telefono():
    telefono = request.args.get("telefono", "").strip()
    if not telefono:
        return jsonify([])
    casas = Casa.query.filter(Casa.telefono.ilike(f"%{telefono}%"), Casa.grupo_id == None).all()
    resultados = [{"id": c.id, "nombre": c.nombre_formateado(), "cliente": c.nombre_cliente or "Sin nombre", "abono": float(c.precio_base)} for c in casas]
    return jsonify(resultados)
