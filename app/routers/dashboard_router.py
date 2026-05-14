from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.utils import nombre_mes, MESES_LARGO, registrar_auditoria
from flask_login import login_required, current_user
from app.decorators import admin_required
from app import db
from app.models import Casa, Country, Barrio
from app.models.abono_historico import AbonoHistorico
from app.models.cierre_mes import CierreMes
from app.models.visit import Visit
from app.models.visit_product import VisitProduct
from datetime import datetime, timedelta, timezone
import re
import urllib.parse
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import func, extract, and_, or_, text
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

def generar_wa_chat_url(casa):
    num = limpiar_telefono(casa.telefono)
    if not num:
        return None
    return f"whatsapp://send?phone={num}"

def obtener_marca_tiempo(mes_contexto=None, anio_contexto=None):
    """Siempre devuelve la fecha/hora real actual en zona horaria Argentina (UTC-3)."""
    tz_ar = timezone(timedelta(hours=-3))
    ahora_ar = datetime.now(tz_ar)
    # Devolvemos sin tzinfo para compatibilidad con el resto del ORM (naive datetime)
    return ahora_ar.replace(tzinfo=None)

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

def generar_wa_individual(casa, mes, anio, abono_mes, extras, saldo_anterior_visual, pagos_en_este_dashboard, pt=None):
    from app.models.plantilla_mensaje import PlantillaMensaje, renderizar_template
    if pt is None:
        pt = PlantillaMensaje.get_activa()

    nombre_wa = casa.nombre_cliente if casa.nombre_cliente else get_nombre_limpio(casa)
    saludo = obtener_saludo_tiempo(nombre_wa)
    saldo_favor = abs(saldo_anterior_visual) if saldo_anterior_visual < -0.01 else 0.0
    saldo_deuda = saldo_anterior_visual if saldo_anterior_visual > 0.01 else 0.0
    total_final = abono_mes + extras + saldo_anterior_visual - pagos_en_este_dashboard

    if total_final <= 0.01:
        resumen_total = "*-- CUENTA AL DÍA --*"
    else:
        resumen_total = f"*-- TOTAL A PAGAR: ${format_money(total_final)} --*"

    prods = obtener_detalle_productos(casa, mes, anio)
    detalle_productos = '\n'.join(f'* {p}' for p in prods)

    variables = {
        'saludo':            (saludo,                          None),
        'resumen_total':     (resumen_total,                   None),
        'mantenimiento':     (format_money(abono_mes),         None),
        'extras':            (format_money(extras),            extras),
        'detalle_productos': (detalle_productos,               len(prods)),
        'saldo_anterior':    (format_money(saldo_deuda),       saldo_deuda),
        'saldo_favor':       (format_money(saldo_favor),       saldo_favor),
        'pagado':            (format_money(pagos_en_este_dashboard), pagos_en_este_dashboard),
    }
    return renderizar_template(pt.get_template_individual(), variables)

def generar_wa_grupo(grupo_nombre, casas_data, mes, anio, total_grupo_mes, total_grupo_saldo_ant_visual, total_pagos_dashboard, saldo_a_favor=0.0, pt=None):
    from app.models.plantilla_mensaje import PlantillaMensaje, renderizar_template
    if pt is None:
        pt = PlantillaMensaje.get_activa()

    saludo = obtener_saludo_tiempo(grupo_nombre)
    total_final = total_grupo_mes + total_grupo_saldo_ant_visual - total_pagos_dashboard - saldo_a_favor

    casas_visibles = [c for c in casas_data if not (c.get('pausado', False) and (c['abono'] + c['extras']) == 0)]
    cant = len(casas_visibles)

    if total_final <= 0.01:
        resumen_total = "*-- CUENTAS AL DÍA --*"
    else:
        resumen_total = f"*-- TOTAL A PAGAR: ${format_money(total_final)} --*"

    lista_lines = []
    for c in casas_visibles:
        casa_obj = c['casa']
        nombre_casa = get_nombre_limpio(casa_obj)
        abono = c['abono']
        extras = c['extras']
        saldo_ant = c.get('saldo_anterior', 0.0)
        total_c = abono + extras
        linea = f"• *{nombre_casa}:* Abono ${format_money(abono)} + Prod. ${format_money(extras)} = *${format_money(total_c)}*"
        if saldo_ant < -0.1:
            linea += f" _(saldo a favor: ${format_money(abs(saldo_ant))})_"
        if extras > 0:
            prods = obtener_detalle_productos(casa_obj, mes, anio)
            if prods:
                linea += "\n  _(" + ", ".join(prods) + ")_"
        lista_lines.append(linea)

    variables = {
        'saludo':          (saludo,                                str(cant)),
        'cant':            (str(cant),                             None),
        'resumen_total':   (resumen_total,                         None),
        'lista_casas':     ('\n'.join(lista_lines),                None),
        'saldo_anterior':  (format_money(total_grupo_saldo_ant_visual), total_grupo_saldo_ant_visual),
        'pagado':          (format_money(total_pagos_dashboard),   total_pagos_dashboard),
        'saldo_favor':     (format_money(saldo_a_favor),           saldo_a_favor),
    }
    return renderizar_template(pt.get_template_grupo(), variables)

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
        total_mes = float(datos['total'])
        
        if h.monto_pagado < (total_mes - 0.01):
            h.pagado = False
            
        if h.monto_pagado <= 0.01:
            h.monto_pagado = 0.0
            h.fecha_pago = None
            h.cobrado_por = None
            h.mensaje_enviado = False
            h.doble_instancia_enviada = False
    else:
        h.pagado = False
        h.mensaje_enviado = False
        h.doble_instancia_enviada = False
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
    
    # Calcular el mes/anio mínimo a considerar según fecha_creacion de la casa
    _fa = None
    if casa.fecha_creacion:
        from datetime import datetime as _dt
        _fa_raw = casa.fecha_creacion
        _fa = _fa_raw.date() if isinstance(_fa_raw, _dt) else _fa_raw

    for h in historiales:
        if plata <= 0.01:
            break
        # Saltar meses anteriores a la fecha de alta del cliente (mismo criterio que obtener_saldo_anterior)
        if _fa and (h.anio, h.mes) < (_fa.year, _fa.month):
            continue
        if not h.pagado:
            datos = casa.obtener_gastos_mensuales(h.mes, h.anio)
            total_mes = float(datos['total'])
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

def _casa_pausada_en_mes(casa, mes, anio, extras=0.0):
    """True si la casa tiene una pausa que cubre el mes dado.

    - Soporta pausas con 'hasta' (rango cerrado).
    - Funciona aunque la casa ya esté reanudada (no depende del flag pausado).
    - Si la pausa inicia en este mismo mes y la casa tiene extras (fue visitada),
      la pausa aplica recién desde el mes siguiente para cobrar ese mes.
    """
    mes_actual = (anio, mes)
    for p in getattr(casa, 'historial_pausas', []):
        inicio = (p.desde.year, p.desde.month)
        fin = (p.hasta.year, p.hasta.month) if p.hasta else None
        if inicio <= mes_actual and (fin is None or fin >= mes_actual):
            return True
    return False

