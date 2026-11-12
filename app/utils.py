import re

MESES_CORTO = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
MESES_LARGO = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']

def natural_sort_key(casa):
    """Clave de ordenamiento natural para objetos Casa.
    Ordena por:
    1. Country (alfabético, insensible a mayúsculas)
    2. Barrio (alfabético, insensible a mayúsculas)
    3. Número de casa de forma natural (ej: '6' antes de '120', '12A' antes de '12B')
    """
    k_country = casa.country.nombre.lower() if getattr(casa, 'country', None) and casa.country else "zzz"
    k_barrio = casa.barrio.nombre.lower() if getattr(casa, 'barrio', None) and casa.barrio else ""
    num_str = str(getattr(casa, 'numero', '') or '')
    k_numero = []
    for text in re.split(r'(\d+)', num_str):
        if not text:
            continue
        if text.isdigit():
            k_numero.append((0, int(text)))
        else:
            k_numero.append((1, text.lower()))
    return (k_country, k_barrio, k_numero)

def nombre_mes(n, largo=False):
    return (MESES_LARGO if largo else MESES_CORTO)[n - 1]

def mover_stock(product_id, cantidad, tipo, usuario, visit_id=None, motivo=None):
    from app.models.products import Product
    from app.models.movimiento_stock import MovimientoStock
    from app import db
    prod = Product.query.get(product_id)
    if prod:
        prod.stock_actual = float(prod.stock_actual) + cantidad
        db.session.add(MovimientoStock(
            product_id=product_id,
            tipo=tipo,
            cantidad=cantidad,
            motivo=motivo,
            usuario=usuario,
            visit_id=visit_id,
        ))

def proporcional_aplica(fecha_creacion, cfg=None):
    """Retorna True si el sistema proporcional aplica a este cliente según la config global.
    Acepta cfg pre-cargado para evitar N+1 queries en loops."""
    from datetime import datetime
    if cfg is None:
        from app.models.configuracion import Configuracion
        cfg = Configuracion.get('proporcional_desde')
    if not cfg:
        return False
    cfg_mes = cfg.get('mes')
    cfg_anio = cfg.get('anio')
    if not cfg_mes or not cfg_anio:
        return False
    if not fecha_creacion:
        return False
    fc = fecha_creacion.date() if isinstance(fecha_creacion, datetime) else fecha_creacion
    return (fc.year, fc.month) >= (cfg_anio, cfg_mes)

def registrar_auditoria(usuario, accion, detalle):
    from app.models.auditoria import AuditoriaLog
    from app import db
    from datetime import datetime, timedelta, timezone
    tz_ar = timezone(timedelta(hours=-3))
    ahora_ar = datetime.now(tz_ar).replace(tzinfo=None)
    log = AuditoriaLog(fecha=ahora_ar, usuario=usuario, accion=accion, detalle=detalle)
    db.session.add(log)

def es_entorno_local():
    """Retorna True si estamos en entorno local, False si producción."""
    import os
    from flask import has_request_context, request

    app_env = os.getenv('APP_ENV', '').strip().lower()
    if app_env == 'local':
        return True
    if app_env == 'production':
        return False
    if os.getenv('FLASK_DEBUG', '').strip().lower() in {'1', 'true', 'yes', 'on'}:
        return True
    if os.getenv('FLASK_ENV', '').strip().lower() == 'development':
        return True

    if has_request_context():
        try:
            host = request.host.split(':')[0]
            if host in ('localhost', '127.0.0.1') or host.startswith('192.168.') or host.startswith('10.') or host.startswith('172.'):
                return True
        except Exception:
            pass

    return False
