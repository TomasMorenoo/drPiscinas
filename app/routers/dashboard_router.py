from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.decorators import admin_required
from app import db
from app.models import Casa, Country, Barrio
from app.models.abono_historico import AbonoHistorico
from app.models.cierre_mes import CierreMes
from app.models.visit import Visit
from datetime import datetime, timedelta, timezone
import re
import urllib.parse
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import func, extract, and_, or_
import calendar
import uuid

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

# ==========================================
# UTILIDADES Y FORMATOS
# ==========================================

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

def obtener_marca_tiempo(mes_contexto, anio_contexto):
    ahora = datetime.now()
    if anio_contexto == ahora.year and mes_contexto == ahora.month:
        return ahora
    else:
        ultimo_dia = calendar.monthrange(anio_contexto, mes_contexto)[1]
        return datetime(anio_contexto, mes_contexto, ultimo_dia, ahora.hour, ahora.minute, ahora.second, ahora.microsecond)

# ==========================================
# LOGICA DE MENSAJES (WHATSAPP)
# ==========================================

def get_ar_time():
    tz_ar = timezone(timedelta(hours=-3))
    return datetime.now(tz_ar)

def obtener_saludo_tiempo(nombre):
    ahora = get_ar_time()
    saludo = "Buenos Días" if ahora.hour < 12 else "Buenas Tardes"
    return f"{saludo} {nombre}"

def get_nombre_limpio(casa):
    nombre = casa.nombre_formateado()
    return re.sub(r'(?i)\s+S/N$', '', nombre).strip()

def obtener_detalle_productos(casa, mes, anio):
    productos_dict = {}
    for v in casa.visitas:
        if v.fecha.month == mes and v.fecha.year == anio:
            for vp in v.productos:
                nombre = vp.product.nombre.strip()
                unidad = vp.product.unidad.strip() if vp.product.unidad else ""
                clave = f"{nombre}_{unidad}"
                
                if clave not in productos_dict:
                    productos_dict[clave] = {'nombre': nombre, 'unidad': unidad, 'cantidad': 0.0}
                productos_dict[clave]['cantidad'] += float(vp.cantidad)
    
    detalles = []
    for p in productos_dict.values():
        c = p['cantidad']
        cant_str = str(int(c)) if c.is_integer() else str(c)
        detalles.append(f"{cant_str}{p['unidad']} de {p['nombre']}")
    return detalles

def generar_texto_deuda(hist_deuda, saldo_anterior, mes, anio):
    if saldo_anterior <= 0.1:
        return ""
    meses_nombres = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    
    texto = f"\nSaldo pendiente: $ {format_money(saldo_anterior)}\n"
    
    if len(hist_deuda) == 1:
        mes_txt = f"{meses_nombres[hist_deuda[0].mes-1]} {hist_deuda[0].anio}"
        texto += f"* Correspondiente al mes de {mes_txt}\n"
    elif len(hist_deuda) > 1:
        meses_txt = ", ".join([f"{meses_nombres[h.mes-1]} {h.anio}" for h in hist_deuda])
        texto += f"* Correspondiente a los meses de {meses_txt}\n"
    else:
        texto += "* Correspondiente a meses anteriores\n"
    return texto

def generar_wa_individual(casa, mes, anio, abono_mes, extras, saldo_anterior):
    nombre_wa = casa.nombre_cliente if casa.nombre_cliente else get_nombre_limpio(casa)
    saludo = obtener_saludo_tiempo(nombre_wa)
    total_final = abono_mes + extras + saldo_anterior
    
    texto_wa = f"{saludo} como te va, te recuerdo el abono de la pile\n\n"
    texto_wa += f"*-- TOTAL ${format_money(total_final)} --*\n\n"
    texto_wa += "Detalle:\n\n"
    texto_wa += f"Mes de mantenimiento ${format_money(abono_mes)}\n"
    
    if extras > 0:
        texto_wa += f"Productos Utilizados $ {format_money(extras)}\n"
        prods = obtener_detalle_productos(casa, mes, anio)
        for p in prods:
            texto_wa += f"* {p}\n"
            
    if saldo_anterior > 0.1:
        hist_deuda = [h for h in casa.historial_abonos if not getattr(h, 'pagado', False) and (h.anio < anio or (h.anio == anio and h.mes < mes))]
        texto_wa += generar_texto_deuda(hist_deuda, saldo_anterior, mes, anio)
        
    texto_wa += "\nMuchas Gracias."
    return texto_wa