def _saldo_grupo_para_mes(grupo, mes, anio):
    """Retorna el saldo_a_favor del grupo solo si aplica al mes consultado (mes posterior al de origen)."""
    saldo = float(grupo.saldo_a_favor or 0)
    if saldo <= 0.01:
        return 0.0
    sm, sy = grupo.saldo_desde_mes, grupo.saldo_desde_anio
    if sm and sy and (anio, mes) > (sy, sm):
        return saldo
    return 0.0

# ==========================================
# OPTIMIZACIÓN: SALDO ANTERIOR EN BATCH
# ==========================================

def calcular_saldos_anteriores_batch(mes, anio):
    """
    Calcula el saldo anterior de todas las casas en una sola query SQL.
    Reemplaza 200 llamadas individuales a obtener_saldo_anterior() en index().
    Limitación: no recalcula pausas añadidas retroactivamente a meses ya cerrados.
    """
    sql = text("""
        SELECT
            ah.casa_id,
            SUM(
                CASE WHEN EXISTS (
                    SELECT 1 FROM pausas p
                    WHERE p.casa_id = ah.casa_id
                      AND p.desde <= make_date(ah.anio, ah.mes, 1)
                      AND (p.hasta IS NULL OR p.hasta >= make_date(ah.anio, ah.mes, 1))
                ) THEN 0 ELSE ah.monto END
                + COALESCE(prod_ext.extras, 0)
                + COALESCE(promo_ext.extras, 0)
                - COALESCE(ah.monto_pagado, 0)
            ) AS saldo
        FROM abonos_historicos ah
        JOIN casas c ON c.id = ah.casa_id
        LEFT JOIN (
            SELECT v.casa_id,
                   EXTRACT(YEAR  FROM v.fecha)::int AS anio,
                   EXTRACT(MONTH FROM v.fecha)::int AS mes,
                   SUM(vp.cantidad * COALESCE(vp.precio_unitario, p.precio)) AS extras
            FROM visits v
            JOIN visit_products vp ON vp.visit_id = v.id
            JOIN products       p  ON p.id = vp.product_id
            GROUP BY v.casa_id,
                     EXTRACT(YEAR  FROM v.fecha),
                     EXTRACT(MONTH FROM v.fecha)
        ) prod_ext ON prod_ext.casa_id = ah.casa_id
                  AND prod_ext.anio     = ah.anio
                  AND prod_ext.mes      = ah.mes
        LEFT JOIN (
            SELECT v.casa_id,
                   EXTRACT(YEAR  FROM v.fecha)::int AS anio,
                   EXTRACT(MONTH FROM v.fecha)::int AS mes,
                   SUM(pr.precio) AS extras
            FROM visits v
            JOIN promos pr ON pr.id = v.promo_id
            GROUP BY v.casa_id,
                     EXTRACT(YEAR  FROM v.fecha),
                     EXTRACT(MONTH FROM v.fecha)
        ) promo_ext ON promo_ext.casa_id = ah.casa_id
                   AND promo_ext.anio     = ah.anio
                   AND promo_ext.mes      = ah.mes
        WHERE NOT (ah.pagado = TRUE AND COALESCE(ah.monto_pagado, 0) = 0)
          AND (ah.anio < :anio OR (ah.anio = :anio AND ah.mes < :mes))
          AND (
              c.fecha_creacion IS NULL
              OR ah.anio > EXTRACT(YEAR  FROM c.fecha_creacion)
              OR (ah.anio  = EXTRACT(YEAR  FROM c.fecha_creacion)
                  AND ah.mes >= EXTRACT(MONTH FROM c.fecha_creacion))
          )
        GROUP BY ah.casa_id
    """)
    try:
        rows = db.session.execute(sql, {"mes": mes, "anio": anio})
        return {row.casa_id: float(row.saldo or 0) for row in rows}
    except Exception:
        return {}

# ==========================================
# RUTAS DEL DASHBOARD
# ==========================================

