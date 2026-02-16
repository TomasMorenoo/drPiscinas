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
    
    # Verificamos si este mes ya tiene algún registro congelado para mostrar el botón correcto
    registro_congelado = AbonoHistorico.query.filter_by(mes=mes, anio=anio).first()
    mes_congelado = True if registro_congelado else False

    casas = Casa.query.filter_by(activo=True).all()
    reporte = []

    total_clientes = 0
    total_abono = 0.0
    total_extras = 0.0
    total_general = 0.0

    for casa in casas:
        datos = casa.obtener_gastos_mensuales(mes, anio)
        extras = float(datos.get("extras", 0))

        historial = AbonoHistorico.query.filter_by(casa_id=casa.id, mes=mes, anio=anio).first()
        abono_mes = float(historial.monto) if historial else float(casa.precio_base or 0)
        
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
        mes_congelado=mes_congelado, # <-- Pasamos la variable al HTML
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
            historial.monto = float(casa.precio_base or 0)
        else:
            nuevo_historial = AbonoHistorico(
                casa_id=casa.id, 
                mes=mes, 
                anio=anio, 
                monto=float(casa.precio_base or 0)
            )
            db.session.add(nuevo_historial)

    db.session.commit()
    flash(f"Abonos congelados exitosamente para el mes {mes}/{anio}", "success")
    return redirect(url_for('dashboard.index', mes=mes, anio=anio))

@dashboard_bp.route("/unsync-abonos", methods=["POST"])
@login_required
def unsync_abonos():
    mes = request.form.get("mes", type=int)
    anio = request.form.get("anio", type=int)

    if not mes or not anio:
        flash("Período no válido", "error")
        return redirect(url_for('dashboard.index'))

    # Borramos todos los registros de abonos guardados para ese mes
    AbonoHistorico.query.filter_by(mes=mes, anio=anio).delete()
    db.session.commit()

    flash(f"Abonos descongelados para el mes {mes}/{anio}. Se volvieron a tomar los valores actuales.", "info")
    return redirect(url_for('dashboard.index', mes=mes, anio=anio))