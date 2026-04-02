from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from app.decorators import admin_required
from app import db
from app.models import Casa, Country, Barrio
from app.models.abono_historico import AbonoHistorico
from app.models.cierre_mes import CierreMes
from app.models.visit import Visit
from datetime import datetime
import re
import urllib.parse
from sqlalchemy.orm import joinedload
from sqlalchemy import func, extract, and_, or_ # <-- Herramientas de matemáticas SQL

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

def natural_sort_key(casa):
    k_country = casa.country.nombre.lower() if casa.country else "zzz"
    k_barrio = casa.barrio.nombre.lower() if casa.barrio else ""
    k_numero = [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(casa.numero))]
    return (k_country, k_barrio, k_numero)

def format_money(value):
    return f"{value:,.0f}".replace(",", ".")

def limpiar_telefono(tel):
    if not tel: return ""
    num = re.sub(r'\D', '', tel)
    if len(num) == 10: num = "549" + num
    return num

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
    
    registro_congelado = CierreMes.query.filter_by(mes=mes, anio=anio).first()
    mes_congelado = True if registro_congelado else False

    # 1. Traemos historiales y casas de base en 1 sola consulta
    historiales_del_mes = AbonoHistorico.query.filter_by(mes=mes, anio=anio).options(
        joinedload(AbonoHistorico.casa).joinedload(Casa.country),
        joinedload(AbonoHistorico.casa).joinedload(Casa.barrio),
        joinedload(AbonoHistorico.casa).joinedload(Casa.grupo)
    ).all()
    
    historial_dict = {h.casa_id: h for h in historiales_del_mes}

    if mes_congelado:
        casas_raw = [h.casa for h in historiales_del_mes]
    else:
        casas_raw = Casa.query.options(
            joinedload(Casa.country),
            joinedload(Casa.barrio),
            joinedload(Casa.grupo)
        ).all()

    # --- INICIO MAGIA SQL: EXTRAS Y SALDOS ---
    
    # A. Diccionario Rápido de EXTRAS (Productos) de ESTE mes
    # (Calculamos todo directo en la base de datos sin instanciar objetos)
    visitas_mes = Visit.query.filter(
        extract('month', Visit.fecha) == mes,
        extract('year', Visit.fecha) == anio
    ).options(joinedload(Visit.productos), joinedload(Visit.promo)).all()
    
    diccionario_extras = {}
    for v in visitas_mes:
        total_v = 0.0
        for vp in v.productos:
            # Si el mes está congelado o ya tiene precio histórico, usamos ese. Si no, el actual.
            precio = vp.precio_unitario if (mes_congelado and vp.precio_unitario) else vp.product.precio
            total_v += float(vp.cantidad) * float(precio)
        if v.promo:
            total_v += float(v.promo.precio)
            
        diccionario_extras[v.casa_id] = diccionario_extras.get(v.casa_id, 0.0) + total_v

    # B. Diccionario Rápido de SALDOS ANTERIORES
    # Primero buscamos toda la plata que DEBÍAN pagar en la historia (antes de este mes)
    saldos_hist = db.session.query(
        AbonoHistorico.casa_id,
        func.sum(AbonoHistorico.monto).label('total_abonos'),
        func.sum(AbonoHistorico.monto_pagado).label('total_pagado')
    ).filter(
        or_(
            AbonoHistorico.anio < anio,
            and_(AbonoHistorico.anio == anio, AbonoHistorico.mes < mes)
        )
    ).group_by(AbonoHistorico.casa_id).all()

    # Buscamos todos los extras consumidos en la historia antes de este mes
    visitas_viejas = Visit.query.filter(
        or_(
            extract('year', Visit.fecha) < anio,
            and_(extract('year', Visit.fecha) == anio, extract('month', Visit.fecha) < mes)
        )
    ).options(joinedload(Visit.productos), joinedload(Visit.promo)).all()
    
    extras_historicos = {}
    for v in visitas_viejas:
        total_v = 0.0
        for vp in v.productos:
            precio = vp.precio_unitario if vp.precio_unitario else vp.product.precio
            total_v += float(vp.cantidad) * float(precio)
        if v.promo:
            total_v += float(v.promo.precio)
        extras_historicos[v.casa_id] = extras_historicos.get(v.casa_id, 0.0) + total_v

    # Consolidamos ambos en un diccionario final: {casa_id: deuda_total}
    diccionario_saldos = {}
    for row in saldos_hist:
        casa_id = row.casa_id
        deuda = (float(row.total_abonos or 0) + extras_historicos.get(casa_id, 0.0)) - float(row.total_pagado or 0)
        diccionario_saldos[casa_id] = round(deuda, 2)
        
    # --- FIN MAGIA SQL ---

    casas = []
    for c in casas_raw:
        if c.activo:
            casas.append(c)
        else:
            if diccionario_extras.get(c.id, 0.0) > 0:
                casas.append(c)

    casas.sort(key=natural_sort_key)

    reporte_sueltas = []
    reporte_grupos = {} 
    
    total_clientes = 0
    total_abono = 0.0
    total_extras = 0.0
    total_recaudado = 0.0 
    total_deuda_anterior = 0.0 
    
    hubo_cambios = False

    for casa in casas:
        # OPTIMIZACIÓN LECTURA EXTRAS Y SALDO: Lectura instantánea de RAM O(1)
        extras = round(diccionario_extras.get(casa.id, 0.0), 2)
        saldo_anterior = diccionario_saldos.get(casa.id, 0.0)

        historial = historial_dict.get(casa.id)
        
        if mes_congelado and historial:
            abono_mes = float(historial.monto)
        else:
            abono_mes = float(casa.precio_base or 0)
        
        total_mes = abono_mes + extras
        
        if saldo_anterior > 0:
            total_deuda_anterior += saldo_anterior

        # Autocorrector de Grupos/Casas Pagadas
        if mes_congelado and historial and getattr(historial, 'pagado', False):
            monto_ideal = total_mes + saldo_anterior
            monto_actual = float(getattr(historial, 'monto_pagado', 0) or 0)
            if abs(monto_actual - monto_ideal) > 0.01:
                historial.monto_pagado = monto_ideal
                hubo_cambios = True

        monto_pagado = float(getattr(historial, 'monto_pagado', 0) or 0)
        saldo_restante = (total_mes + saldo_anterior) - monto_pagado

        esta_pagado = getattr(historial, 'pagado', False) if historial else False
        mensaje_enviado = getattr(historial, 'mensaje_enviado', False) if historial else False

        if mes_congelado and historial:
            if not casa.grupo_id:
                if saldo_restante <= 0.01:
                    esta_pagado = True
                    mensaje_enviado = True
                    if not historial.pagado:
                        historial.pagado = True
                        historial.mensaje_enviado = True
                        hubo_cambios = True

        item_casa = {
            "id_historial": historial.id if historial else None,
            "historial_obj": historial, 
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
            if casa.telefono:
                num_tel = limpiar_telefono(casa.telefono)
                texto_wa = f"Hola! Te paso el resumen: Abono ${format_money(abono_mes)} + Productos ${format_money(extras)}. Total a pagar: ${format_money(total_mes + saldo_anterior)}."
                item_casa["url_wa"] = f"https://wa.me/{num_tel}?text={urllib.parse.quote(texto_wa)}"
            reporte_sueltas.append(item_casa)

        total_clientes += 1
        total_abono += abono_mes
        total_extras += extras
        if esta_pagado and monto_pagado == 0:
            total_recaudado += total_mes
        else:
            total_recaudado += monto_pagado

    total_general = total_abono + total_extras + total_deuda_anterior

    for g_id, g in reporte_grupos.items():
        if mes_congelado and g["saldo_restante"] <= 0.01:
            g["pagado"] = True
            g["mensaje_enviado"] = True
            for c in g["casas"]:
                c["pagado"] = True
                c["mensaje_enviado"] = True
                hist_obj = c["historial_obj"]
                if hist_obj and not hist_obj.pagado:
                    hist_obj.pagado = True
                    hist_obj.mensaje_enviado = True
                    hubo_cambios = True
        else:
            g["pagado"] = all(c["pagado"] for c in g["casas"])
            g["mensaje_enviado"] = all(c["mensaje_enviado"] for c in g["casas"])

        if g["telefono"]:
            num_tel = limpiar_telefono(g["telefono"])
            cant = len(g["casas"])
            texto_wa = f"Hola! *{g['nombre']}* Te paso el resumen de las {cant} propiedades.\n\n"
            for c in g["casas"]:
                texto_wa += f"• {c['casa'].nombre_formateado()}: Abono ${format_money(c['abono'])} + Productos ${format_money(c['extras'])} = ${format_money(c['total_mes'])}\n"
            if g['saldo_anterior'] < -0.1:
                texto_wa += f"\nSaldo a favor (Mes anterior): *${format_money(abs(g['saldo_anterior']))}*"
            elif g['saldo_anterior'] > 0.1:
                texto_wa += f"\nDeuda pendiente (Mes anterior): *${format_money(g['saldo_anterior'])}*"
            texto_wa += f"\n*TOTAL A PAGAR: ${format_money(g['total_mes'] + g['saldo_anterior'])}*"
            g["url_wa"] = f"https://wa.me/{num_tel}?text={urllib.parse.quote(texto_wa)}"

    if hubo_cambios:
        db.session.commit()

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
        kpi_deuda=total_deuda_anterior,
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

@dashboard_bp.route("/marcar-pagado-directo/<int:id>", methods=["POST"])
@login_required
@admin_required
def marcar_pagado_directo(id):
    registro = AbonoHistorico.query.get_or_404(id)
    
    casa = registro.casa
    total_mes = float(registro.monto) + float(casa.obtener_gastos_mensuales(registro.mes, registro.anio)['extras'])
    saldo_ant = casa.obtener_saldo_anterior(registro.mes, registro.anio)
    
    registro.pagado = True
    registro.mensaje_enviado = True
    registro.monto_pagado = total_mes + saldo_ant
    
    db.session.commit()
    return jsonify({"success": True})


@dashboard_bp.route("/sync-abonos", methods=["POST"])
@login_required
@admin_required
def sync_abonos():
    from app.models.visit import Visit
    from sqlalchemy import extract
    
    mes = request.form.get("mes", type=int)
    anio = request.form.get("anio", type=int)
    if not mes or not anio: return redirect(url_for('dashboard.index'))
    
    cierre = CierreMes.query.filter_by(mes=mes, anio=anio).first()
    if not cierre:
        db.session.add(CierreMes(mes=mes, anio=anio))
    
    for casa in Casa.query.filter_by(activo=True).all():
        hist = AbonoHistorico.query.filter_by(casa_id=casa.id, mes=mes, anio=anio).first()
        if not hist:
            db.session.add(AbonoHistorico(casa_id=casa.id, mes=mes, anio=anio, monto=float(casa.precio_base or 0)))
        else:
            hist.monto = float(casa.precio_base or 0)
            
    db.session.commit()
    return redirect(url_for('dashboard.index', mes=mes, anio=anio))

@dashboard_bp.route("/unsync-abonos", methods=["POST"])
@login_required
@admin_required
def unsync_abonos():
    mes = request.form.get("mes", type=int)
    anio = request.form.get("anio", type=int)
    if mes and anio:
        CierreMes.query.filter_by(mes=mes, anio=anio).delete()
        
        fantasmas = AbonoHistorico.query.filter_by(mes=mes, anio=anio, pagado=False).all()
        for f in fantasmas:
            if not f.monto_pagado or float(f.monto_pagado) <= 0.01:
                db.session.delete(f)
                
        db.session.commit()
    return redirect(url_for('dashboard.index', mes=mes, anio=anio))


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
        for h in historiales:
            h.pagado = True
            h.mensaje_enviado = True
            c = h.casa
            total_mes = float(h.monto) + float(c.obtener_gastos_mensuales(mes, anio)['extras'])
            saldo_ant = c.obtener_saldo_anterior(mes, anio)
            h.monto_pagado = total_mes + saldo_ant
    else:
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
    
    for h in historiales:
        c = h.casa
        total_mes = float(h.monto) + float(c.obtener_gastos_mensuales(mes, anio)['extras'])
        saldo_ant = c.obtener_saldo_anterior(mes, anio)
        deuda_total = total_mes + saldo_ant
        deuda_restante = deuda_total - h.monto_pagado
        
        total_deuda_grupo += deuda_restante
        deudas.append({"hist": h, "restante": deuda_restante})

    if monto_ingresado >= total_deuda_grupo:
        sobrante = monto_ingresado - total_deuda_grupo
        sobrante_por_casa = sobrante / len(deudas) if len(deudas) > 0 else 0
        
        for d in deudas:
            h = d["hist"]
            h.monto_pagado += d["restante"] + sobrante_por_casa
            h.pagado = True
            h.mensaje_enviado = True
    else:
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


@dashboard_bp.route("/planilla-impresion")
@login_required
@admin_required
def planilla_impresion():
    mes = int(request.args.get("mes", datetime.now().month))
    anio = int(request.args.get("anio", datetime.now().year))
    
    registro_congelado = CierreMes.query.filter_by(mes=mes, anio=anio).first()
    if registro_congelado:
        historiales = AbonoHistorico.query.filter_by(mes=mes, anio=anio).all()
        casas = [h.casa for h in historiales]
    else:
        casas = Casa.query.filter_by(activo=True).all()

    casas.sort(key=natural_sort_key)
    
    filas = []
    for casa in casas:
        datos = casa.obtener_gastos_mensuales(mes, anio)
        producto = float(datos.get("extras", 0))
        
        historial = AbonoHistorico.query.filter_by(casa_id=casa.id, mes=mes, anio=anio).first()
        abono = float(historial.monto) if (registro_congelado and historial) else float(casa.precio_base or 0)
        
        saldo_anterior = casa.obtener_saldo_anterior(mes, anio)
        total_a_pagar = abono + producto + saldo_anterior
            
        filas.append({
            "cliente": casa.nombre_formateado(),
            "producto": producto,
            "abono": abono,
            "saldo_anterior": saldo_anterior,
            "total_a_pagar": total_a_pagar
        })
        
    nombres_meses = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    nombre_mes = nombres_meses[mes - 1]

    return render_template("dashboard/planilla.html", filas=filas, mes_nombre=nombre_mes, anio=anio)

@dashboard_bp.route("/api/totales")
@login_required
@admin_required
def api_totales():
    mes = int(request.args.get("mes", datetime.now().month))
    anio = int(request.args.get("anio", datetime.now().year))
    
    registro_congelado = CierreMes.query.filter_by(mes=mes, anio=anio).first()
    mes_congelado = True if registro_congelado else False

    # 1. Traemos historiales
    historiales_del_mes = AbonoHistorico.query.filter_by(mes=mes, anio=anio).all()
    historial_dict = {h.casa_id: h for h in historiales_del_mes}

    if mes_congelado:
        casas_raw = [h.casa for h in historiales_del_mes]
    else:
        casas_raw = Casa.query.all()

    # 2. Diccionario de Extras (CORREGIDO)
    visitas_mes = Visit.query.filter(
        extract('month', Visit.fecha) == mes,
        extract('year', Visit.fecha) == anio
    ).options(joinedload(Visit.productos), joinedload(Visit.promo)).all()
    
    diccionario_extras = {}
    for v in visitas_mes:
        total_v = 0.0
        for vp in v.productos:
            precio = vp.precio_unitario if (mes_congelado and vp.precio_unitario) else vp.product.precio
            total_v += float(vp.cantidad) * float(precio)
        if v.promo:
            total_v += float(v.promo.precio)
        diccionario_extras[v.casa_id] = diccionario_extras.get(v.casa_id, 0.0) + total_v

    # 3. Diccionario de Saldos (CORREGIDO)
    saldos_hist = db.session.query(
        AbonoHistorico.casa_id,
        func.sum(AbonoHistorico.monto).label('total_abonos'),
        func.sum(AbonoHistorico.monto_pagado).label('total_pagado')
    ).filter(
        or_(
            AbonoHistorico.anio < anio,
            and_(AbonoHistorico.anio == anio, AbonoHistorico.mes < mes)
        )
    ).group_by(AbonoHistorico.casa_id).all()

    visitas_viejas = Visit.query.filter(
        or_(
            extract('year', Visit.fecha) < anio,
            and_(extract('year', Visit.fecha) == anio, extract('month', Visit.fecha) < mes)
        )
    ).options(joinedload(Visit.productos), joinedload(Visit.promo)).all()
    
    extras_historicos = {}
    for v in visitas_viejas:
        total_v = 0.0
        for vp in v.productos:
            precio = vp.precio_unitario if vp.precio_unitario else vp.product.precio
            total_v += float(vp.cantidad) * float(precio)
        if v.promo:
            total_v += float(v.promo.precio)
        extras_historicos[v.casa_id] = extras_historicos.get(v.casa_id, 0.0) + total_v

    diccionario_saldos = {}
    for row in saldos_hist:
        casa_id = row.casa_id
        deuda = (float(row.total_abonos or 0) + extras_historicos.get(casa_id, 0.0)) - float(row.total_pagado or 0)
        diccionario_saldos[casa_id] = round(deuda, 2)

    casas = []
    for c in casas_raw:
        if c.activo:
            casas.append(c)
        else:
            if diccionario_extras.get(c.id, 0.0) > 0:
                casas.append(c)

    total_abono = 0.0
    total_extras = 0.0
    total_recaudado = 0.0 
    total_deuda_anterior = 0.0 

    for casa in casas:
        extras = round(diccionario_extras.get(casa.id, 0.0), 2)
        saldo_anterior = diccionario_saldos.get(casa.id, 0.0)

        historial = historial_dict.get(casa.id)
        
        abono_mes = float(historial.monto) if (mes_congelado and historial) else float(casa.precio_base or 0)
        total_mes = abono_mes + extras
        
        if saldo_anterior > 0:
            total_deuda_anterior += saldo_anterior

        esta_pagado = getattr(historial, 'pagado', False) if historial else False
        monto_pagado = float(getattr(historial, 'monto_pagado', 0) or 0)

        total_abono += abono_mes
        total_extras += extras
        
        if esta_pagado and monto_pagado == 0:
            total_recaudado += total_mes
        else:
            total_recaudado += monto_pagado

    total_general = total_abono + total_extras + total_deuda_anterior
    kpi_pendiente = total_general - total_recaudado

    return jsonify({
        "kpi_deuda": f"${format_money(total_deuda_anterior)}",
        "kpi_recaudado": f"${format_money(total_recaudado)}",
        "kpi_pendiente": f"${format_money(kpi_pendiente)}",
        "kpi_total": f"${format_money(total_general)}"
    })