@dashboard_bp.route("/")
@login_required
@admin_required
def index():
    _now = datetime.now()
    mes_actual = _now.month
    anio_actual = _now.year
    _default_mes  = 12 if mes_actual == 1 else mes_actual - 1
    _default_anio = anio_actual - 1 if mes_actual == 1 else anio_actual

    try:
        mes = int(request.args.get("mes", _default_mes))
        anio = int(request.args.get("anio", _default_anio))
    except ValueError:
        mes = _default_mes
        anio = _default_anio

    registro_congelado = CierreMes.query.filter_by(mes=mes, anio=anio).first()
    mes_congelado = True if registro_congelado else False

    query_casas = Casa.query.options(
        joinedload(Casa.country),
        joinedload(Casa.barrio),
        joinedload(Casa.grupo),
        selectinload(Casa.historial_pausas),
        selectinload(Casa.visitas).selectinload(Visit.productos).joinedload(VisitProduct.product),
        selectinload(Casa.visitas).joinedload(Visit.promo)
    )

    casas_raw = query_casas.all()
    historial_dict = {h.casa_id: h for h in AbonoHistorico.query.filter_by(mes=mes, anio=anio).all()}
    saldos_batch = calcular_saldos_anteriores_batch(mes, anio)

    # Detecta pagos en cascada: txn_id del mes actual que también aparece en un mes POSTERIOR
    _cascade_txns = set()
    _txn_ids = {h.transaccion_id for h in historial_dict.values() if h and h.transaccion_id}
    if _txn_ids:
        _cascade_rows = AbonoHistorico.query.filter(
            AbonoHistorico.transaccion_id.in_(_txn_ids),
            or_(AbonoHistorico.anio > anio, and_(AbonoHistorico.anio == anio, AbonoHistorico.mes > mes))
        ).with_entities(AbonoHistorico.casa_id, AbonoHistorico.transaccion_id).all()
        _cascade_txns = {(r.casa_id, r.transaccion_id) for r in _cascade_rows}

    casas = []
    _cache_datos = {}
    for c in casas_raw:
        if c.fecha_creacion:
            if c.fecha_creacion.year > anio or (c.fecha_creacion.year == anio and c.fecha_creacion.month > mes):
                continue

        hist_v = historial_dict.get(c.id)
        datos_v = c.obtener_gastos_mensuales(mes, anio, hist=hist_v)
        extras_v = float(datos_v.get("extras", 0))

        if hist_v:
            ab_v = float(hist_v.monto)
        else:
            ab_v = float(c.precio_base or 0) if (c.activo or extras_v > 0) else 0.0

        saldo_anterior_v = saldos_batch.get(c.id, 0.0) if saldos_batch else c.obtener_saldo_anterior(mes, anio)

        if not c.activo and (ab_v + extras_v + saldo_anterior_v) <= 0.1:
            continue

        _cache_datos[c.id] = {"datos": datos_v, "saldo_anterior": saldo_anterior_v}
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
        _cd = _cache_datos[casa.id]
        datos = _cd["datos"]
        extras = float(datos.get("extras", 0))
        saldo_anterior_real = _cd["saldo_anterior"]
        historial = historial_dict.get(casa.id)

        pausado_mes = _casa_pausada_en_mes(casa, mes, anio, extras)
        if pausado_mes:
            abono_mes = 0.0
        elif historial:
            abono_mes = float(historial.monto)
        else:
            abono_mes = float(casa.precio_base or 0) if (casa.activo or extras > 0) else 0.0

        total_mes = abono_mes + extras

        # --- LÓGICA VISUAL DE FOTO DEL MES ---
        # Con pagos en cascada, obtener_saldo_anterior() ya refleja correctamente
        # todos los abonos parciales aplicados a meses anteriores.
        # NO sumamos pago_deudas_este_mes porque eso duplicaría deudas ya saldadas.
        saldo_anterior_visual = saldo_anterior_real
        monto_pagado_mes_actual = float(getattr(historial, 'monto_pagado', 0) or 0)

        # Si el monto_pagado fue aplicado por cascade de un mes anterior (fecha_pago < mes actual),
        # tratarlo como crédito en saldo_anterior, no como pago hecho en este período.
        fp = getattr(historial, 'fecha_pago', None) if historial else None
        if monto_pagado_mes_actual > 0.01 and fp and (fp.year, fp.month) < (anio, mes):
            saldo_anterior_visual = saldo_anterior_real - monto_pagado_mes_actual
            pagos_en_este_dashboard = 0.0
        else:
            pagos_en_este_dashboard = monto_pagado_mes_actual

        saldo_restante = (total_mes + saldo_anterior_visual) - pagos_en_este_dashboard
        
        esta_pagado = getattr(historial, 'pagado', False) if historial else False
        mensaje_enviado = getattr(historial, 'mensaje_enviado', False) if historial else False
        doble_instancia_enviada = getattr(historial, 'doble_instancia_enviada', False) if historial else False

        if saldo_anterior_visual > 0:
            total_deuda_anterior += saldo_anterior_visual

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
                historial.detalle_pagos = f"{txn_id}:{abono_mes + extras}"
                hubo_cambios = True

        # Estado para filtros: pagado > notificado > saldar > pendiente
        # "saldar" = solo quienes hicieron un pago parcial
        _pago_parcial_flag = pagos_en_este_dashboard > 0 and not esta_pagado
        if esta_pagado:
            estado_item = "pagado"
        elif mensaje_enviado:
            estado_item = "notificado"
        elif _pago_parcial_flag:
            estado_item = "saldar"
        else:
            estado_item = "pendiente"

        _txn = historial.transaccion_id if historial else None
        item_casa = {
            "id_historial": historial.id if historial else None,
            "historial_obj": historial,
            "casa": casa,
            "abono": abono_mes,
            "extras": extras,
            "detalle_productos": obtener_detalle_productos(casa, mes, anio) if extras > 0 else [],
            "total_mes": total_mes,
            "saldo_anterior": saldo_anterior_visual,
            "saldo_restante": saldo_restante,
            "monto_pagado": pagos_en_este_dashboard,
            "pagado": esta_pagado,
            "mensaje_enviado": mensaje_enviado,
            "doble_instancia_enviada": doble_instancia_enviada,
            "pagos_en_este_dashboard": pagos_en_este_dashboard,
            "estado": estado_item,
            "tiene_telefono": bool(casa.telefono),
            "pausado": pausado_mes,
            "pagado_atrasado": bool(_txn and (casa.id, _txn) in _cascade_txns)
        }

        if casa.grupo_id:
            if casa.grupo_id not in reporte_grupos:
                reporte_grupos[casa.grupo_id] = {
                    "grupo_id": casa.grupo_id,
                    "nombre": casa.grupo.nombre,
                    "nombre_display": casa.grupo.nombre_display,
                    "casas": [],
                    "total_mes": 0.0, "saldo_anterior": 0.0, "saldo_restante": 0.0,
                    "monto_pagado": 0.0, "telefono": casa.telefono,
                    "saldo_a_favor": _saldo_grupo_para_mes(casa.grupo, mes, anio)
                }
            g = reporte_grupos[casa.grupo_id]
            g["casas"].append(item_casa)
            g["total_mes"] += total_mes
            g["saldo_anterior"] += saldo_anterior_visual
            g["saldo_restante"] += saldo_restante
            g["monto_pagado"] += pagos_en_este_dashboard
        else:
            reporte_sueltas.append(item_casa)

        total_clientes += 1
        total_abono += abono_mes
        total_extras += extras
        total_recaudado += pagos_en_este_dashboard

    total_general = total_abono + total_extras + total_deuda_anterior

    for g_id, g in reporte_grupos.items():
        if mes_congelado and g["saldo_restante"] <= 0.01:
            g["pagado"] = True
            g["mensaje_enviado"] = True
            g["doble_instancia_enviada"] = False
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
            g["doble_instancia_enviada"] = all(c.get("doble_instancia_enviada", False) for c in g["casas"])

        # Estado del grupo para filtros
        if g["pagado"]:
            g["estado"] = "pagado"
        elif g.get("mensaje_enviado"):
            g["estado"] = "notificado"
        elif any(c.get("estado") == "saldar" for c in g["casas"]):
            g["estado"] = "saldar"
        else:
            g["estado"] = "pendiente"

        pass  # url_wa generada on-demand via /api/wa-url-grupo/<grupo_id>

    if hubo_cambios:
        db.session.commit()

    # KPI Falta Saldar
    kpi_saldar_count = sum(1 for it in reporte_sueltas if it.get("estado") == "saldar")
    kpi_saldar_monto = sum(it.get("saldo_restante", 0) for it in reporte_sueltas if it.get("estado") == "saldar")
    for g in reporte_grupos.values():
        if g.get("estado") == "saldar":
            kpi_saldar_count += 1
            kpi_saldar_monto += g.get("saldo_restante", 0)

    return render_template(
        "dashboard/index.html",
        reporte_sueltas=reporte_sueltas,
        reporte_grupos=list(reporte_grupos.values()),
        mes=mes, anio=anio, mes_congelado=mes_congelado,
        mes_actual=mes_actual, anio_actual=anio_actual,
        kpi_clientes=total_clientes, kpi_abono=total_abono, kpi_extras=total_extras,
        kpi_deuda=total_deuda_anterior, kpi_recaudado=total_recaudado,
        kpi_pendiente=total_general - total_recaudado, kpi_total=total_general,
        kpi_saldar_count=kpi_saldar_count, kpi_saldar_monto=kpi_saldar_monto
    )

@dashboard_bp.route("/marcar-mensaje/<int:id>", methods=["POST"])
@login_required
@admin_required
def marcar_mensaje(id):
    registro = AbonoHistorico.query.get_or_404(id)
    registro.mensaje_enviado = True
    db.session.commit()
    return jsonify({"success": True})


@dashboard_bp.route("/marcar-doble-instancia/<int:id>", methods=["POST"])
@login_required
@admin_required
def marcar_doble_instancia(id):
    registro = AbonoHistorico.query.get_or_404(id)
    registro.doble_instancia_enviada = True
    db.session.commit()
    return jsonify({"success": True})


@dashboard_bp.route("/marcar-doble-instancia-grupo/<int:grupo_id>", methods=["POST"])
@login_required
@admin_required
def marcar_doble_instancia_grupo(grupo_id):
    data = request.get_json(silent=True) or {}
    mes = data.get("mes")
    anio = data.get("anio")
    historiales = AbonoHistorico.query.filter(
        AbonoHistorico.casa_id.in_(
            db.session.query(Casa.id).filter_by(grupo_id=grupo_id)
        ),
        AbonoHistorico.mes == mes,
        AbonoHistorico.anio == anio
    ).all()
    for h in historiales:
        h.doble_instancia_enviada = True
    db.session.commit()
    return jsonify({"success": True})


