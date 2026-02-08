from flask import Blueprint, render_template, request
from app.models import Casa
from datetime import datetime

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

@dashboard_bp.route("/")
def index():
    # 1. Obtener filtros
    mes = int(request.args.get("mes", datetime.now().month))
    anio = int(request.args.get("anio", datetime.now().year))
    
    # 2. Buscar datos
    casas = Casa.query.filter_by(activo=True).all()
    reporte = []

    # Variables acumuladoras (Iniciamos en 0)
    total_clientes = 0
    total_abono = 0
    total_extras = 0
    total_general = 0

    # 3. Procesar cada casa
    for casa in casas:
        # Usamos el método que creamos en el modelo Casa
        datos = casa.obtener_gastos_mensuales(mes, anio)
        
        # Agregamos al reporte individual
        reporte.append({
            "casa": casa,
            "abono": datos["abono"],
            "extras": datos["extras"],
            "total": datos["total"]
        })

        # 4. Sumamos a los Totales Generales (KPIs)
        total_clientes += 1
        total_abono += datos["abono"]
        total_extras += datos["extras"]
        total_general += datos["total"]

    # 5. Enviamos todo a la vista (incluyendo los totales calculados)
    return render_template(
        "dashboard/index.html",
        reporte=reporte,
        mes=mes,
        anio=anio,
        # Pasamos los KPIs calculados
        kpi_clientes=total_clientes,
        kpi_abono=total_abono,
        kpi_extras=total_extras,
        kpi_total=total_general
    )