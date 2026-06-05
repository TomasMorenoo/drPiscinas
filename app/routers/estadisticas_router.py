from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from app.decorators import admin_required
from app.models.casa import Casa
from app.models.abono_historico import AbonoHistorico
from app.models.visit import Visit
from app.models.country import Country
from app.models.visit_product import VisitProduct
from app.models.configuracion import Configuracion
from app import db
from sqlalchemy import extract, func
from sqlalchemy.orm import selectinload, joinedload
from datetime import datetime
import json

estadisticas_bp = Blueprint("estadisticas", __name__, url_prefix="/estadisticas")

# =======================================================
# RUTA: Guarda la preferencia de meses en la base de datos
# =======================================================
@estadisticas_bp.route("/guardar-prefs", methods=["POST"])
@login_required
@admin_required
def guardar_prefs():
    data = request.get_json(silent=True) or {}
    if 'meses_alta' in data:
        Configuracion.set('meses_alta', data['meses_alta'])
        db.session.commit()
    return jsonify({"success": True})


@estadisticas_bp.route("/")
@login_required
@admin_required
def index():
    anio_actual = datetime.now().year
    anio_anterior = anio_actual - 1
    
    # 1. KPI Clientes (Solo los activos)
    kpi_clientes = Casa.query.filter_by(activo=True).count()
    
    # 2. KPI Countries y Barrios
    kpi_countries = Country.query.count()
    
    # Buscamos los countries y contamos cuántos barrios distintos y casas totales tienen
    countries_con_barrios = db.session.query(
        Country.nombre, 
        func.count(func.distinct(Casa.barrio_id)),
        func.count(Casa.id)
    ).join(Casa, Country.id == Casa.country_id).group_by(Country.nombre).all()
    
    lista_countries = [{"nombre": c[0], "barrios": c[1], "casas": c[2]} for c in countries_con_barrios]
    
    # 3. Estadísticas Anuales de Dinero ($ Abonos y $ Productos del año actual)
    meses_abonos = [0.0] * 12
    meses_productos = [0.0] * 12
    meses_proyectados = [False] * 12   # True = sin cierre oficial, valor estimado

    # Solo consideramos "cerrados" los meses con registro en CierreMes
    from app.models.cierre_mes import CierreMes
    meses_cerrados = set(
        row[0] for row in db.session.query(CierreMes.mes).filter(CierreMes.anio == anio_actual).all()
    )

    abonos_db = db.session.query(AbonoHistorico.mes, func.sum(AbonoHistorico.monto)).filter(
        AbonoHistorico.anio == anio_actual,
        AbonoHistorico.mes.in_(meses_cerrados)
    ).group_by(AbonoHistorico.mes).all()

    meses_con_datos = set()
    for mes, total in abonos_db:
        meses_abonos[mes - 1] = float(total)
        meses_con_datos.add(mes)

    # Para los meses sin cierre oficial, estimar desde precio_base de clientes activos
    casas_activas = Casa.query.filter_by(activo=True).all()
    for i in range(12):
        mes = i + 1
        if mes not in meses_con_datos:
            estimado = sum(
                float(c.precio_base or 0)
                for c in casas_activas
                if not c.fecha_creacion or
                   (c.fecha_creacion.year, c.fecha_creacion.month) <= (anio_actual, mes)
            )
            meses_abonos[i] = estimado
            meses_proyectados[i] = True

    total_anual_abonos = sum(meses_abonos)

    # 4. Eager Loading
    visitas_rango = Visit.query.options(
        selectinload(Visit.promo),
        selectinload(Visit.productos).joinedload(VisitProduct.product)
    ).filter(extract('year', Visit.fecha).in_([anio_actual, anio_anterior])).all()
    
    uso_productos_mes = {}
    
    for v in visitas_rango:
        v_anio = v.fecha.year
        v_mes = v.fecha.month
        llave_mes = f"{v_anio}-{v_mes:02d}" 
        
        if llave_mes not in uso_productos_mes:
            uso_productos_mes[llave_mes] = {}
            
        total_v_dinero = 0.0
        
        if v_anio == anio_actual and v.promo and v.promo.precio:
            total_v_dinero += float(v.promo.precio)
            
        for vp in v.productos:
            nombre_prod = vp.product.nombre
            unidad_prod = vp.product.unidad if vp.product.unidad else "unidades"
            cantidad = float(vp.cantidad)
            
            if v_anio == anio_actual:
                precio = vp.precio_unitario if vp.precio_unitario else vp.product.precio
                total_v_dinero += cantidad * float(precio)
                
            if nombre_prod not in uso_productos_mes[llave_mes]:
                uso_productos_mes[llave_mes][nombre_prod] = {"cantidad": 0.0, "unidad": unidad_prod}
                
            uso_productos_mes[llave_mes][nombre_prod]["cantidad"] += cantidad
            
        if v_anio == anio_actual:
            meses_productos[v_mes - 1] += total_v_dinero
            
    total_anual_productos = sum(meses_productos)

    # --- LEEMOS LA PREFERENCIA GUARDADA EN LA BASE DE DATOS ---
    meses_alta_guardados = Configuracion.get('meses_alta', None)

    return render_template(
        "estadisticas/index.html",
        anio_actual=anio_actual,
        anio_anterior=anio_anterior,
        kpi_clientes=kpi_clientes,
        kpi_countries=kpi_countries,
        lista_countries=json.dumps(lista_countries),
        meses_abonos=json.dumps(meses_abonos),
        meses_productos=json.dumps(meses_productos),
        meses_proyectados=json.dumps(meses_proyectados),
        total_anual_abonos=total_anual_abonos,
        total_anual_productos=total_anual_productos,
        uso_productos_mes=json.dumps(uso_productos_mes),
        meses_alta_session=json.dumps(meses_alta_guardados) if meses_alta_guardados is not None else "null"
    )