@dashboard_bp.route("/api/wa-url-recordatorio-grupo/<int:grupo_id>")
@login_required
@admin_required
def api_wa_url_recordatorio_grupo(grupo_id):
    mes = request.args.get("mes", type=int)
    anio = request.args.get("anio", type=int)
    if not mes or not anio:
        return jsonify({"url": None})
    from app.models.grupo import GrupoCliente
    grupo = GrupoCliente.query.get_or_404(grupo_id)
    casas_grupo = Casa.query.filter_by(grupo_id=grupo_id).options(
        selectinload(Casa.historial_abonos),
        selectinload(Casa.historial_pausas),
        selectinload(Casa.visitas).selectinload(Visit.productos).joinedload(VisitProduct.product),
        selectinload(Casa.visitas).joinedload(Visit.promo)
    ).all()
    telefono_repr = next((c.telefono for c in casas_grupo if c.telefono), None)
    if not telefono_repr:
        return jsonify({"url": None})
    hist_dict = {h.casa_id: h for h in AbonoHistorico.query.filter(
        AbonoHistorico.casa_id.in_([c.id for c in casas_grupo]),
        AbonoHistorico.mes == mes, AbonoHistorico.anio == anio
    ).all()}
    total_deuda = 0.0
    for c in casas_grupo:
        h = hist_dict.get(c.id)
        datos = c.obtener_gastos_mensuales(mes, anio, hist=h)
        extras = float(datos.get("extras", 0))
        pausado = _casa_pausada_en_mes(c, mes, anio, extras)
        abono = 0.0 if pausado else (float(h.monto) if h and float(h.monto) > 0 else float(c.precio_base or 0))
        saldo = c.obtener_saldo_anterior(mes, anio)
        pagos = float(h.monto_pagado or 0) if h else 0.0
        total_deuda += abono + extras + saldo - pagos
    saldo_a_favor = _saldo_grupo_para_mes(grupo, mes, anio)
    total_deuda = max(0.0, total_deuda - saldo_a_favor)
    saludo = obtener_saludo_tiempo(grupo.nombre)
    from app.models.plantilla_mensaje import PlantillaMensaje, renderizar_template
    pt = PlantillaMensaje.get_activa()
    variables = {
        'saludo': (saludo, None),
        'deuda':  (format_money(total_deuda), None),
        'mes':    (MESES_LARGO[mes - 1], None),
        'anio':   (str(anio), None),
    }
    texto = renderizar_template(pt.get_template_recordatorio(), variables)
    tel = re.sub(r'\D', '', telefono_repr)
    if len(tel) == 10:
        tel = "549" + tel
    return jsonify({"url": f"whatsapp://send?phone={tel}&text={urllib.parse.quote(texto)}"})


@dashboard_bp.route("/api/wa-url-recordatorio/<int:id_historial>")
@login_required
@admin_required
def api_wa_url_recordatorio(id_historial):
    hist = AbonoHistorico.query.get_or_404(id_historial)
    casa = Casa.query.options(
        selectinload(Casa.historial_abonos),
        selectinload(Casa.historial_pausas),
        selectinload(Casa.visitas).selectinload(Visit.productos).joinedload(VisitProduct.product),
        selectinload(Casa.visitas).joinedload(Visit.promo)
    ).get(hist.casa_id)
    if not casa or not casa.telefono:
        return jsonify({"url": None})
    mes, anio = hist.mes, hist.anio
    saldo_anterior = casa.obtener_saldo_anterior(mes, anio)
    datos = casa.obtener_gastos_mensuales(mes, anio, hist=hist)
    extras = float(datos.get("extras", 0))
    pausado = _casa_pausada_en_mes(casa, mes, anio, extras)
    abono_mes = 0.0 if pausado else (float(hist.monto) if float(hist.monto) > 0 else float(casa.precio_base or 0))
    pagos = float(hist.monto_pagado or 0)
    deuda = abono_mes + extras + saldo_anterior - pagos
    nombre_wa = casa.nombre_cliente if casa.nombre_cliente else get_nombre_limpio(casa)
    saludo = obtener_saludo_tiempo(nombre_wa)
    from app.models.plantilla_mensaje import PlantillaMensaje, renderizar_template
    pt = PlantillaMensaje.get_activa()
    variables = {
        'saludo': (saludo, None),
        'deuda':  (format_money(deuda), None),
        'mes':    (MESES_LARGO[mes - 1], None),
        'anio':   (str(anio), None),
    }
    texto = renderizar_template(pt.get_template_recordatorio(), variables)
    num_tel = limpiar_telefono(casa.telefono)
    return jsonify({"url": f"whatsapp://send?phone={num_tel}&text={urllib.parse.quote(texto)}"})


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
    wa_chat_url = None

    if action == 'undo' or (pagado and action != 'advance'):
        # --- AUDITORÍA: deshacer pago ---
        casa_undo = registro.casa
        mes_nombre_undo = nombre_mes(registro.mes)
        registrar_auditoria(
            current_user.username,
            'DESHACER_PAGO',
            f"{casa_undo.nombre_formateado()} — {mes_nombre_undo} {registro.anio}"
        )

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
                # obtener_saldo_anterior ya refleja correctamente todos los pagos en cascada
                saldo_anterior_visual = casa.obtener_saldo_anterior(registro.mes, registro.anio)
                pagos_en_este_dashboard = float(registro.monto_pagado or 0)

                texto_wa = generar_wa_individual(casa, registro.mes, registro.anio, float(registro.monto), float(datos['extras']), saldo_anterior_visual, pagos_en_este_dashboard)
                url_wa = f"whatsapp://send?phone={limpiar_telefono(casa.telefono)}&text={urllib.parse.quote(texto_wa)}"
        else:
            casa = registro.casa
            datos = casa.obtener_gastos_mensuales(registro.mes, registro.anio)
            saldo_ant = casa.obtener_saldo_anterior(registro.mes, registro.anio)
            total_a_pagar = float(datos['total']) + saldo_ant - float(registro.monto_pagado or 0)

            # --- AUDITORÍA: marcar pagado ---
            mes_nombre_pago = nombre_mes(registro.mes)
            registrar_auditoria(
                current_user.username,
                'PAGO',
                f"{casa.nombre_formateado()} — {mes_nombre_pago} {registro.anio} — ${format_money(total_a_pagar)}"
            )

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

            wa_chat_url = generar_wa_chat_url(casa)

    db.session.commit()
    return jsonify({"success": True, "url_wa": url_wa, "wa_chat_url": wa_chat_url})

