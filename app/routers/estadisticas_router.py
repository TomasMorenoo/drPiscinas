from flask import Blueprint, render_template
from flask_login import login_required
from app.decorators import admin_required
from app.models.casa import Casa
from app.models.abono_historico import AbonoHistorico
from app.models.visit import Visit
from app.models.country import Country
from app.models.visit_product import VisitProduct  # <--- IMPORTAMOS ESTO
from app import db
from sqlalchemy import extract, func
from sqlalchemy.orm import selectinload, joinedload
from datetime import datetime
import json

estadisticas_bp = Blueprint("estadisticas", __name__, url_prefix="/estadisticas")

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
        func.count(Casa.id) # <--- AGREGAMOS EL CONTEO DE CASAS
    ).join(Casa, Country.id == Casa.country_id).group_by(Country.nombre).all()
    
    # Sumamos "casas: c[2]" al diccionario que le mandamos al Javascript
    lista_countries = [{"nombre": c[0], "barrios": c[1], "casas": c[2]} for c in countries_con_barrios]
    
    # 3. Estadísticas Anuales de Dinero ($ Abonos y $ Productos del año actual)
    meses_abonos = [0.0] * 12
    meses_productos = [0.0] * 12
    
    abonos_db = db.session.query(AbonoHistorico.mes, func.sum(AbonoHistorico.monto)).filter(AbonoHistorico.anio == anio_actual).group_by(AbonoHistorico.mes).all()
    for mes, total in abonos_db:
        meses_abonos[mes - 1] = float(total)
        
    total_anual_abonos = sum(meses_abonos)

    # 4. Eager Loading CORREGIDO: Usamos VisitProduct.product sin comillas
    visitas_rango = Visit.query.options(
        selectinload(Visit.promo),
        selectinload(Visit.productos).joinedload(VisitProduct.product) # <--- CORRECCIÓN ACÁ
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
            
            # Sumar al gráfico de ingresos solo si es del año actual
            if v_anio == anio_actual:
                precio = vp.precio_unitario if vp.precio_unitario else vp.product.precio
                total_v_dinero += cantidad * float(precio)
                
            # Cargar la tabla de uso físico de productos
            if nombre_prod not in uso_productos_mes[llave_mes]:
                uso_productos_mes[llave_mes][nombre_prod] = {"cantidad": 0.0, "unidad": unidad_prod}
                
            uso_productos_mes[llave_mes][nombre_prod]["cantidad"] += cantidad
            
        # Sumar ingresos de esta visita al mes correspondiente
        if v_anio == anio_actual:
            meses_productos[v_mes - 1] += total_v_dinero
            
    total_anual_productos = sum(meses_productos)

    return render_template(
        "estadisticas/index.html",
        anio_actual=anio_actual,
        anio_anterior=anio_anterior,
        kpi_clientes=kpi_clientes,
        kpi_countries=kpi_countries,
        lista_countries=json.dumps(lista_countries),
        meses_abonos=json.dumps(meses_abonos),
        meses_productos=json.dumps(meses_productos),
        total_anual_abonos=total_anual_abonos,
        total_anual_productos=total_anual_productos,
        uso_productos_mes=json.dumps(uso_productos_mes)
    )