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

    if mes_congelado:
        historiales = AbonoHistorico.query.filter_by(mes=mes, anio=anio).all()
        casas = [h.casa for h in historiales]
    else:
        casas = Casa.query.filter_by(activo=True).all()

    casas.sort(key=natural_sort_key)

    reporte_sueltas = []
    reporte_grupos = {} 
    
    total_clientes = 0
    total_abono = 0.0
    total_extras = 0.0
    total_recaudado = 0.0 

    for casa in casas:
        datos = casa.obtener_gastos_mensuales(mes, anio)
        extras = float(datos.get("extras", 0))

        historial = AbonoHistorico.query.filter_by(casa_id=casa.id, mes=mes, anio=anio).first()
        abono_mes = float(historial.monto) if historial else float(casa.precio_base or 0)
        
        total_mes = abono_mes + extras
        saldo_anterior = casa.obtener_saldo_anterior(mes, anio)
        monto_pagado = float(getattr(historial, 'monto_pagado', 0) or 0)
        saldo_restante = (total_mes + saldo_anterior) - monto_pagado

        esta_pagado = getattr(historial, 'pagado', False) if historial else False
        mensaje_enviado = getattr(historial, 'mensaje_enviado', False) if historial else False

        item_casa = {
            "id_historial": historial.id if historial else None,
            "casa": casa,
            "abono": abono_mes,
            "extras": extras,
            "total_mes": total_mes, 
            "saldo_anterior": saldo_anterior,
            "saldo_restante": saldo_restante, 
            "monto_pagado": monto_pagado,
            "pagado": esta_pagado,
            "mensaje_enviado": mensaje_enviado,
            "url_wa": "" 
        }

        # LÓGICA DE AGRUPAMIENTO
        if casa.grupo_id:
            if casa.grupo_id not in reporte_grupos:
                reporte_grupos[casa.grupo_id] = {
                    "grupo_id": casa.grupo_id,
                    "nombre": casa.grupo.nombre,
                    "casas": [],
                    "total_mes": 0.0,
                    "saldo_anterior": 0.0,
                    "saldo_restante": 0.0,
                    "monto_pagado": 0.0,
                    "telefono": casa.telefono
                }
            g = reporte_grupos[casa.grupo_id]
            g["casas"].append(item_casa)
            g["total_mes"] += total_mes
            g["saldo_anterior"] += saldo_anterior
            g["saldo_restante"] += saldo_restante
            g["monto_pagado"] += monto_pagado
        else:
            # WhatsApp Individual
            if casa.telefono:
                texto_wa = f"Hola! Te paso el resumen: Abono ${format_money(abono_mes)} + Productos ${format_money(extras)}. Total a pagar: ${format_money(total_mes + saldo_anterior)}."
                item_casa["url_wa"] = f"https://wa.me/549{re.sub(r'\D', '', casa.telefono)}?text={urllib.parse.quote(texto_wa)}"
            reporte_sueltas.append(item_casa)

        total_clientes += 1
        total_abono += abono_mes
        total_extras += extras
        if esta_pagado and monto_pagado == 0:
            total_recaudado += total_mes
        else:
            total_recaudado += monto_pagado

    total_general = total_abono + total_extras

    # Preparar WhatsApp y Estados para Grupos
    for g_id, g in reporte_grupos.items():
        g["pagado"] = all(c["pagado"] for c in g["casas"])
        g["mensaje_enviado"] = all(c["mensaje_enviado"] for c in g["casas"])

        if g["telefono"]:
            cant = len(g["casas"])
            texto_wa = f"Hola! *{g['nombre']}* Te paso el resumen de las {cant} propiedades.\n\n"
            
            # 1. Detalle del mes por casa (SIN saldo anterior)
            for c in g["casas"]:
                nombre_c = c['casa'].nombre_formateado()
                abono_str = format_money(c['abono'])
                extras_str = format_money(c['extras'])
                total_c_str = format_money(c['total_mes']) 
                texto_wa += f"• {nombre_c}: Abono ${abono_str} + Productos ${extras_str} = ${total_c_str}\n"
            
            # 2. Resumen financiero del grupo (Saldo a favor / en contra)
            if g['saldo_anterior'] < -0.1:
                texto_wa += f"\nSaldo a favor (Mes anterior): *${format_money(abs(g['saldo_anterior']))}*"
            elif g['saldo_anterior'] > 0.1:
                texto_wa += f"\nDeuda pendiente (Mes anterior): *${format_money(g['saldo_anterior'])}*"

            # 3. Total Final
            texto_wa += f"\n*TOTAL A PAGAR: ${format_money(g['total_mes'] + g['saldo_anterior'])}*"
            
            tel = re.sub(r'\D', '', g['telefono'])
            if len(tel) == 10: tel = "549" + tel
            g["url_wa"] = f"https://wa.me/{tel}?text={urllib.parse.quote(texto_wa)}"

    lista_grupos = list(reporte_grupos.values())

    return render_template(
        "dashboard/index.html",
        reporte_sueltas=reporte_sueltas,
        reporte_grupos=lista_grupos,
        mes=mes,
        anio=anio,
        mes_congelado=mes_congelado,
        kpi_clientes=total_clientes,
        kpi_abono=total_abono,
        kpi_extras=total_extras,
        kpi_recaudado=total_recaudado,
        kpi_pendiente=total_general - total_recaudado,
        kpi_total=total_general
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
    
    url_wa = None 

    if not pagado and not enviado:
        registro.mensaje_enviado = True
        registro.pagado = False
        
        casa = registro.casa
        if casa.telefono:
            datos = casa.obtener_gastos_mensuales(registro.mes, registro.anio)
            total_mes = datos['total']
            saldo_ant = casa.obtener_saldo_anterior(registro.mes, registro.anio)
            
            nombre_wa = casa.nombre_cliente if casa.nombre_cliente else casa.nombre_formateado()
            texto_wa = f"Hola! {nombre_wa} Te paso el resumen: Total a pagar ${format_money(total_mes + saldo_ant)}. Gracias"
            
            texto_codificado = urllib.parse.quote(texto_wa)
            tel = re.sub(r'\D', '', casa.telefono)
            if len(tel) == 10: tel = "549" + tel
            url_wa = f"https://wa.me/{tel}?text={texto_codificado}"

    elif not pagado and enviado:
        registro.pagado = True
        registro.mensaje_enviado = True
        casa = registro.casa
        total_mes = float(registro.monto) + float(casa.obtener_gastos_mensuales(registro.mes, registro.anio)['extras'])
        saldo_ant = casa.obtener_saldo_anterior(registro.mes, registro.anio)
        registro.monto_pagado = total_mes + saldo_ant

    else:
        registro.pagado = False
        registro.mensaje_enviado = False
        registro.monto_pagado = 0.0
        
    db.session.commit()
    return jsonify({"success": True, "url_wa": url_wa})

@dashboard_bp.route("/sync-abonos", methods=["POST"])
@login_required
@admin_required
def sync_abonos():
    from app.models.visit import Visit
    from sqlalchemy import extract
    
    mes = request.form.get("mes", type=int)
    anio = request.form.get("anio", type=int)
    if not mes or not anio: return redirect(url_for('dashboard.index'))
    
    for casa in Casa.query.filter_by(activo=True).all():
        if not AbonoHistorico.query.filter_by(casa_id=casa.id, mes=mes, anio=anio).first():
            db.session.add(AbonoHistorico(casa_id=casa.id, mes=mes, anio=anio, monto=float(casa.precio_base or 0)))
            
    visitas_mes = Visit.query.filter(extract('month', Visit.fecha) == mes, extract('year', Visit.fecha) == anio).all()
    for visita in visitas_mes:
        for vp in visita.productos:
            vp.precio_unitario = vp.product.precio 
            
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
    
    if registro.monto_pagado >= ((total_mes + saldo_ant) - 0.1): 
        registro.pagado = True
        registro.mensaje_enviado = True
    else:
        registro.pagado = False
        
    db.session.commit()
    return jsonify({"success": True})

# ==========================================
# NUEVAS RUTAS EXCLUSIVAS PARA GRUPOS
# ==========================================

@dashboard_bp.route("/marcar-mensaje-grupo/<int:grupo_id>", methods=["POST"])
@login_required
@admin_required
def marcar_mensaje_grupo(grupo_id):
    mes = request.json.get("mes")
    anio = request.json.get("anio")
    
    casas_grupo = Casa.query.filter_by(grupo_id=grupo_id).all()
    historiales = AbonoHistorico.query.filter(
        AbonoHistorico.casa_id.in_([c.id for c in casas_grupo]),
        AbonoHistorico.mes == mes,
        AbonoHistorico.anio == anio
    ).all()
    
    for h in historiales:
        h.mensaje_enviado = True
        
    db.session.commit()
    return jsonify({"success": True})


@dashboard_bp.route("/toggle-pago-grupo/<int:grupo_id>", methods=["POST"])
@login_required
@admin_required
def toggle_pago_grupo(grupo_id):
    mes = request.json.get("mes")
    anio = request.json.get("anio")
    
    casas_grupo = Casa.query.filter_by(grupo_id=grupo_id).all()
    historiales = AbonoHistorico.query.filter(
        AbonoHistorico.casa_id.in_([c.id for c in casas_grupo]),
        AbonoHistorico.mes == mes,
        AbonoHistorico.anio == anio
    ).all()

    if not historiales:
        return jsonify({"success": False})

    all_pagado = all(h.pagado for h in historiales)
    all_enviado = all(h.mensaje_enviado for h in historiales)
    url_wa = None

    if not all_pagado and not all_enviado:
        # Pasa a Enviado y genera la URL
        for h in historiales:
            h.mensaje_enviado = True
            h.pagado = False
            
        grupo = casas_grupo[0].grupo
        telefono_repr = next((c.telefono for c in casas_grupo if c.telefono), None)
        
        if telefono_repr:
            cant = len(casas_grupo)
            texto_wa = f"Hola! *{grupo.nombre}* Te paso el resumen de las {cant} propiedades.\n\n"
            total_grupo_mes = 0
            total_grupo_saldo_ant = 0
            
            for h in historiales:
                c = h.casa
                abono = float(h.monto)
                extras = float(c.obtener_gastos_mensuales(mes, anio)['extras'])
                saldo_ant = c.obtener_saldo_anterior(mes, anio)
                
                total_c = abono + extras
                total_grupo_mes += total_c
                total_grupo_saldo_ant += saldo_ant
                
                texto_wa += f"• {c.nombre_formateado()}: Abono ${format_money(abono)} + Productos ${format_money(extras)} = ${format_money(total_c)}\n"
            
            if total_grupo_saldo_ant < -0.1:
                texto_wa += f"\nSaldo a favor (Mes anterior): *${format_money(abs(total_grupo_saldo_ant))}*"
            elif total_grupo_saldo_ant > 0.1:
                texto_wa += f"\nDeuda pendiente (Mes anterior): *${format_money(total_grupo_saldo_ant)}*"
                
            texto_wa += f"\n*TOTAL A PAGAR: ${format_money(total_grupo_mes + total_grupo_saldo_ant)}*"
            
            tel = re.sub(r'\D', '', telefono_repr)
            if len(tel) == 10: tel = "549" + tel
            url_wa = f"https://wa.me/{tel}?text={urllib.parse.quote(texto_wa)}"

    elif not all_pagado and all_enviado:
        # Pasa a Pagado (Pagan el total exacto)
        for h in historiales:
            h.pagado = True
            h.mensaje_enviado = True
            c = h.casa
            total_mes = float(h.monto) + float(c.obtener_gastos_mensuales(mes, anio)['extras'])
            saldo_ant = c.obtener_saldo_anterior(mes, anio)
            h.monto_pagado = total_mes + saldo_ant
    else:
        # Resetea a Pendiente
        for h in historiales:
            h.pagado = False
            h.mensaje_enviado = False
            h.monto_pagado = 0.0

    db.session.commit()
    return jsonify({"success": True, "url_wa": url_wa})


@dashboard_bp.route("/registrar-pago-grupo/<int:grupo_id>", methods=["POST"])
@login_required
@admin_required
def registrar_pago_grupo(grupo_id):
    mes = request.json.get("mes")
    anio = request.json.get("anio")
    monto_ingresado = float(request.json.get("monto", 0))

    casas_grupo = Casa.query.filter_by(grupo_id=grupo_id).all()
    historiales = AbonoHistorico.query.filter(
        AbonoHistorico.casa_id.in_([c.id for c in casas_grupo]),
        AbonoHistorico.mes == mes,
        AbonoHistorico.anio == anio
    ).all()

    deudas = []
    total_deuda_grupo = 0
    
    # 1. Calculamos la deuda real de cada casa del grupo
    for h in historiales:
        c = h.casa
        total_mes = float(h.monto) + float(c.obtener_gastos_mensuales(mes, anio)['extras'])
        saldo_ant = c.obtener_saldo_anterior(mes, anio)
        deuda_total = total_mes + saldo_ant
        deuda_restante = deuda_total - h.monto_pagado
        
        total_deuda_grupo += deuda_restante
        deudas.append({"hist": h, "restante": deuda_restante})

    # 2. Distribución del dinero ingresado
    if monto_ingresado >= total_deuda_grupo:
        # Alcanza para saldar a todos y sobra (Distribución equitativa del saldo a favor)
        sobrante = monto_ingresado - total_deuda_grupo
        sobrante_por_casa = sobrante / len(deudas) if len(deudas) > 0 else 0
        
        for d in deudas:
            h = d["hist"]
            h.monto_pagado += d["restante"] + sobrante_por_casa
            h.pagado = True
            h.mensaje_enviado = True
    else:
        # No alcanza, distribuimos hasta donde llegue el dinero (en orden)
        plata_disponible = monto_ingresado
        for d in deudas:
            h = d["hist"]
            if plata_disponible <= 0:
                break
                
            if plata_disponible >= d["restante"]:
                h.monto_pagado += d["restante"]
                plata_disponible -= d["restante"]
                h.pagado = True
                h.mensaje_enviado = True
            else:
                h.monto_pagado += plata_disponible
                plata_disponible = 0
                h.pagado = False

    db.session.commit()
    return jsonify({"success": True})