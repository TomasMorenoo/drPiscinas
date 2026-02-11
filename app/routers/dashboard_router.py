from flask import Blueprint, render_template, request
from flask_login import login_required
from app.models.casa import Casa
from datetime import datetime

# Definición del Blueprint para el dashboard
dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

@dashboard_bp.route("/")
@login_required # Candado de seguridad para usuarios autenticados
def index():
    # 1. Obtener filtros de mes y año desde la URL (por defecto el mes/año actual)
    try:
        mes = int(request.args.get("mes", datetime.now().month))
        anio = int(request.args.get("anio", datetime.now().year))
    except ValueError:
        mes = datetime.now().month
        anio = datetime.now().year
    
    # 2. Buscar datos de todas las casas que están activas
    casas = Casa.query.filter_by(activo=True).all()
    reporte = []

    # Variables acumuladoras para los KPIs (indicadores clave de desempeño)
    total_clientes = 0
    total_abono = 0
    total_extras = 0
    total_general = 0

    # 3. Procesar cada casa para calcular sus gastos del mes seleccionado
    for casa in casas:
        # Se asume que el modelo Casa tiene el método obtener_gastos_mensuales(mes, anio)
        datos = casa.obtener_gastos_mensuales(mes, anio)
        
        # Guardamos la información individual para la tabla del reporte
        reporte.append({
            "casa": casa,
            "abono": datos["abono"],
            "extras": datos["extras"],
            "total": datos["total"]
        })

        # 4. Actualizamos los Totales Generales (KPIs) del período
        total_clientes += 1
        total_abono += datos["abono"]
        total_extras += datos["extras"]
        total_general += datos["total"]

    # 5. Enviamos la información al template del dashboard
    return render_template(
        "dashboard/index.html",
        reporte=reporte,
        mes=mes,
        anio=anio,
        # Pasamos los KPIs calculados para las tarjetas superiores
        kpi_clientes=total_clientes,
        kpi_abono=total_abono,
        kpi_extras=total_extras,
        kpi_total=total_general,
        # 'now' se usa para mostrar la fecha de última actualización en el dash
        now=datetime.now()
    )