@dashboard_bp.route("/marcar-pagado-directo/<int:id>", methods=["POST"])
@login_required
@admin_required
def marcar_pagado_directo(id):
    registro = AbonoHistorico.query.get_or_404(id)
    casa = registro.casa
    datos = casa.obtener_gastos_mensuales(registro.mes, registro.anio)
    saldo_ant = casa.obtener_saldo_anterior(registro.mes, registro.anio)

    total_a_pagar = float(datos['total']) + saldo_ant - float(registro.monto_pagado or 0)

    # --- AUDITORÍA ---
    mes_nombre_d = nombre_mes(registro.mes)
    registrar_auditoria(
        current_user.username,
        'PAGO',
        f"{casa.nombre_formateado()} — {mes_nombre_d} {registro.anio} — ${format_money(total_a_pagar)}"
    )

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
    return jsonify({"success": True, "wa_chat_url": generar_wa_chat_url(casa)})


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

    casas_sync = Casa.query.options(
        selectinload(Casa.historial_pausas),
        selectinload(Casa.visitas).selectinload(Visit.productos).joinedload(VisitProduct.product),
        selectinload(Casa.visitas).joinedload(Visit.promo)
    ).all()
    hist_sync_dict = {h.casa_id: h for h in AbonoHistorico.query.filter_by(mes=mes, anio=anio).all()}

    for casa in casas_sync:
        hist = hist_sync_dict.get(casa.id)
        datos_v = casa.obtener_gastos_mensuales(mes, anio, hist=hist)
        extras_v = float(datos_v.get("extras", 0))

        if not casa.activo and extras_v <= 0:
            continue

        if _casa_pausada_en_mes(casa, mes, anio, extras_v):
            abono_a_guardar = 0.0
        else:
            abono_a_guardar = float(casa.precio_base or 0) if (casa.activo or extras_v > 0) else 0.0
        if not hist:
            db.session.add(AbonoHistorico(casa_id=casa.id, mes=mes, anio=anio, monto=abono_a_guardar))
        else:
            if not getattr(hist, 'pagado', False) and float(hist.monto_pagado or 0) == 0 and float(hist.monto or 0) != 0:
                hist.monto = abono_a_guardar

    mes_nombre_s = nombre_mes(mes)
    registrar_auditoria(current_user.username, 'CERRAR_MES', f"{mes_nombre_s} {anio}")
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
        mes_nombre_u = nombre_mes(mes)
        registrar_auditoria(current_user.username, 'ABRIR_MES', f"{mes_nombre_u} {anio}")
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
    
    casas_grupo = Casa.query.filter_by(grupo_id=grupo_id).options(
        joinedload(Casa.grupo),
        selectinload(Casa.historial_abonos),
        selectinload(Casa.historial_pausas),
        selectinload(Casa.visitas).selectinload(Visit.productos).joinedload(VisitProduct.product),
        selectinload(Casa.visitas).joinedload(Visit.promo)
    ).all()
    historiales = AbonoHistorico.query.filter(
        AbonoHistorico.casa_id.in_([c.id for c in casas_grupo]),
        AbonoHistorico.mes == mes,
        AbonoHistorico.anio == anio
    ).all()

    if not historiales:
        return jsonify({"success": False, "message": "Sin historiales para este período. Cerrá el mes primero."})

    # Usar len() > 0 para evitar que all([]) = True engañe la lógica de estado
    all_pagado  = len(historiales) > 0 and all(h.pagado for h in historiales)
    all_enviado = len(historiales) > 0 and all(h.mensaje_enviado for h in historiales)
    url_wa = None
    wa_chat_url = None

    if action == 'undo':
        # ── DESHACER PAGO ────────────────────────────────────────────
        from app.models.grupo import GrupoCliente
        grupo_undo = GrupoCliente.query.get(grupo_id)
        if grupo_undo:
            grupo_undo.saldo_a_favor = 0.0
        if casas_grupo:
            grupo_obj_aud = casas_grupo[0].grupo
            mes_nombre_gu = nombre_mes(mes)
            registrar_auditoria(
                current_user.username,
                'DESHACER_PAGO',
                f"Grupo {grupo_obj_aud.nombre if grupo_obj_aud else grupo_id} — {mes_nombre_gu} {anio}"
            )

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

    elif action == 'advance':
        if all_pagado:
            # Ya están todos pagados, nada que hacer
            pass

        elif all_enviado:
            # ── NOTIFICADO → PAGADO ──────────────────────────────────
            if casas_grupo:
                grupo_obj_p = casas_grupo[0].grupo
                mes_nombre_gp = nombre_mes(mes)
                registrar_auditoria(
                    current_user.username,
                    'PAGO',
                    f"Grupo {grupo_obj_p.nombre if grupo_obj_p else grupo_id} — {mes_nombre_gp} {anio}"
                )

            txn_id = f"TXN-{uuid.uuid4().hex[:8].upper()}"
            for h in historiales:
                c = h.casa
                datos = c.obtener_gastos_mensuales(mes, anio)
                saldo_ant = c.obtener_saldo_anterior(mes, anio)
                total_a_pagar = float(datos['total']) + saldo_ant - float(h.monto_pagado or 0)

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

            wa_chat_url = next((generar_wa_chat_url(c) for c in casas_grupo if c.telefono), None)

        else:
            # ── PENDIENTE → NOTIFICADO ───────────────────────────────
            for h in historiales:
                h.mensaje_enviado = True
                h.pagado = False

            grupo = casas_grupo[0].grupo
            telefono_repr = next((c.telefono for c in casas_grupo if c.telefono), None)

            if telefono_repr:
                casas_data = []
                total_grupo_mes = 0
                total_grupo_saldo_ant_visual = 0
                total_pagos_dashboard = 0

                for h in historiales:
                    c = h.casa
                    abono = float(h.monto)
                    extras = float(c.obtener_gastos_mensuales(mes, anio)['extras'])
                    saldo_ant = c.obtener_saldo_anterior(mes, anio)

                    total_grupo_mes += (abono + extras)
                    total_grupo_saldo_ant_visual += saldo_ant
                    total_pagos_dashboard += float(h.monto_pagado or 0)

                    casas_data.append({'casa': c, 'abono': abono, 'extras': extras, 'saldo_anterior': saldo_ant, 'pausado': _casa_pausada_en_mes(c, mes, anio, extras)})

                saldo_a_favor_grupo = _saldo_grupo_para_mes(grupo, mes, anio)
                texto_wa = generar_wa_grupo(grupo.nombre, casas_data, mes, anio, total_grupo_mes, total_grupo_saldo_ant_visual, total_pagos_dashboard, saldo_a_favor_grupo)

                tel = re.sub(r'\D', '', telefono_repr)
                if len(tel) == 10: tel = "549" + tel
                url_wa = f"whatsapp://send?phone={tel}&text={urllib.parse.quote(texto_wa)}"

    db.session.commit()
    return jsonify({"success": True, "url_wa": url_wa, "wa_chat_url": wa_chat_url})

