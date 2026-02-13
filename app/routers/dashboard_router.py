from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app import db
from app.models.casa import Casa
from app.models.abono_historico import AbonoHistorico
from datetime import datetime

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

@dashboard_bp.route("/")
@login_required
def index():
    try:
        mes = int(request.args.get("mes", datetime.now().month))
        anio = int(request.args.get("anio", datetime.now().year))
    except ValueError:
        mes = datetime.now().month
        anio = datetime.now().year
    
    casas = Casa.query.filter_by(activo=True).all()
    reporte = []

    total_clientes = 0
    total_abono = 0
    total_extras = 0
    total_general = 0

    for casa in casas:
        # Obtenemos los extras del mes
        datos = casa.obtener_gastos_mensuales(mes, anio)
        extras = datos.get("extras", 0)

        # Buscamos si hay un abono congelado para esta casa en este mes/año
        historial = AbonoHistorico.query.filter_by(casa_id=casa.id, mes=mes, anio=anio).first()
        
        # Si existe el historial, usamos ese monto. Si no, mostramos el precio actual.
        abono_mes = historial.monto if historial else (casa.precio_base or 0)
        
        total_cliente = abono_mes + extras

        reporte.append({
            "casa": casa,
            "abono": abono_mes,
            "extras": extras,
            "total": total_cliente
        })

        total_clientes += 1
        total_abono += abono_mes
        total_extras += extras
        total_general += total_cliente

    return render_template(
        "dashboard/index.html",
        reporte=reporte,
        mes=mes,
        anio=anio,
        kpi_clientes=total_clientes,
        kpi_abono=total_abono,
        kpi_extras=total_extras,
        kpi_total=total_general,
        now=datetime.now()
    )

@dashboard_bp.route("/sync-abonos", methods=["POST"])
@login_required
def sync_abonos():
    mes = request.form.get("mes", type=int)
    anio = request.form.get("anio", type=int)

    if not mes or not anio:
        flash("Período no válido", "error")
        return redirect(url_for('dashboard.index'))

    casas_activas = Casa.query.filter_by(activo=True).all()
    
    for casa in casas_activas:
        historial = AbonoHistorico.query.filter_by(casa_id=casa.id, mes=mes, anio=anio).first()
        
        if historial:
            historial.monto = casa.precio_base or 0
        else:
            nuevo_historial = AbonoHistorico(
                casa_id=casa.id, 
                mes=mes, 
                anio=anio, 
                monto=casa.precio_base or 0
            )
            db.session.add(nuevo_historial)

    db.session.commit()
    flash(f"Abonos congelados exitosamente para el mes {mes}/{anio}", "success")
    return redirect(url_for('dashboard.index', mes=mes, anio=anio))