def generar_wa_grupo(grupo_nombre, casas_data, mes, anio, total_grupo, saldo_anterior_grupo):
    saludo = obtener_saludo_tiempo(grupo_nombre)
    cant = len(casas_data)
    
    texto_wa = f"{saludo} Te paso el resumen de las {cant} propiedades.\n\n"
    texto_wa += f"*-- TOTAL ${format_money(total_grupo + saldo_anterior_grupo)} --*\n\n"
    
    for c in casas_data:
        casa_obj = c['casa']
        nombre_casa = get_nombre_limpio(casa_obj)
        abono = c['abono']
        extras = c['extras']
        total_c = abono + extras
        
        texto_wa += f"• *{nombre_casa}:* Abono ${format_money(abono)} + Productos ${format_money(extras)} = *${format_money(total_c)}*\n"
        
        if extras > 0:
            prods = obtener_detalle_productos(casa_obj, mes, anio)
            if prods:
                texto_wa += f"Detalle Productos: {', '.join(prods)}\n"
        texto_wa += "\n"
        
    if saldo_anterior_grupo < -0.1:
        texto_wa += f"Saldo a favor: *${format_money(abs(saldo_anterior_grupo))}*\n\n"
    elif saldo_anterior_grupo > 0.1:
        texto_wa += f"Saldo pendiente: *${format_money(saldo_anterior_grupo)}*\n\n"
        
    texto_wa += "Muchas Gracias."
    return texto_wa

# ==========================================
# LOGICA DE PAGOS Y CASCADA
# ==========================================

def revertir_transaccion(h, txn_id):
    if getattr(h, 'detalle_pagos', None) and txn_id in h.detalle_pagos:
        pagos = h.detalle_pagos.split('|')
        nuevos_pagos = []
        monto_a_restar = 0.0
        ultimo_txn = None
        
        for p in pagos:
            if ':' in p:
                t_id, amt = p.split(':')
                if t_id == txn_id:
                    monto_a_restar += float(amt)
                else:
                    nuevos_pagos.append(p)
                    ultimo_txn = t_id
        
        h.monto_pagado = max(0.0, float(h.monto_pagado or 0) - monto_a_restar)
        h.detalle_pagos = "|".join(nuevos_pagos) if nuevos_pagos else None
        h.transaccion_id = ultimo_txn
        
        datos = h.casa.obtener_gastos_mensuales(h.mes, h.anio)
        total_mes = float(h.monto) + float(datos.get('extras', 0))
        
        if h.monto_pagado < (total_mes - 0.01):
            h.pagado = False
            
        if h.monto_pagado <= 0.01:
            h.monto_pagado = 0.0
            h.fecha_pago = None
            h.cobrado_por = None
            h.mensaje_enviado = False
    else:
        h.pagado = False
        h.mensaje_enviado = False
        h.monto_pagado = 0.0
        h.cobrado_por = None
        h.fecha_pago = None
        h.transaccion_id = None
        if hasattr(h, 'detalle_pagos'):
            h.detalle_pagos = None

