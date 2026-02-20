from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from app import db
from app.models import Casa, Country, Barrio
from app.models.abono_historico import AbonoHistorico
from datetime import datetime
import re
import urllib.parse # Necesario para codificar el texto de WhatsApp

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

def natural_sort_key(casa):
    k_country = casa.country.nombre.lower() if casa.country else "zzz"
    k_barrio = casa.barrio.nombre.lower() if casa.barrio else ""
    k_numero = [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(casa.numero))]
    return (k_country, k_barrio, k_numero)

# Funcioncita para formatear la plata ej: 35000 -> 35.000
def format_money(value):
    return f"{value:,.0f}".replace(",", ".")

@dashboard_bp.route("/")
@login_required
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
        
        total_cliente = abono_mes + extras
        
        # Leemos los estados de la base de datos
        esta_pagado = getattr(historial, 'pagado', False) if historial else False 
        mensaje_enviado = getattr(historial, 'mensaje_enviado', False) if historial else False

        # --- LÓGICA DEL MENSAJE DE WHATSAPP ---
        url_wa = ""
        if casa.telefono:
            # 1. Definimos a quién le hablamos
            nombre_wa = casa.nombre_cliente if casa.nombre_cliente else casa.nombre_formateado()
            
            # 2. Armamos el texto exacto que pediste
            texto_wa = f"Hola! {nombre_wa} Te paso el resumen del mes: Abono ${format_money(abono_mes)} + Productos ${format_money(extras)}. Total ${format_money(total_cliente)}. Gracias"
            texto_codificado = urllib.parse.quote(texto_wa)
            
            # 3. Limpiamos el teléfono (para que WhatsApp lo entienda)
            tel = re.sub(r'\D', '', casa.telefono)
            if len(tel) == 10: # Si puso 1122334455, le clavamos el 549 de Argentina
                tel = "549" + tel
                
            url_wa = f"https://wa.me/{tel}?text={texto_codificado}"

        reporte.append({
            "id_historial": historial.id if historial else None,
            "casa": casa,
            "abono": abono_mes,
            "extras": extras,
            "total": total_cliente,
            "pagado": esta_pagado,
            "mensaje_enviado": mensaje_enviado,
            "url_wa": url_wa
        })

        total_clientes += 1
        total_abono += abono_mes
        total_extras += extras
        if esta_pagado:
            total_recaudado += total_cliente

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

# --- NUEVA RUTA PARA MARCAR MENSAJE COMO ENVIADO ---
@dashboard_bp.route("/marcar-mensaje/<int:id>", methods=["POST"])
@login_required
def marcar_mensaje(id):
    registro = AbonoHistorico.query.get_or_404(id)
    registro.mensaje_enviado = True
    db.session.commit()
    return jsonify({"success": True})

@dashboard_bp.route("/toggle-pago/<int:id>", methods=["POST"])
@login_required
def toggle_pago(id):
    registro = AbonoHistorico.query.get_or_404(id)
    
    # Obtenemos los estados actuales
    pagado = getattr(registro, 'pagado', False)
    enviado = getattr(registro, 'mensaje_enviado', False)
    
    # CICLO DE 3 ESTADOS: Pendiente -> Enviado -> Pagado -> Vuelve a Pendiente
    if not pagado and not enviado:
        # 1. Estaba Pendiente -> Pasa a Enviado
        registro.mensaje_enviado = True
        registro.pagado = False
    elif not pagado and enviado:
        # 2. Estaba Enviado -> Pasa a Pagado
        registro.pagado = True
        registro.mensaje_enviado = True
    else:
        # 3. Estaba Pagado -> Vuelve a Pendiente (resetea todo)
        registro.pagado = False
        registro.mensaje_enviado = False
        
    db.session.commit()
    return jsonify({"success": True})

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
            db.session.add(AbonoHistorico(
                casa_id=casa.id, mes=mes, anio=anio, monto=float(casa.precio_base or 0)
            ))
    db.session.commit()
    flash(f"✅ El mes {mes}/{anio} se ha CERRADO correctamente.", "success")
    return redirect(url_for('dashboard.index', mes=mes, anio=anio))

@dashboard_bp.route("/unsync-abonos", methods=["POST"])
@login_required
def unsync_abonos():
    mes = request.form.get("mes", type=int)
    anio = request.form.get("anio", type=int)
    if not mes or not anio:
        flash("Período no válido", "error")
        return redirect(url_for('dashboard.index'))
    AbonoHistorico.query.filter_by(mes=mes, anio=anio).delete()
    db.session.commit()
    flash(f"🔓 El mes {mes}/{anio} ha sido REABIERTO.", "info")
    return redirect(url_for('dashboard.index', mes=mes, anio=anio))