@dashboard_bp.route("/registrar-pago-grupo/<int:grupo_id>", methods=["POST"])
@login_required
@admin_required
def registrar_pago_grupo(grupo_id):
    mes = request.json.get("mes")
    anio = request.json.get("anio")
    monto_ingresado = float(request.json.get("monto", 0))
    monto_usd = request.json.get("monto_usd")
    cotizacion_usd = request.json.get("cotizacion_usd")

    from app.models.grupo import GrupoCliente
    casas_grupo = Casa.query.filter_by(grupo_id=grupo_id).options(
        selectinload(Casa.historial_abonos),
        selectinload(Casa.historial_pausas),
        selectinload(Casa.visitas).selectinload(Visit.productos).joinedload(VisitProduct.product),
        selectinload(Casa.visitas).joinedload(Visit.promo)
    ).all()
    grupo_obj = GrupoCliente.query.get(grupo_id)
    historiales = AbonoHistorico.query.filter(
        AbonoHistorico.casa_id.in_([c.id for c in casas_grupo]),
        AbonoHistorico.mes == mes,
        AbonoHistorico.anio == anio
    ).all()

    # --- AUDITORÍA ---
    if casas_grupo and monto_ingresado > 0:
        mes_nombre_rg = nombre_mes(mes)
        if monto_usd and cotizacion_usd:
            detalle_rg = f"Grupo {grupo_obj.nombre if grupo_obj else grupo_id} — {mes_nombre_rg} {anio} — {format_money(float(monto_usd))} USD X ${format_money(float(cotizacion_usd))} = ${format_money(monto_ingresado)}"
        else:
            detalle_rg = f"Grupo {grupo_obj.nombre if grupo_obj else grupo_id} — {mes_nombre_rg} {anio} — ${format_money(monto_ingresado)}"
        registrar_auditoria(current_user.username, 'PAGO_PARCIAL', detalle_rg)

    deudas = []
    total_deuda_grupo = 0

    for h in historiales:
        c = h.casa
        total_mes = float(c.obtener_gastos_mensuales(mes, anio)['total'])
        saldo_ant = c.obtener_saldo_anterior(mes, anio)
        deuda_total = total_mes + saldo_ant
        # Clamp a 0: si la casa tiene saldo a favor (deuda_restante < 0), no genera deuda
        deuda_restante = max(0.0, deuda_total - float(h.monto_pagado or 0))

        total_deuda_grupo += deuda_restante
        deudas.append({"hist": h, "restante": deuda_restante})

    # Solo usar saldo_a_favor si fue generado en un mes anterior al actual
    saldo_grupo = 0.0
    if grupo_obj and float(grupo_obj.saldo_a_favor or 0) > 0.01:
        sm, sy = grupo_obj.saldo_desde_mes, grupo_obj.saldo_desde_anio
        if sm and sy and (anio, mes) > (sy, sm):
            saldo_grupo = float(grupo_obj.saldo_a_favor)
    disponible_total = monto_ingresado + saldo_grupo

    if disponible_total >= total_deuda_grupo:
        # Pagar cada casa exactamente su deuda (sin distribuir sobrante a las casas)
        for d in deudas:
            if d["restante"] > 0.01:
                aplicar_pago_en_cascada(d["hist"].casa, d["restante"], current_user.username, mes, anio)
        # El sobrante queda a favor del grupo, registrado desde este mes
        if grupo_obj is not None:
            grupo_obj.saldo_a_favor = disponible_total - total_deuda_grupo
            grupo_obj.saldo_desde_mes = mes
            grupo_obj.saldo_desde_anio = anio
    else:
        # Pago parcial: aplica en cascada hasta agotar el disponible (incluyendo saldo del grupo)
        if grupo_obj is not None:
            grupo_obj.saldo_a_favor = 0.0
            grupo_obj.saldo_desde_mes = None
            grupo_obj.saldo_desde_anio = None
        plata_disponible = disponible_total
        for d in deudas:
            if plata_disponible <= 0.01:
                break
            if d["restante"] <= 0.01:
                continue  # casa con saldo a favor, no requiere pago
            if plata_disponible >= d["restante"]:
                aplicar_pago_en_cascada(d["hist"].casa, d["restante"], current_user.username, mes, anio)
                plata_disponible -= d["restante"]
            else:
                aplicar_pago_en_cascada(d["hist"].casa, plata_disponible, current_user.username, mes, anio)
                plata_disponible = 0

    db.session.commit()
    wa_chat_url = next((generar_wa_chat_url(c) for c in casas_grupo if c.telefono), None)
    return jsonify({"success": True, "wa_chat_url": wa_chat_url})


@dashboard_bp.route("/registrar-pago-especial/<int:id_historial>", methods=["POST"])
@login_required
@admin_required
def registrar_pago_especial(id_historial):
    registro = AbonoHistorico.query.get_or_404(id_historial)
    monto_ingresado = float(request.json.get("monto", 0))
    monto_usd = request.json.get("monto_usd")
    cotizacion_usd = request.json.get("cotizacion_usd")

    if monto_ingresado > 0:
        # --- AUDITORÍA ---
        mes_nombre_e = nombre_mes(registro.mes)
        if monto_usd and cotizacion_usd:
            detalle_e = f"{registro.casa.nombre_formateado()} — {mes_nombre_e} {registro.anio} — {format_money(float(monto_usd))} USD X ${format_money(float(cotizacion_usd))} = ${format_money(monto_ingresado)}"
        else:
            detalle_e = f"{registro.casa.nombre_formateado()} — {mes_nombre_e} {registro.anio} — ${format_money(monto_ingresado)}"
        registrar_auditoria(current_user.username, 'PAGO_PARCIAL', detalle_e)
        aplicar_pago_en_cascada(registro.casa, monto_ingresado, current_user.username, registro.mes, registro.anio)

    db.session.commit()
    return jsonify({"success": True, "wa_chat_url": generar_wa_chat_url(registro.casa)})