def aplicar_pago_en_cascada(casa, monto_ingresado, username, mes_contexto, anio_contexto):
    from app.models.abono_historico import AbonoHistorico
    marca_tiempo = obtener_marca_tiempo(mes_contexto, anio_contexto)
    
    txn_id = f"TXN-{uuid.uuid4().hex[:8].upper()}"
    historiales = AbonoHistorico.query.filter_by(casa_id=casa.id).order_by(AbonoHistorico.anio.asc(), AbonoHistorico.mes.asc()).all()
    plata = float(monto_ingresado)
    
    for h in historiales:
        if plata <= 0.01:
            break
        if not h.pagado:
            datos = casa.obtener_gastos_mensuales(h.mes, h.anio)
            total_mes = float(h.monto) + float(datos['extras'])
            deuda = total_mes - float(h.monto_pagado or 0)
            
            monto_aplicado = 0.0
            if deuda > 0.01:
                if plata >= (deuda - 0.01):
                    monto_aplicado = deuda
                    h.monto_pagado = float(h.monto_pagado or 0) + deuda
                    plata -= deuda
                    h.pagado = True
                    h.mensaje_enviado = True
                else:
                    monto_aplicado = plata
                    h.monto_pagado = float(h.monto_pagado or 0) + plata
                    plata = 0
                
                h.cobrado_por = username
                h.fecha_pago = marca_tiempo
                h.transaccion_id = txn_id
                
                detalle_str = f"{txn_id}:{monto_aplicado}"
                actual = getattr(h, 'detalle_pagos', None)
                h.detalle_pagos = f"{actual}|{detalle_str}" if actual else detalle_str
                    
    if plata > 0.01 and historiales:
        ultimo = historiales[-1]
        ultimo.monto_pagado = float(ultimo.monto_pagado or 0) + plata
        ultimo.pagado = True
        ultimo.mensaje_enviado = True
        ultimo.cobrado_por = username
        ultimo.fecha_pago = marca_tiempo
        ultimo.transaccion_id = txn_id
        detalle_str = f"{txn_id}:{plata}"
        actual = getattr(ultimo, 'detalle_pagos', None)
        ultimo.detalle_pagos = f"{actual}|{detalle_str}" if actual else detalle_str

    hist_actual = next((h for h in historiales if h.mes == mes_contexto and h.anio == anio_contexto), None)
    if hist_actual:
        hist_actual.transaccion_id = txn_id
        detalle_str = f"{txn_id}:0.0"
        actual = getattr(hist_actual, 'detalle_pagos', None)
        if not actual:
            hist_actual.detalle_pagos = detalle_str
        elif txn_id not in actual:
            hist_actual.detalle_pagos = f"{actual}|{detalle_str}"

