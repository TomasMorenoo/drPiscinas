from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from app.decorators import admin_required
from app import db
from app.models import Casa, Country, Barrio
from app.models.abono_historico import AbonoHistorico
from datetime import datetime
import re
import urllib.parse

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

def natural_sort_key(casa):
    k_country = casa.country.nombre.lower() if casa.country else "zzz"
    k_barrio = casa.barrio.nombre.lower() if casa.barrio else ""
    k_numero = [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(casa.numero))]
    return (k_country, k_barrio, k_numero)

def format_money(value):
    return f"{value:,.0f}".replace(",", ".")

@dashboard_bp.route("/")
@login_required
@admin_required
def index():
    try:
        mes = int(request.args.get("mes", datetime.now().month))
        anio = int(request.args.get("anio", datetime.now().year))
    except ValueError:
        mes = datetime.now().month
        anio = datetime.now().year
    
    registro_congelado = AbonoHistorico.query.filter_by(mes=mes, anio=anio).first()
    mes_congelado = True if registro_congelado else False

    casas = Casa.query.filter_by(activo=True).all()
    casas.sort(key=natural_sort_key)

    reporte = []
    total_clientes = 0
    total_abono = 0.0
    total_extras = 0.0
    total_recaudado = 0.0 

    for casa in casas:
        datos = casa.obtener_gastos_mensuales(mes, anio)
        extras = float(datos.get("extras", 0))

        historial = AbonoHistorico.query.filter_by(casa_id=casa.id, mes=mes, anio=anio).first()
        abono_mes = float(historial.monto) if historial else float(casa.precio_base or 0)
        
        # 1. Total de ESTE mes (Abono + Extras)
        total_mes = abono_mes + extras
        
        # 2. Arrastre de meses anteriores
        saldo_anterior = casa.obtener_saldo_anterior(mes, anio)
        
        # 3. Lo que pagó este mes
        monto_pagado = float(getattr(historial, 'monto_pagado', 0) or 0)
        
        # 4. Saldo resultante final (Lo que debe HOY)
        saldo_restante = (total_mes + saldo_anterior) - monto_pagado

        esta_pagado = getattr(historial, 'pagado', False) if historial else False
        mensaje_enviado = getattr(historial, 'mensaje_enviado', False) if historial else False

        url_wa = ""
        if casa.telefono:
            nombre_wa = casa.nombre_cliente if casa.nombre_cliente else casa.nombre_formateado()
            
            # WSP Inteligente
            texto_wa = f"Hola! {nombre_wa} Te paso el resumen: Abono ${format_money(abono_mes)} + Productos ${format_money(extras)}."
            if saldo_anterior > 0:
                texto_wa += f" Deuda anterior: ${format_money(saldo_anterior)}."
            elif saldo_anterior < 0:
                texto_wa += f" Saldo a favor: ${format_money(abs(saldo_anterior))}."
            
            texto_wa += f" Total a pagar: ${format_money(total_mes + saldo_anterior)}. Gracias"
            
            texto_codificado = urllib.parse.quote(texto_wa)
            tel = re.sub(r'\D', '', casa.telefono)
            if len(tel) == 10: 
                tel = "549" + tel
            url_wa = f"https://wa.me/{tel}?text={texto_codificado}"

        reporte.append({
            "id_historial": historial.id if historial else None,
            "casa": casa,
            "abono": abono_mes,
            "extras": extras,
            "total_mes": total_mes, # Columna Total (Negro)
            "saldo_anterior": saldo_anterior,
            "saldo_restante": saldo_restante, # Columna Saldo
            "monto_pagado": monto_pagado,
            "pagado": esta_pagado,
            "mensaje_enviado": mensaje_enviado,
            "url_wa": url_wa
        })

        total_clientes += 1
        total_abono += abono_mes
        total_extras += extras
        
        # KPI Recaudado
        if esta_pagado and monto_pagado == 0:
            total_recaudado += total_mes
        else:
            total_recaudado += monto_pagado

    total_general = total_abono + total_extras

    return render_template(
        "dashboard/index.html",
        reporte=reporte,
        mes=mes,
        anio=anio,
        mes_congelado=mes_congelado,
        kpi_clientes=total_clientes,
        kpi_abono=total_abono,
        kpi_extras=total_extras,
        kpi_recaudado=total_recaudado,
        kpi_pendiente=total_general - total_recaudado,
        kpi_total=total_general,
        now=datetime.now()
    )