@dashboard_bp.route("/planilla-impresion")
@login_required
@admin_required
def planilla_impresion():
    mes    = int(request.args.get("mes",    datetime.now().month))
    anio   = int(request.args.get("anio",   datetime.now().year))
    filtro = request.args.get("filtro", "todos")
    
    registro_congelado = CierreMes.query.filter_by(mes=mes, anio=anio).first()
    mes_congelado = True if registro_congelado else False

    casas_raw = Casa.query.options(
        joinedload(Casa.country),
        joinedload(Casa.barrio),
        joinedload(Casa.grupo),
        selectinload(Casa.historial_pausas),
        selectinload(Casa.visitas).selectinload(Visit.productos).joinedload(VisitProduct.product),
        selectinload(Casa.visitas).joinedload(Visit.promo)
    ).all()
    historial_dict = {h.casa_id: h for h in AbonoHistorico.query.filter_by(mes=mes, anio=anio).all()}
    saldos_batch = calcular_saldos_anteriores_batch(mes, anio)

    casas = []
    for c in casas_raw:
        # Excluir clientes cuya fecha de inicio es posterior al mes consultado
        if c.fecha_creacion:
            if (c.fecha_creacion.year, c.fecha_creacion.month) > (anio, mes):
                continue
        datos_v = c.obtener_gastos_mensuales(mes, anio, hist=historial_dict.get(c.id))
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

        pausado_mes = _casa_pausada_en_mes(casa, mes, anio, producto)
        if pausado_mes:
            if producto == 0:
                continue
            abono = 0.0
        elif historial:
            abono = float(historial.monto)
        else:
            abono = float(casa.precio_base or 0) if (casa.activo or producto > 0) else 0.0

        saldo_anterior_visual = saldos_batch.get(casa.id, 0.0) if saldos_batch else casa.obtener_saldo_anterior(mes, anio)

        total_a_pagar = abono + producto + saldo_anterior_visual

        if not casa.activo and total_a_pagar <= 0.1:
            continue

        monto_pagado_mes_actual = float(getattr(historial, 'monto_pagado', 0) or 0)

        esta_pagado = False
        if historial and getattr(historial, 'pagado', False) and (total_a_pagar - monto_pagado_mes_actual) <= 0.01:
            esta_pagado = True
        elif total_a_pagar <= 0.01 and historial and getattr(historial, 'pagado', False):
            esta_pagado = True

        notificado = bool(getattr(historial, 'mensaje_enviado', False)) if historial else False
        tiene_saldo = saldo_anterior_visual > 0.1
        pago_parcial = monto_pagado_mes_actual > 0 and not esta_pagado

        # Estado para filtros: pagado > notificado > saldar > pendiente
        # "saldar" = solo quienes hicieron un pago parcial (tienen el botón amarillo)
        # Saldo anterior sin pago = pendiente o notificado, no saldar
        if esta_pagado:
            estado = "pagado"
        elif notificado:
            estado = "notificado"
        elif pago_parcial:
            estado = "saldar"
        else:
            estado = "pendiente"

        # Monto restante a cobrar (total menos lo ya pagado este mes)
        restante = max(0.0, total_a_pagar - monto_pagado_mes_actual)

        # Agrupa productos del mes (normales + extras) sin distinguir origen
        prods_agrupados = {}
        for v in casa.visitas:
            if v.fecha.month == mes and v.fecha.year == anio:
                for vp in v.productos:
                    nombre = vp.product.nombre.strip()
                    unidad = (vp.product.unidad or "").strip()
                    clave = f"{nombre}_{unidad}"
                    if clave not in prods_agrupados:
                        prods_agrupados[clave] = {"nombre": nombre, "unidad": unidad, "cantidad": 0.0}
                    prods_agrupados[clave]["cantidad"] += float(vp.cantidad)

        detalle_prods = []
        for p in prods_agrupados.values():
            c = p["cantidad"]
            cant_str = str(int(c)) if c == int(c) else str(round(c, 2))
            detalle_prods.append(f"{cant_str}{p['unidad']} {p['nombre']}")

        texto_detalle = ", ".join(detalle_prods)

        item = {
            "cliente": casa.nombre_formateado(),
            "producto": producto,
            "detalle_productos": texto_detalle,
            "abono": abono,
            "saldo_anterior": saldo_anterior_visual,
            "total_a_pagar": total_a_pagar,
            "restante": restante,
            "monto_pagado": monto_pagado_mes_actual,
            "pagado": esta_pagado,
            "notificado": notificado,
            "tiene_saldo": tiene_saldo,
            "pago_parcial": pago_parcial,
            "estado": estado,
        }

        if casa.grupo_id:
            if casa.grupo_id not in reporte_grupos:
                reporte_grupos[casa.grupo_id] = {
                    "nombre": casa.grupo.nombre,
                    "nombre_display": casa.grupo.nombre_display,
                    "filas": [],
                    "total_grupo": 0.0,
                    "saldo_a_favor": _saldo_grupo_para_mes(casa.grupo, mes, anio),
                    "grupo_pagado": True,
                    "grupo_notificado": False,
                    "grupo_tiene_saldo": False,
                }
            reporte_grupos[casa.grupo_id]["filas"].append(item)
            reporte_grupos[casa.grupo_id]["total_grupo"] += restante
            if not esta_pagado:
                reporte_grupos[casa.grupo_id]["grupo_pagado"] = False
            if notificado:
                reporte_grupos[casa.grupo_id]["grupo_notificado"] = True
            if tiene_saldo:
                reporte_grupos[casa.grupo_id]["grupo_tiene_saldo"] = True
        else:
            reporte_sueltas.append(item)
        
    # Calcular estado de cada grupo para filtros
    # "saldar" = solo si algún miembro hizo pago parcial (mismo criterio que filas)
    for g in reporte_grupos.values():
        any_parcial = any(f.get("pago_parcial") for f in g["filas"])
        if g["grupo_pagado"]:
            g["estado"] = "pagado"
        elif g["grupo_notificado"]:
            g["estado"] = "notificado"
        elif any_parcial:
            g["estado"] = "saldar"
        else:
            g["estado"] = "pendiente"

    return render_template("dashboard/planilla.html",
                           reporte_sueltas=reporte_sueltas,
                           reporte_grupos=list(reporte_grupos.values()),
                           mes_nombre=nombre_mes(mes, largo=True),
                           anio=anio,
                           filtro=filtro)

@dashboard_bp.route("/api/totales")
@login_required
@admin_required
def api_totales():
    mes = int(request.args.get("mes", datetime.now().month))
    anio = int(request.args.get("anio", datetime.now().year))
    
    query_casas = Casa.query.options(
        selectinload(Casa.historial_pausas),
        selectinload(Casa.visitas).selectinload(Visit.productos).joinedload(VisitProduct.product),
        selectinload(Casa.visitas).joinedload(Visit.promo)
    )
    casas_raw = query_casas.all()
    historial_dict = {h.casa_id: h for h in AbonoHistorico.query.filter_by(mes=mes, anio=anio).all()}
    saldos_batch = calcular_saldos_anteriores_batch(mes, anio)

    total_abono = 0.0
    total_extras = 0.0
    total_recaudado = 0.0
    total_deuda_anterior = 0.0

    for casa in casas_raw:
        datos = casa.obtener_gastos_mensuales(mes, anio)
        extras_v = float(datos.get("extras", 0))

        if not casa.activo and extras_v <= 0:
            continue

        saldo_anterior_real = saldos_batch.get(casa.id, 0.0) if saldos_batch else casa.obtener_saldo_anterior(mes, anio)
        historial = historial_dict.get(casa.id)
        
        pausado_mes = _casa_pausada_en_mes(casa, mes, anio, extras_v)
        if pausado_mes:
            abono_mes = 0.0
        elif historial:
            abono_mes = float(historial.monto)
        else:
            abono_mes = float(casa.precio_base or 0) if (casa.activo or extras_v > 0) else 0.0

        # obtener_saldo_anterior ya refleja correctamente todos los pagos en cascada
        saldo_anterior_visual = saldo_anterior_real

        if not casa.activo and (abono_mes + extras_v + saldo_anterior_visual) <= 0.1:
            continue

        total_mes = abono_mes + extras_v

        if saldo_anterior_visual > 0:
            total_deuda_anterior += saldo_anterior_visual

        monto_pagado_mes_actual = float(getattr(historial, 'monto_pagado', 0) or 0)
        pagos_en_este_dashboard = monto_pagado_mes_actual

        total_abono += abono_mes
        total_extras += extras_v
        total_recaudado += pagos_en_este_dashboard

    total_general = total_abono + total_extras + total_deuda_anterior
    return jsonify({
        "kpi_deuda": f"${format_money(total_deuda_anterior)}",
        "kpi_recaudado": f"${format_money(total_recaudado)}",
        "kpi_pendiente": f"${format_money(total_general - total_recaudado)}",
        "kpi_total": f"${format_money(total_general)}"
    })

# ================================================
# API: WA URL ON-DEMAND
# ================================================