# ==========================================
# RUTAS DEL DASHBOARD
# ==========================================

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

    query_casas = Casa.query.options(
        joinedload(Casa.country),
        joinedload(Casa.barrio),
        joinedload(Casa.grupo),
        selectinload(Casa.historial_abonos),
        selectinload(Casa.visitas).selectinload(Visit.productos),
        selectinload(Casa.visitas).joinedload(Visit.promo)
    )

    casas_raw = query_casas.all()
    historial_dict = {h.casa_id: h for h in AbonoHistorico.query.filter_by(mes=mes, anio=anio).all()}

    casas = []
    for c in casas_raw:
        if c.fecha_creacion:
            if c.fecha_creacion.year > anio or (c.fecha_creacion.year == anio and c.fecha_creacion.month > mes):
                continue
                
        datos_v = c.obtener_gastos_mensuales(mes, anio)
        extras_v = float(datos_v.get("extras", 0))
        saldo_ant_v = c.obtener_saldo_anterior(mes, anio)
        hist_v = historial_dict.get(c.id)
        
        # AHORA RESPETA CUALQUIER HISTORIAL GUARDADO
        if hist_v:
            ab_v = float(hist_v.monto)
        else:
            ab_v = float(c.precio_base or 0) if (c.activo or extras_v > 0) else 0.0
        
        if not c.activo and (ab_v + extras_v + saldo_ant_v) <= 0.1:
            continue
            
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
        datos = casa.obtener_gastos_mensuales(mes, anio)
        extras = float(datos.get("extras", 0))
        saldo_anterior = casa.obtener_saldo_anterior(mes, anio)
        historial = historial_dict.get(casa.id)
        
        # AHORA RESPETA CUALQUIER HISTORIAL GUARDADO
        if historial:
            abono_mes = float(historial.monto)
        else:
            abono_mes = float(casa.precio_base or 0) if (casa.activo or extras > 0) else 0.0
            
        total_mes = abono_mes + extras
        
        if saldo_anterior > 0:
            total_deuda_anterior += saldo_anterior

        monto_pagado = float(getattr(historial, 'monto_pagado', 0) or 0)
        saldo_restante = (total_mes + saldo_anterior) - monto_pagado
        esta_pagado = getattr(historial, 'pagado', False) if historial else False
        mensaje_enviado = getattr(historial, 'mensaje_enviado', False) if historial else False

        pagos_en_este_dashboard = sum(
            float(h.monto_pagado or 0) 
            for h in casa.historial_abonos 
            if h.fecha_pago and h.fecha_pago.month == mes and h.fecha_pago.year == anio
        )

        if mes_congelado and historial and not casa.grupo_id:
            if saldo_restante <= 0.01 and not historial.pagado:
                esta_pagado = True
                mensaje_enviado = True
                historial.pagado = True
                historial.mensaje_enviado = True
                historial.cobrado_por = "SISTEMA (Auto $0)"
                historial.fecha_pago = obtener_marca_tiempo(mes, anio)
                
                txn_id = f"TXN-{uuid.uuid4().hex[:8].upper()}"
                historial.transaccion_id = txn_id
                detalle_str = f"{txn_id}:{abono_mes + extras}"
                historial.detalle_pagos = detalle_str
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
            "pagos_en_este_dashboard": pagos_en_este_dashboard,
            "url_wa": "" 
        }

        if casa.grupo_id:
            if casa.grupo_id not in reporte_grupos:
                reporte_grupos[casa.grupo_id] = {
                    "grupo_id": casa.grupo_id, "nombre": casa.grupo.nombre, "casas": [],
                    "total_mes": 0.0, "saldo_anterior": 0.0, "saldo_restante": 0.0,
                    "monto_pagado": 0.0, "telefono": casa.telefono
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
                texto_wa = generar_wa_individual(casa, mes, anio, abono_mes, extras, saldo_anterior)
                item_casa["url_wa"] = f"whatsapp://send?phone={num_tel}&text={urllib.parse.quote(texto_wa)}"
            
            reporte_sueltas.append(item_casa)

        total_clientes += 1
        total_abono += abono_mes
        total_extras += extras
        
        if esta_pagado:
            if monto_pagado == 0:
                total_recaudado += (total_mes + saldo_anterior)
            else:
                total_recaudado += monto_pagado
        else:
            total_recaudado += monto_pagado

    total_general = total_abono + total_extras + total_deuda_anterior

    for g_id, g in reporte_grupos.items():
        if mes_congelado and g["saldo_restante"] <= 0.01:
            g["pagado"] = True
            g["mensaje_enviado"] = True
            for c in g["casas"]:
                c["pagado"] = True; c["mensaje_enviado"] = True
                hist_obj = c["historial_obj"]
                if hist_obj and not hist_obj.pagado:
                    hist_obj.pagado = True
                    hist_obj.mensaje_enviado = True
                    
                    txn_id = f"TXN-{uuid.uuid4().hex[:8].upper()}"
                    hist_obj.transaccion_id = txn_id
                    total_c = float(hist_obj.monto) + c["extras"]
                    hist_obj.detalle_pagos = f"{txn_id}:{total_c}"
                    hubo_cambios = True
        else:
            g["pagado"] = all(c["pagado"] for c in g["casas"])
            g["mensaje_enviado"] = all(c["mensaje_enviado"] for c in g["casas"])

        if g["telefono"]:
            num_tel = limpiar_telefono(g["telefono"])
            texto_wa = generar_wa_grupo(g['nombre'], g["casas"], mes, anio, g['total_mes'], g['saldo_anterior'])
            g["url_wa"] = f"whatsapp://send?phone={num_tel}&text={urllib.parse.quote(texto_wa)}"

    if hubo_cambios:
        db.session.commit()

    return render_template(
        "dashboard/index.html",
        reporte_sueltas=reporte_sueltas,
        reporte_grupos=list(reporte_grupos.values()),
        mes=mes, anio=anio, mes_congelado=mes_congelado,
        kpi_clientes=total_clientes, kpi_abono=total_abono, kpi_extras=total_extras,
        kpi_deuda=total_deuda_anterior, kpi_recaudado=total_recaudado,
        kpi_pendiente=total_general - total_recaudado, kpi_total=total_general
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
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    
    registro = AbonoHistorico.query.get_or_404(id)
    pagado = getattr(registro, 'pagado', False)
    enviado = getattr(registro, 'mensaje_enviado', False)
    url_wa = None 

    if action == 'undo' or (pagado and action != 'advance'):
        txns_to_revert = []
        if getattr(registro, 'detalle_pagos', None):
            for p in registro.detalle_pagos.split('|'):
                if ':' in p:
                    txns_to_revert.append(p.split(':')[0])
        elif getattr(registro, 'transaccion_id', None):
            txns_to_revert.append(registro.transaccion_id)
            
        if txns_to_revert:
            for t_id in txns_to_revert:
                hermanos = AbonoHistorico.query.filter(
                    or_(
                        AbonoHistorico.transaccion_id == t_id,
                        AbonoHistorico.detalle_pagos.like(f"%{t_id}%")
                    )
                ).all()
                for h in hermanos:
                    revertir_transaccion(h, t_id)
        else:
            revertir_transaccion(registro, "VIEJO")
            
    elif action == 'advance' or not pagado:
        if not pagado and not enviado:
            registro.mensaje_enviado = True
            casa = registro.casa
            if casa.telefono:
                datos = casa.obtener_gastos_mensuales(registro.mes, registro.anio)
                saldo_ant = casa.obtener_saldo_anterior(registro.mes, registro.anio)
                
                texto_wa = generar_wa_individual(casa, registro.mes, registro.anio, float(registro.monto), float(datos['extras']), saldo_ant)
                url_wa = f"whatsapp://send?phone={limpiar_telefono(casa.telefono)}&text={urllib.parse.quote(texto_wa)}"
        else:
            casa = registro.casa
            datos = casa.obtener_gastos_mensuales(registro.mes, registro.anio)
            saldo_ant = casa.obtener_saldo_anterior(registro.mes, registro.anio)
            total_a_pagar = float(registro.monto) + float(datos['extras']) + saldo_ant - float(registro.monto_pagado or 0)
            
            if total_a_pagar > 0.01:
                aplicar_pago_en_cascada(casa, total_a_pagar, current_user.username, registro.mes, registro.anio)
            else:
                registro.pagado = True
                registro.mensaje_enviado = True
                registro.cobrado_por = current_user.username
                registro.fecha_pago = obtener_marca_tiempo(registro.mes, registro.anio)
                
                if hasattr(registro, 'transaccion_id'):
                    txn_id = f"TXN-{uuid.uuid4().hex[:8].upper()}"
                    registro.transaccion_id = txn_id
                    detalle_str = f"{txn_id}:{total_a_pagar}"
                    actual = getattr(registro, 'detalle_pagos', None)
                    registro.detalle_pagos = f"{actual}|{detalle_str}" if actual else detalle_str
                
    db.session.commit()
    return jsonify({"success": True, "url_wa": url_wa})

@dashboard_bp.route("/marcar-pagado-directo/<int:id>", methods=["POST"])
@login_required
@admin_required
def marcar_pagado_directo(id):
    registro = AbonoHistorico.query.get_or_404(id)
    casa = registro.casa
    datos = casa.obtener_gastos_mensuales(registro.mes, registro.anio)
    saldo_ant = casa.obtener_saldo_anterior(registro.mes, registro.anio)
    
    total_a_pagar = float(registro.monto) + float(datos['extras']) + saldo_ant - float(registro.monto_pagado or 0)
    
    if total_a_pagar > 0.01:
        aplicar_pago_en_cascada(casa, total_a_pagar, current_user.username, registro.mes, registro.anio)
    else:
        registro.pagado = True
        registro.mensaje_enviado = True
        registro.cobrado_por = current_user.username
        registro.fecha_pago = obtener_marca_tiempo(registro.mes, registro.anio)
        if hasattr(registro, 'transaccion_id'):
            txn_id = f"TXN-{uuid.uuid4().hex[:8].upper()}"
            registro.transaccion_id = txn_id
            detalle_str = f"{txn_id}:{total_a_pagar}"
            actual = getattr(registro, 'detalle_pagos', None)
            registro.detalle_pagos = f"{actual}|{detalle_str}" if actual else detalle_str
    
    db.session.commit()
    return jsonify({"success": True})


@dashboard_bp.route("/sync-abonos", methods=["POST"])
@login_required
@admin_required
def sync_abonos():
    mes = request.form.get("mes", type=int)
    anio = request.form.get("anio", type=int)
    if not mes or not anio: return redirect(url_for('dashboard.index'))
    
    cierre = CierreMes.query.filter_by(mes=mes, anio=anio).first()
    if not cierre:
        db.session.add(CierreMes(mes=mes, anio=anio))
    
    for casa in Casa.query.all():
        datos_v = casa.obtener_gastos_mensuales(mes, anio)
        extras_v = float(datos_v.get("extras", 0))
        
        if not casa.activo and extras_v <= 0:
            continue
            
        abono_a_guardar = float(casa.precio_base or 0) if (casa.activo or extras_v > 0) else 0.0
            
        hist = AbonoHistorico.query.filter_by(casa_id=casa.id, mes=mes, anio=anio).first()
        if not hist:
            db.session.add(AbonoHistorico(casa_id=casa.id, mes=mes, anio=anio, monto=abono_a_guardar))
        else:
            hist.monto = abono_a_guardar
            
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
            if (not f.monto_pagado or float(f.monto_pagado) <= 0.01) and not getattr(f, 'mensaje_enviado', False):
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
    action = request.json.get("action")
    
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

    if action == 'undo' or (all_pagado and action != 'advance'):
        txns_to_revert = set()
        for h in historiales:
            if getattr(h, 'detalle_pagos', None):
                for p in h.detalle_pagos.split('|'):
                    if ':' in p:
                        txns_to_revert.add(p.split(':')[0])
            elif getattr(h, 'transaccion_id', None):
                txns_to_revert.add(h.transaccion_id)
                
        if txns_to_revert:
            for t_id in txns_to_revert:
                hermanos = AbonoHistorico.query.filter(
                    or_(
                        AbonoHistorico.transaccion_id == t_id,
                        AbonoHistorico.detalle_pagos.like(f"%{t_id}%")
                    )
                ).all()
                for hm in hermanos:
                    revertir_transaccion(hm, t_id)
        else:
            for h in historiales:
                revertir_transaccion(h, "VIEJO")

    elif action == 'advance' or not all_pagado:
        if not all_pagado and not all_enviado:
            for h in historiales:
                h.mensaje_enviado = True
                h.pagado = False
                
            grupo = casas_grupo[0].grupo
            telefono_repr = next((c.telefono for c in casas_grupo if c.telefono), None)
            
            if telefono_repr:
                casas_data = []
                total_grupo_mes = 0
                total_grupo_saldo_ant = 0
                
                for h in historiales:
                    c = h.casa
                    abono = float(h.monto)
                    extras = float(c.obtener_gastos_mensuales(mes, anio)['extras'])
                    saldo_ant = c.obtener_saldo_anterior(mes, anio)
                    total_grupo_mes += (abono + extras)
                    total_grupo_saldo_ant += saldo_ant
                    casas_data.append({'casa': c, 'abono': abono, 'extras': extras})
                
                texto_wa = generar_wa_grupo(grupo.nombre, casas_data, mes, anio, total_grupo_mes, total_grupo_saldo_ant)
                
                tel = re.sub(r'\D', '', telefono_repr)
                if len(tel) == 10: tel = "549" + tel
                url_wa = f"whatsapp://send?phone={tel}&text={urllib.parse.quote(texto_wa)}"

        else:
            txn_id = f"TXN-{uuid.uuid4().hex[:8].upper()}"
            for h in historiales:
                c = h.casa
                datos = c.obtener_gastos_mensuales(mes, anio)
                saldo_ant = c.obtener_saldo_anterior(mes, anio)
                total_a_pagar = float(h.monto) + float(datos['extras']) + saldo_ant - float(h.monto_pagado or 0)
                
                if total_a_pagar > 0.01:
                    aplicar_pago_en_cascada(c, total_a_pagar, current_user.username, mes, anio)
                else:
                    h.pagado = True
                    h.mensaje_enviado = True
                    h.cobrado_por = current_user.username
                    h.fecha_pago = obtener_marca_tiempo(mes, anio)
                    if hasattr(h, 'transaccion_id'):
                        h.transaccion_id = txn_id
                        detalle_str = f"{txn_id}:{total_a_pagar}"
                        actual = getattr(h, 'detalle_pagos', None)
                        h.detalle_pagos = f"{actual}|{detalle_str}" if actual else detalle_str

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
            aplicar_pago_en_cascada(d["hist"].casa, d["restante"] + sobrante_por_casa, current_user.username, mes, anio)
    else:
        plata_disponible = monto_ingresado
        for d in deudas:
            if plata_disponible <= 0.01:
                break
            if plata_disponible >= d["restante"]:
                aplicar_pago_en_cascada(d["hist"].casa, d["restante"], current_user.username, mes, anio)
                plata_disponible -= d["restante"]
            else:
                aplicar_pago_en_cascada(d["hist"].casa, plata_disponible, current_user.username, mes, anio)
                plata_disponible = 0

    db.session.commit()
    return jsonify({"success": True})


@dashboard_bp.route("/registrar-pago-especial/<int:id_historial>", methods=["POST"])
@login_required
@admin_required
def registrar_pago_especial(id_historial):
    registro = AbonoHistorico.query.get_or_404(id_historial)
    monto_ingresado = float(request.json.get("monto", 0))
    
    if monto_ingresado > 0:
        aplicar_pago_en_cascada(registro.casa, monto_ingresado, current_user.username, registro.mes, registro.anio)
        
    db.session.commit()
    return jsonify({"success": True})


@dashboard_bp.route("/planilla-impresion")
@login_required
@admin_required
def planilla_impresion():
    mes = int(request.args.get("mes", datetime.now().month))
    anio = int(request.args.get("anio", datetime.now().year))
    
    registro_congelado = CierreMes.query.filter_by(mes=mes, anio=anio).first()
    mes_congelado = True if registro_congelado else False

    casas_raw = Casa.query.all()
    historial_dict = {h.casa_id: h for h in AbonoHistorico.query.filter_by(mes=mes, anio=anio).all()}
    
    casas = []
    for c in casas_raw:
        datos_v = c.obtener_gastos_mensuales(mes, anio)
        if not c.activo and float(datos_v.get("extras", 0)) <= 0:
            continue
        casas.append(c)

    casas.sort(key=natural_sort_key)
    
    reporte_sueltas = []
    reporte_grupos = {}
    
    for casa in casas:
        datos = casa.obtener_gastos_mensuales(mes, anio)
        producto = float(datos.get("extras", 0))
        historial = historial_dict.get(casa.id)
        
        if historial:
            abono = float(historial.monto)
        else:
            abono = float(casa.precio_base or 0) if (casa.activo or producto > 0) else 0.0
            
        saldo_anterior = casa.obtener_saldo_anterior(mes, anio)
        total_a_pagar = abono + producto + saldo_anterior

        if not casa.activo and total_a_pagar <= 0.1:
            continue

        # --- LÓGICA DE TACHADO (Saber si ya pagó) ---
        monto_pagado = float(getattr(historial, 'monto_pagado', 0) or 0)
        esta_pagado = False
        if historial and getattr(historial, 'pagado', False) and (total_a_pagar - monto_pagado) <= 0.01:
            esta_pagado = True
        elif total_a_pagar <= 0.01 and historial and getattr(historial, 'pagado', False):
            esta_pagado = True

        detalle_prods = []
        for v in casa.visitas:
            if v.fecha.month == mes and v.fecha.year == anio:
                for vp in v.productos:
                    unidad = vp.product.unidad if vp.product.unidad else ""
                    extra_tag = " (Agregado)" if v.observaciones == "[EXTRA_MANUAL]" else ""
                    detalle_prods.append(f"{vp.cantidad}{unidad} {vp.product.nombre}{extra_tag}")
        
        texto_detalle = ", ".join(detalle_prods)
            
        item = {
            "cliente": casa.nombre_formateado(),
            "producto": producto,
            "detalle_productos": texto_detalle, 
            "abono": abono,
            "saldo_anterior": saldo_anterior,
            "total_a_pagar": total_a_pagar,
            "pagado": esta_pagado # <-- Nuevo dato para la planilla
        }

        if casa.grupo_id:
            if casa.grupo_id not in reporte_grupos:
                reporte_grupos[casa.grupo_id] = {
                    "nombre": casa.grupo.nombre,
                    "filas": [],
                    "total_grupo": 0.0,
                    "grupo_pagado": True # Asumimos True y lo bajamos si alguno debe
                }
            reporte_grupos[casa.grupo_id]["filas"].append(item)
            reporte_grupos[casa.grupo_id]["total_grupo"] += total_a_pagar
            if not esta_pagado:
                reporte_grupos[casa.grupo_id]["grupo_pagado"] = False
        else:
            reporte_sueltas.append(item)
        
    nombres_meses = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    nombre_mes = nombres_meses[mes - 1]

    return render_template("dashboard/planilla.html", 
                           reporte_sueltas=reporte_sueltas, 
                           reporte_grupos=list(reporte_grupos.values()), 
                           mes_nombre=nombre_mes, 
                           anio=anio)
@dashboard_bp.route("/api/totales")
@login_required
@admin_required
def api_totales():
    mes = int(request.args.get("mes", datetime.now().month))
    anio = int(request.args.get("anio", datetime.now().year))
    
    registro_congelado = CierreMes.query.filter_by(mes=mes, anio=anio).first()
    mes_congelado = True if registro_congelado else False

    query_casas = Casa.query.options(
        selectinload(Casa.historial_abonos),
        selectinload(Casa.visitas).selectinload(Visit.productos),
        selectinload(Casa.visitas).joinedload(Visit.promo)
    )

    casas_raw = query_casas.all()
    historial_dict = {h.casa_id: h for h in AbonoHistorico.query.filter_by(mes=mes, anio=anio).all()}

    total_abono = 0.0
    total_extras = 0.0
    total_recaudado = 0.0 
    total_deuda_anterior = 0.0 

    for casa in casas_raw:
        datos = casa.obtener_gastos_mensuales(mes, anio)
        extras_v = float(datos.get("extras", 0))
        
        if not casa.activo and extras_v <= 0:
            continue
            
        saldo_anterior = casa.obtener_saldo_anterior(mes, anio)
        historial = historial_dict.get(casa.id)
        
        # AHORA RESPETA CUALQUIER HISTORIAL GUARDADO
        if historial:
            abono_mes = float(historial.monto)
        else:
            abono_mes = float(casa.precio_base or 0) if (casa.activo or extras_v > 0) else 0.0
        
        if not casa.activo and (abono_mes + extras_v + saldo_anterior) <= 0.1:
            continue
            
        total_mes = abono_mes + extras_v
        
        if saldo_anterior > 0:
            total_deuda_anterior += saldo_anterior

        esta_pagado = getattr(historial, 'pagado', False) if historial else False
        monto_pagado = float(getattr(historial, 'monto_pagado', 0) or 0)

        total_abono += abono_mes
        total_extras += extras_v
        
        if esta_pagado and monto_pagado == 0:
            total_recaudado += total_mes
        else:
            total_recaudado += monto_pagado

    total_general = total_abono + total_extras + total_deuda_anterior
    return jsonify({
        "kpi_deuda": f"${format_money(total_deuda_anterior)}",
        "kpi_recaudado": f"${format_money(total_recaudado)}",
        "kpi_pendiente": f"${format_money(total_general - total_recaudado)}",
        "kpi_total": f"${format_money(total_general)}"
    })