@dashboard_bp.route("/marcar-mensaje/<int:id>", methods=["POST"])
@login_required
@admin_required
def marcar_mensaje(id):
    registro = AbonoHistorico.query.get_or_404(id)
    registro.mensaje_enviado = True
    db.session.commit()
    return jsonify({"success": True})

@dashboard_bp.route("/toggle-pago/<int:id>", methods=["POST"])
@login_required
@admin_required
def toggle_pago(id):
    registro = AbonoHistorico.query.get_or_404(id)
    pagado = getattr(registro, 'pagado', False)
    enviado = getattr(registro, 'mensaje_enviado', False)
    
    casa = registro.casa
    
    if not pagado and not enviado:
        registro.mensaje_enviado = True
        registro.pagado = False
    elif not pagado and enviado:
        registro.pagado = True
        registro.mensaje_enviado = True
        # Si le da al tilde, asume que canceló el mes y toda la deuda anterior
        total_mes = float(registro.monto) + float(casa.obtener_gastos_mensuales(registro.mes, registro.anio)['extras'])
        saldo_ant = casa.obtener_saldo_anterior(registro.mes, registro.anio)
        registro.monto_pagado = total_mes + saldo_ant
    else:
        registro.pagado = False
        registro.mensaje_enviado = False
        registro.monto_pagado = 0.0 # Resetea
        
    db.session.commit()
    return jsonify({"success": True})

@dashboard_bp.route("/sync-abonos", methods=["POST"])
@login_required
@admin_required
def sync_abonos():
    mes = request.form.get("mes", type=int)
    anio = request.form.get("anio", type=int)
    if not mes or not anio: return redirect(url_for('dashboard.index'))
    for casa in Casa.query.filter_by(activo=True).all():
        if not AbonoHistorico.query.filter_by(casa_id=casa.id, mes=mes, anio=anio).first():
            db.session.add(AbonoHistorico(casa_id=casa.id, mes=mes, anio=anio, monto=float(casa.precio_base or 0)))
    db.session.commit()
    return redirect(url_for('dashboard.index', mes=mes, anio=anio))

@dashboard_bp.route("/unsync-abonos", methods=["POST"])
@login_required
@admin_required
def unsync_abonos():
    mes = request.form.get("mes", type=int)
    anio = request.form.get("anio", type=int)
    if mes and anio:
        AbonoHistorico.query.filter_by(mes=mes, anio=anio).delete()
        db.session.commit()
    return redirect(url_for('dashboard.index', mes=mes, anio=anio))

@dashboard_bp.route("/registrar-pago-especial/<int:id_historial>", methods=["POST"])
@login_required
@admin_required
def registrar_pago_especial(id_historial):
    registro = AbonoHistorico.query.get_or_404(id_historial)
    monto_ingresado = float(request.json.get("monto", 0))
    
    registro.monto_pagado += monto_ingresado
    
    casa = registro.casa
    total_mes = float(registro.monto) + float(casa.obtener_gastos_mensuales(registro.mes, registro.anio)['extras'])
    saldo_ant = casa.obtener_saldo_anterior(registro.mes, registro.anio)
    
    # Si con lo que puso, la deuda llegó a 0 o quedó a favor
    if registro.monto_pagado >= ((total_mes + saldo_ant) - 0.1): 
        registro.pagado = True
        registro.mensaje_enviado = True
    else:
        registro.pagado = False
        
    db.session.commit()
    return jsonify({"success": True})