@dashboard_bp.route("/api/wa-url/<int:id_historial>")
@login_required
@admin_required
def api_wa_url(id_historial):
    hist = AbonoHistorico.query.get_or_404(id_historial)
    casa = Casa.query.options(
        selectinload(Casa.historial_abonos),
        selectinload(Casa.historial_pausas),
        selectinload(Casa.visitas).selectinload(Visit.productos).joinedload(VisitProduct.product),
        selectinload(Casa.visitas).joinedload(Visit.promo)
    ).get(hist.casa_id)
    if not casa or not casa.telefono:
        return jsonify({"url": None})
    mes, anio = hist.mes, hist.anio
    from app.models.plantilla_mensaje import PlantillaMensaje
    pt = PlantillaMensaje.get_activa()
    datos = casa.obtener_gastos_mensuales(mes, anio, hist=hist)
    extras = float(datos.get("extras", 0))
    pausado = _casa_pausada_en_mes(casa, mes, anio, extras)
    abono_mes = 0.0 if pausado else (float(hist.monto) if float(hist.monto) > 0 else float(casa.precio_base or 0))
    saldo_anterior = casa.obtener_saldo_anterior(mes, anio)
    pagos = float(hist.monto_pagado or 0)
    num_tel = limpiar_telefono(casa.telefono)
    texto = generar_wa_individual(casa, mes, anio, abono_mes, extras, saldo_anterior, pagos, pt=pt)
    return jsonify({"url": f"whatsapp://send?phone={num_tel}&text={urllib.parse.quote(texto)}"})


@dashboard_bp.route("/api/wa-url-grupo/<int:grupo_id>")
@login_required
@admin_required
def api_wa_url_grupo(grupo_id):
    mes = request.args.get("mes", type=int)
    anio = request.args.get("anio", type=int)
    if not mes or not anio:
        return jsonify({"url": None})
    from app.models.grupo import GrupoCliente
    grupo = GrupoCliente.query.get_or_404(grupo_id)
    casas_grupo = Casa.query.filter_by(grupo_id=grupo_id).options(
        selectinload(Casa.historial_abonos),
        selectinload(Casa.historial_pausas),
        selectinload(Casa.visitas).selectinload(Visit.productos).joinedload(VisitProduct.product),
        selectinload(Casa.visitas).joinedload(Visit.promo)
    ).all()
    telefono_repr = next((c.telefono for c in casas_grupo if c.telefono), None)
    if not telefono_repr:
        return jsonify({"url": None})
    hist_dict = {h.casa_id: h for h in AbonoHistorico.query.filter(
        AbonoHistorico.casa_id.in_([c.id for c in casas_grupo]),
        AbonoHistorico.mes == mes, AbonoHistorico.anio == anio
    ).all()}
    casas_data = []
    total_grupo_mes = total_grupo_saldo = total_pagos = 0.0
    for c in casas_grupo:
        h = hist_dict.get(c.id)
        datos = c.obtener_gastos_mensuales(mes, anio, hist=h)
        extras = float(datos.get("extras", 0))
        pausado = _casa_pausada_en_mes(c, mes, anio, extras)
        abono = 0.0 if pausado else (float(h.monto) if h and float(h.monto) > 0 else float(c.precio_base or 0))
        saldo = c.obtener_saldo_anterior(mes, anio)
        pagos = float(h.monto_pagado or 0) if h else 0.0
        total_grupo_mes += abono + extras
        total_grupo_saldo += saldo
        total_pagos += pagos
        casas_data.append({"casa": c, "abono": abono, "extras": extras, "saldo_anterior": saldo, "pausado": pausado})
    from app.models.plantilla_mensaje import PlantillaMensaje
    pt = PlantillaMensaje.get_activa()
    saldo_a_favor = _saldo_grupo_para_mes(grupo, mes, anio)
    texto = generar_wa_grupo(grupo.nombre, casas_data, mes, anio, total_grupo_mes, total_grupo_saldo, total_pagos, saldo_a_favor, pt=pt)
    tel = re.sub(r'\D', '', telefono_repr)
    if len(tel) == 10:
        tel = "549" + tel
    return jsonify({"url": f"whatsapp://send?phone={tel}&text={urllib.parse.quote(texto)}"})


# ================================================
# API: COTIZACIÓN DÓLAR
# ================================================
@dashboard_bp.route("/api/cotizacion-dolar")
@login_required
@admin_required
def api_cotizacion_dolar():
    """Devuelve la cotización actualizada según el tipo configurado en root."""
    import urllib.request
    import json as _json
    from app.models.configuracion import Configuracion

    tipo = Configuracion.get('tipo_dolar', 'blue')  # 'blue' o 'mep'
    endpoint_map = {
        'blue': 'blue',
        'mep':  'bolsa',  # MEP = Bolsa en dolarapi.com
    }
    casa = endpoint_map.get(tipo, 'blue')

    try:
        url = f"https://dolarapi.com/v1/dolares/{casa}"
        req = urllib.request.Request(url, headers={"User-Agent": "DrPiscinas/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = _json.loads(resp.read().decode())
        return jsonify({
            "ok":    True,
            "tipo":  tipo,
            "label": "Dólar Blue" if tipo == 'blue' else "Dólar MEP",
            "compra": data.get("compra"),
            "venta":  data.get("venta"),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502


@dashboard_bp.route("/auditoria")
@login_required
def auditoria():
    from app.models.auditoria import AuditoriaLog
    from datetime import datetime as _dt, timedelta as _td
    if not (current_user.is_admin() or current_user.username == 'root'):
        flash("No tenés permisos para ver esta sección.", "error")
        return redirect(url_for('main.home'))

    page    = request.args.get("page", 1, type=int)
    usuario = request.args.get("usuario", "").strip()
    accion  = request.args.get("accion", "").strip()
    fecha_d = request.args.get("fecha_desde", "").strip()
    fecha_h = request.args.get("fecha_hasta", "").strip()

    q = AuditoriaLog.query.order_by(AuditoriaLog.fecha.desc())

    if current_user.username != 'root':
        q = q.filter(AuditoriaLog.usuario != 'root')

    if usuario:
        q = q.filter(AuditoriaLog.usuario.ilike(f"%{usuario}%"))
    if accion:
        q = q.filter(AuditoriaLog.accion == accion)
    if fecha_d:
        try:
            q = q.filter(AuditoriaLog.fecha >= _dt.strptime(fecha_d, "%Y-%m-%d"))
        except ValueError:
            pass
    if fecha_h:
        try:
            q = q.filter(AuditoriaLog.fecha < _dt.strptime(fecha_h, "%Y-%m-%d") + _td(days=1))
        except ValueError:
            pass

    paginacion = q.paginate(page=page, per_page=50, error_out=False)
    acciones_disponibles = [r[0] for r in db.session.query(AuditoriaLog.accion).distinct().order_by(AuditoriaLog.accion).all()]

    return render_template(
        "dashboard/auditoria.html",
        logs=paginacion.items,
        paginacion=paginacion,
        acciones_disponibles=acciones_disponibles,
        filtro_usuario=usuario,
        filtro_accion=accion,
        filtro_fecha_desde=fecha_d,
        filtro_fecha_hasta=fecha_h,
    )


@dashboard_bp.route("/test-forzar-error")
@login_required
@admin_required
def test_forzar_error():
    raise Exception("Error de prueba forzado manualmente")
