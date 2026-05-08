MESES_CORTO = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
MESES_LARGO = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']

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

def registrar_auditoria(usuario, accion, detalle):
    from app.models.auditoria import AuditoriaLog
    from app import db
    from datetime import datetime, timedelta, timezone
    tz_ar = timezone(timedelta(hours=-3))
    ahora_ar = datetime.now(tz_ar).replace(tzinfo=None)
    log = AuditoriaLog(fecha=ahora_ar, usuario=usuario, accion=accion, detalle=detalle)
    db.session.add(log)
