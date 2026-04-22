MESES_CORTO = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
MESES_LARGO = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']

def nombre_mes(n, largo=False):
    return (MESES_LARGO if largo else MESES_CORTO)[n - 1]

def registrar_auditoria(usuario, accion, detalle):
    from app.models.auditoria import AuditoriaLog
    from app import db
    from datetime import datetime, timedelta, timezone
    tz_ar = timezone(timedelta(hours=-3))
    ahora_ar = datetime.now(tz_ar).replace(tzinfo=None)
    log = AuditoriaLog(fecha=ahora_ar, usuario=usuario, accion=accion, detalle=detalle)
    db.session.add(log)
