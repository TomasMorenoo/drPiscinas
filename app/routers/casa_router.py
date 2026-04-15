from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.decorators import admin_required
from app import db
from app.models import Casa, Country, Barrio
from app.models.visit import Visit
from app.models.visit_product import VisitProduct
from app.models.products import Product
from app.models.abono_historico import AbonoHistorico
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, and_
import re
import calendar
from datetime import datetime
from app.models.casa import HistorialAumento
import os

casa_bp = Blueprint("casas", __name__, url_prefix="/casas")

# ==========================================
# AUDITORÍA DB
# ==========================================

def registrar_auditoria(usuario, accion, detalle):
    """Guarda una entrada en el log de auditoría."""
    from app.models.auditoria import AuditoriaLog
    from datetime import timedelta, timezone
    tz_ar = timezone(timedelta(hours=-3))
    ahora_ar = datetime.now(tz_ar).replace(tzinfo=None)
    log = AuditoriaLog(fecha=ahora_ar, usuario=usuario, accion=accion, detalle=detalle)
    db.session.add(log)

# ==========================================
# LOG EN TXT DE AUMENTOS (AUDITORÍA)
# ==========================================
NOMBRES_MESES = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']

def format_money(value):
    """Formatea números a texto con puntos en los miles (ej: 15.000)"""
    return f"{value:,.0f}".replace(",", ".")

def log_aumento_txt(cliente, p_i, aumento, p_f, mes_num):
    """Guarda el registro exacto del aumento en un archivo de texto"""
    mes_nombre = NOMBRES_MESES[mes_num] if 1 <= mes_num <= 12 else str(mes_num)
    linea = f"{cliente} | {format_money(p_i)} | {format_money(aumento)} | {format_money(p_f)} | {mes_nombre}\n"
    
    # Se guarda en la raíz del proyecto (junto a docker-compose.yml)
    filepath = os.path.join(os.getcwd(), 'registro_aumentos.txt')
    
    escribir_encabezado = not os.path.exists(filepath) or os.path.getsize(filepath) == 0
    
    with open(filepath, "a", encoding="utf-8") as f:
        if escribir_encabezado:
            f.write("CLIENTE | P.I | AUMENTO | P.F | a partir\n")
        f.write(linea)

# ==========================================
# LÓGICA DE ORDENAMIENTO (NATURAL)
# ==========================================
def natural_sort_key(casa):
    k_country = casa.country.nombre.lower() if casa.country else "zzz"
    k_barrio = casa.barrio.nombre.lower() if casa.barrio else ""
    k_numero = [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(casa.numero))]
    return (k_country, k_barrio, k_numero)

# ==========================================
# MAGIA DE REDONDEO Y LINEA DE TIEMPO
# ==========================================
def aplicar_redondeo(valor):
    entero = int(round(valor))
    resto = entero % 1000
    if resto < 500:
        return float(entero - resto)       
    elif resto == 500:
        return float(entero)               
    else:
        return float(entero + (1000 - resto)) 

def asegurar_historial_pasado(casa, precio_viejo, mes_desde, anio_desde):
    from datetime import datetime
    limite_inferior = datetime(2026, 1, 1)

    fecha_inicio = max(casa.fecha_creacion or limite_inferior, limite_inferior)

    m_curr = fecha_inicio.month
    y_curr = fecha_inicio.year
    m_end = mes_desde - 1
    y_end = anio_desde
    if m_end == 0:
        m_end = 12
        y_end -= 1

    while (y_curr < y_end) or (y_curr == y_end and m_curr <= m_end):
        hist = AbonoHistorico.query.filter_by(casa_id=casa.id, mes=m_curr, anio=y_curr).first()
        if not hist:
            nuevo_hist = AbonoHistorico(
                casa_id=casa.id,
                mes=m_curr,
                anio=y_curr,
                monto=precio_viejo,
                pagado=True,
                monto_pagado=precio_viejo,
                cobrado_por="SISTEMA (Historial Congelado)"
            )
            db.session.add(nuevo_hist)
        m_curr += 1
        if m_curr > 12:
            m_curr = 1
            y_curr += 1

def actualizar_historial_futuro(casa, nuevo_precio, mes_desde, anio_desde):
    futuros = AbonoHistorico.query.filter(
        AbonoHistorico.casa_id == casa.id,
        or_(
            AbonoHistorico.anio > anio_desde,
            and_(AbonoHistorico.anio == anio_desde, AbonoHistorico.mes >= mes_desde)
        ),
        AbonoHistorico.pagado == False,
        AbonoHistorico.monto_pagado == 0  # No tocar meses con pagos ya registrados
    ).all()
    for f in futuros:
        f.monto = nuevo_precio

# ==========================================
# LISTADO
# ==========================================
@casa_bp.route("/", methods=["GET"])
@login_required
@admin_required
def listar_casas():
    buscar = request.args.get("buscar", "").strip()
    estado = request.args.get("estado", "todo")
    country_id = request.args.get("country_id", "")
    barrio_id = request.args.get("barrio_id", "")

    query = Casa.query

    if buscar:
        query = query.join(Country).outerjoin(Barrio).filter(
            db.or_(
                Casa.numero.ilike(f"%{buscar}%"),
                Barrio.nombre.ilike(f"%{buscar}%"),
                Country.nombre.ilike(f"%{buscar}%"),
                Casa.nombre_cliente.ilike(f"%{buscar}%")
            )
        )

    if estado == "activos":
        query = query.filter(Casa.activo == True)
    elif estado == "inactivos":
        query = query.filter(Casa.activo == False)

    if country_id:
        query = query.filter(Casa.country_id == country_id)

    if barrio_id:
        query = query.filter(Casa.barrio_id == barrio_id)

    casas = query.all()
    casas.sort(key=natural_sort_key)

    countries = Country.query.filter_by(activo=True).order_by(Country.nombre).all()
    
    barrios = []
    if country_id:
        barrios = Barrio.query.filter_by(country_id=country_id, activo=True).order_by(Barrio.nombre).all()

    return render_template(
        "casas/list.html", 
        casas=casas, 
        countries=countries, 
        barrios=barrios,
        buscar_actual=buscar,
        estado_actual=estado,
        country_actual=country_id,
        barrio_actual=barrio_id
    )

# ==========================================
# HERRAMIENTA DE AUMENTOS GLOBALES
# ==========================================
@casa_bp.route("/aumento", methods=["GET", "POST"])
@login_required
@admin_required 
def herramienta_aumento():
    if request.method == "POST":
        tipo = request.form.get("tipo")
        country_id = request.form.get("country_id")
        mes_desde = int(request.form.get("mes_desde", datetime.now().month))
        anio_desde = int(request.form.get("anio_desde", datetime.now().year))
        
        try:
            valor = float(request.form.get("valor", 0).replace(',', '.'))
        except ValueError:
            flash("El valor ingresado no es válido.", "error")
            return redirect(url_for("casas.herramienta_aumento"))

        if valor <= 0:
            flash("El aumento debe ser mayor a 0.", "error")
            return redirect(url_for("casas.herramienta_aumento"))

        query = Casa.query.filter_by(activo=True)
        if country_id:
            query = query.filter_by(country_id=country_id)
        
        casas_afectadas = query.all()
        count = 0

        db.session.query(Casa).update({Casa.precio_anterior: None})

        for casa in casas_afectadas:
            precio_actual = float(casa.precio_base) if casa.precio_base else 0.0
            if precio_actual > 0:
                casa.precio_anterior = precio_actual
                if tipo == "porcentaje":
                    nuevo_bruto = precio_actual * (1 + (valor / 100))
                else:
                    nuevo_bruto = precio_actual + valor
                
                nuevo_precio = aplicar_redondeo(nuevo_bruto)
                casa.precio_base = nuevo_precio
                
                asegurar_historial_pasado(casa, precio_actual, mes_desde, anio_desde)
                actualizar_historial_futuro(casa, nuevo_precio, mes_desde, anio_desde)
                count += 1

                # --- GUARDAR EN EL TXT DE AUDITORÍA ---
                diferencia = nuevo_precio - precio_actual
                log_aumento_txt(casa.nombre_formateado(), precio_actual, diferencia, nuevo_precio, mes_desde)

        db.session.commit()

        # --- REGISTRO DEL AUMENTO ---
        if count > 0:
            target = "TODOS LOS CLIENTES"
            if country_id:
                c_obj = Country.query.get(country_id)
                if c_obj: target = f"COUNTRY {c_obj.nombre.upper()}"

            if tipo == "porcentaje":
                texto_valor = f"{valor}%"
            else:
                texto_valor = f"${format_money(valor)}"
            desc = f"Aumento Global ({texto_valor}) a {target}"

            log = HistorialAumento(fecha=datetime.now(), descripcion=desc, casas_afectadas=count, mes_desde=mes_desde, anio_desde=anio_desde)
            db.session.add(log)

            # --- AUDITORÍA: aumento individual por cada casa ---
            for casa in casas_afectadas:
                precio_viejo = float(casa.precio_anterior) if casa.precio_anterior else 0.0
                precio_nuevo = float(casa.precio_base)
                diferencia_aud = precio_nuevo - precio_viejo
                registrar_auditoria(
                    current_user.username,
                    'AUMENTO',
                    f"{casa.nombre_formateado()} — Antes: ${format_money(precio_viejo)} → +${format_money(diferencia_aud)} → Nuevo: ${format_money(precio_nuevo)} (desde {mes_desde}/{anio_desde})"
                )

            db.session.commit()

            flash(f"✅ Precios actualizados en {count} propiedades a partir de {mes_desde}/{anio_desde}.", "success")
        else:
            flash("⚠️ No se encontraron propiedades con abono mayor a $0 para aumentar.", "warning")
            
        return redirect(url_for("casas.listar_casas"))

    countries = Country.query.filter_by(activo=True).order_by(Country.nombre).all()
    hay_backup = Casa.query.filter(Casa.precio_anterior.isnot(None), Casa.precio_anterior > 0).first() is not None
    
    # Límite de 15 restaurado para la vista web
    ultimos_aumentos = HistorialAumento.query.order_by(HistorialAumento.fecha.desc()).limit(15).all()
    
    return render_template("casas/aumento.html", countries=countries, hay_backup=hay_backup, ultimos_aumentos=ultimos_aumentos)

# ==========================================
# DESHACER EL ÚLTIMO AUMENTO
# ==========================================
@casa_bp.route("/deshacer_aumento")
@login_required
@admin_required
def deshacer_aumento():
    casas_modificadas = Casa.query.filter(Casa.precio_anterior.isnot(None), Casa.precio_anterior > 0).all()
    
    if not casas_modificadas:
        flash("No hay cambios recientes válidos para deshacer.", "warning")
        return redirect(url_for("casas.listar_casas"))
    
    count = 0
    for casa in casas_modificadas:
        precio_malo = float(casa.precio_base)
        precio_bueno = float(casa.precio_anterior)
        
        historiales = AbonoHistorico.query.filter_by(casa_id=casa.id, pagado=False).all()
        for h in historiales:
            if float(h.monto) == precio_malo:
                h.monto = precio_bueno
        
        casa.precio_base = precio_bueno
        casa.precio_anterior = None 
        count += 1
        
    db.session.commit()
    
    # --- REGISTRO DEL DESHACER ---
    if count > 0:
        desc = "Reversión (Deshacer) del último aumento"
        log = HistorialAumento(fecha=datetime.now(), descripcion=desc, casas_afectadas=count)
        db.session.add(log)

        # --- AUDITORÍA ---
        registrar_auditoria(
            current_user.username,
            'DESHACER_AUMENTO',
            f"Se revirtió el último aumento en {count} propiedades"
        )

        db.session.commit()

    flash(f"⏪ Se restauraron los abonos originales en {count} propiedades.", "info")
    return redirect(url_for("casas.listar_casas"))

# ==========================================
# EDITAR CLIENTE
# ==========================================
@casa_bp.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required 
def editar_casa(id):
    casa = Casa.query.get_or_404(id)

    if request.method == "POST":
        # --- LOGICA DEL S/N ---
        sin_numero = request.form.get("sin_numero")
        if sin_numero:
            numero = "S/N"
        else:
            numero = request.form.get("numero", "").strip()
            
        nombre_cliente = request.form.get("nombre_cliente", "").strip()
        telefono = request.form.get("telefono", "").strip()
        email = request.form.get("email", "").strip()
        fecha_creacion_str = request.form.get("fecha_creacion", "").strip()
        try:
            nueva_fecha_creacion = datetime.strptime(fecha_creacion_str, '%Y-%m-%d') if fecha_creacion_str else casa.fecha_creacion
        except ValueError:
            nueva_fecha_creacion = casa.fecha_creacion

        try:
            nuevo_precio = float(request.form.get("precio_base", 0))
        except ValueError:
            flash("El precio debe ser un número válido.", "error")
            return redirect(url_for("casas.editar_casa", id=id))
            
        country_id = request.form.get("country_id")
        barrio_id = request.form.get("barrio_id") or None

        if not numero or not country_id or not telefono or nuevo_precio < 0:
            flash("Datos inválidos. Asegurate de completar el Teléfono y el Número.", "error")
            return redirect(url_for("casas.editar_casa", id=id))

        query = Casa.query.filter(Casa.id != id).filter_by(numero=numero, country_id=country_id)
        if barrio_id:
            query = query.filter_by(barrio_id=barrio_id)
        else:
            query = query.filter_by(barrio_id=None)
            
        if query.first():
            flash("Ya existe otra casa con esa dirección.", "error")
            return redirect(url_for("casas.editar_casa", id=id))

        precio_actual_db = float(casa.precio_base) if casa.precio_base else 0.0
        
        # --- EL BLINDAJE PARA LA EDICIÓN MANUAL ---
        if abs(precio_actual_db - nuevo_precio) > 0.01:
            casa.precio_anterior = precio_actual_db
            
            ahora = datetime.now()
            # Congelamos el historial usando la función suelta, pasándole el objeto 'casa'
            asegurar_historial_pasado(casa, precio_actual_db, ahora.month, ahora.year)
            
            casa.precio_base = nuevo_precio
            
            # Actualizamos el mes actual si no está pagado
            hist_actual = AbonoHistorico.query.filter_by(
                casa_id=casa.id, mes=ahora.month, anio=ahora.year, pagado=False
            ).first()
            if hist_actual:
                hist_actual.monto = nuevo_precio

        casa.numero = numero
        casa.country_id = country_id
        casa.barrio_id = barrio_id
        casa.nombre_cliente = nombre_cliente
        casa.telefono = telefono
        casa.email = email if email else None
        casa.fecha_creacion = nueva_fecha_creacion
        
        db.session.commit()
        flash("Cliente actualizado.", "success")
        return redirect(url_for("casas.listar_casas"))

    countries = Country.query.filter_by(activo=True).order_by(Country.nombre).all()
    barrios = Barrio.query.filter_by(country_id=casa.country_id, activo=True).order_by(Barrio.nombre).all()
    
    return render_template("casas/edit.html", casa=casa, countries=countries, barrios=barrios)

# ==========================================
# CREAR (CON CARGA MÚLTIPLE)
# ==========================================
@casa_bp.route("/create", methods=["GET", "POST"])
@login_required
@admin_required 
def crear_casa():
    if request.method == "POST":
        # --- LOGICA DEL S/N ---
        sin_numero = request.form.get("sin_numero")
        if sin_numero:
            numeros_input = "S/N"
        else:
            numeros_input = request.form.get("numero", "").strip()
            
        precio_base = request.form.get("precio_base", "").strip()
        country_id = request.form.get("country_id")
        barrio_id = request.form.get("barrio_id") or None
        nombre_cliente = request.form.get("nombre_cliente", "").strip()
        telefono = request.form.get("telefono", "").strip()
        email = request.form.get("email", "").strip()
        fecha_creacion_str = request.form.get("fecha_creacion", "").strip()
        try:
            fecha_creacion_obj = datetime.strptime(fecha_creacion_str, '%Y-%m-%d') if fecha_creacion_str else datetime.now()
        except ValueError:
            fecha_creacion_obj = datetime.now()

        if not numeros_input or not precio_base or not country_id or not telefono:
            flash("Faltan datos obligatorios (incluyendo el Teléfono).", "error")
            return redirect(url_for("casas.crear_casa"))

        numeros_lista = [n.strip() for n in numeros_input.split(",") if n.strip()]
        
        creados = 0
        omitidos = 0
        
        for num in numeros_lista:
            query = Casa.query.filter_by(numero=num, country_id=country_id)
            if barrio_id:
                query = query.filter_by(barrio_id=barrio_id)
            else:
                query = query.filter_by(barrio_id=None)
                
            if query.first():
                omitidos += 1
                continue 

            nueva_casa = Casa(
                numero=num,
                precio_base=precio_base,
                country_id=country_id,
                barrio_id=barrio_id,
                nombre_cliente=nombre_cliente,
                telefono=telefono,
                email=email if email else None,
                fecha_creacion=fecha_creacion_obj
            )
            db.session.add(nueva_casa)
            creados += 1

        db.session.commit()

        # --- AUDITORÍA ---
        if creados > 0:
            country_obj = Country.query.get(country_id)
            country_nombre = country_obj.nombre if country_obj else str(country_id)
            nombres_creados = ", ".join(numeros_lista[:creados]) if len(numeros_lista) <= 5 else f"{creados} clientes"
            registrar_auditoria(
                current_user.username,
                'CREAR_CLIENTE',
                f"{nombres_creados} — {country_nombre}" + (f" — {nombre_cliente}" if nombre_cliente else "")
            )
            db.session.commit()

        if creados > 0 and omitidos == 0:
            flash(f"✅ Se crearon {creados} clientes correctamente.", "success")
        elif creados > 0 and omitidos > 0:
            flash(f"⚠️ Se crearon {creados} clientes. {omitidos} se omitieron porque ya existían.", "warning")
        elif creados == 0 and omitidos > 0:
            flash(f"❌ No se creó ningún cliente. Los {omitidos} ingresados ya existían.", "error")

        return redirect(url_for("casas.listar_casas"))

    countries = Country.query.filter_by(activo=True).order_by(Country.nombre).all()
    barrios = Barrio.query.filter_by(activo=True).order_by(Barrio.nombre).all()
    return render_template("casas/create.html", countries=countries, barrios=barrios)

# ==========================================
# EXTRAS MANUALES
# ==========================================
@casa_bp.route("/perfil/<int:id>/agregar_extra", methods=["POST"])
@login_required
def agregar_extra(id):
    casa = Casa.query.get_or_404(id)
    product_id = request.form.get("product_id")
    cantidad = request.form.get("cantidad")
    mes = int(request.form.get("mes"))
    anio = int(request.form.get("anio"))

    if product_id and cantidad:
        producto = Product.query.get(product_id)
        
        ultimo_dia = calendar.monthrange(anio, mes)[1]
        fecha_fantasma = datetime(anio, mes, ultimo_dia, 12, 0, 0)

        nueva_visita = Visit(
            casa_id=casa.id,
            usuario_id=current_user.id,
            fecha=fecha_fantasma,
            observaciones="[EXTRA_MANUAL]"
        )
        db.session.add(nueva_visita)
        db.session.flush()

        nuevo_vp = VisitProduct(
            visit_id=nueva_visita.id,
            product_id=producto.id,
            cantidad=float(cantidad),
            precio_unitario=producto.precio
        )
        db.session.add(nuevo_vp)
        
        historial = AbonoHistorico.query.filter_by(casa_id=casa.id, mes=mes, anio=anio).first()
        if historial:
            historial.monto += float(cantidad) * float(producto.precio)

        db.session.commit()
        flash("Producto extra cargado exitosamente.", "success")
        
    return redirect(url_for('casas.perfil', id=casa.id))

@casa_bp.route("/eliminar_extra/<int:visit_id>", methods=["POST"])
@login_required
@admin_required
def eliminar_extra(visit_id):
    visita = Visit.query.get_or_404(visit_id)
    casa_id = visita.casa_id
    if visita.observaciones == "[EXTRA_MANUAL]":
        historial = AbonoHistorico.query.filter_by(casa_id=casa_id, mes=visita.fecha.month, anio=visita.fecha.year).first()
        if historial:
            for vp in visita.productos:
                historial.monto -= float(vp.cantidad) * float(vp.precio_unitario or vp.product.precio)

        VisitProduct.query.filter_by(visit_id=visita.id).delete()
        db.session.delete(visita)
        db.session.commit()
        flash("Producto extra eliminado.", "info")
    return redirect(url_for('casas.perfil', id=casa_id))

# ==========================================
# PERFIL DEL CLIENTE
# ==========================================
@casa_bp.route("/perfil/<int:id>")
@login_required
def perfil(id):
    casa = Casa.query.get_or_404(id)
    
    visitas = sorted(casa.visitas, key=lambda v: v.fecha, reverse=True)
    historial_asc = AbonoHistorico.query.filter_by(casa_id=casa.id).order_by(AbonoHistorico.anio.asc(), AbonoHistorico.mes.asc()).all()
    
    productos = Product.query.filter_by(activo=True).order_by(Product.nombre).all()
    
    detalles_pagos = []
    saldo_acumulado = 0.0
    nombres_meses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

    # Filtrar meses anteriores a la fecha de alta del cliente en el sistema
    if casa.fecha_creacion:
        _fc = casa.fecha_creacion
        historial_asc = [h for h in historial_asc if (h.anio, h.mes) >= (_fc.year, _fc.month)]

    for h in historial_asc:
        gastos = casa.obtener_gastos_mensuales(h.mes, h.anio)
        total_mes = gastos['total']
        pagado_real = float(getattr(h, 'monto_pagado', 0) or 0)
        
        saldo_anterior_iter = saldo_acumulado
        saldo_acumulado += total_mes
        saldo_acumulado -= pagado_real
        
        if getattr(h, 'pagado', False) and pagado_real == 0 and saldo_acumulado > 0.01:
            pagado_simulado = saldo_acumulado 
            saldo_acumulado = 0.0
            dinero_mostrado = pagado_simulado
        else:
            dinero_mostrado = pagado_real
            
        detalles_pagos.append({
            "periodo": f"{nombres_meses[h.mes - 1]} {h.anio}",
            "saldo_anterior": saldo_anterior_iter,
            "costo_mes": total_mes,
            "pagado": dinero_mostrado,
            "saldo": saldo_acumulado,
            "historial": h
        })
        
    detalles_pagos.reverse()
    
    return render_template("casas/perfil.html", casa=casa, visitas=visitas, detalles_pagos=detalles_pagos, productos=productos)

# ==========================================
# OTRAS RUTAS
# ==========================================
@casa_bp.route("/barrios/<int:country_id>")
@login_required
def barrios_por_country(country_id):
    barrios = Barrio.query.filter_by(country_id=country_id, activo=True).order_by(Barrio.nombre).all()
    return jsonify([{"id": b.id, "nombre": b.nombre} for b in barrios])

@casa_bp.route("/toggle/<int:id>")
@login_required
@admin_required
def toggle_casa(id):
    casa = Casa.query.get_or_404(id)
    if casa.activo:
        casa.activo = False
        casa.inactivado_por = current_user.username
        casa.fecha_inactivacion = datetime.now()
        registrar_auditoria(
            current_user.username,
            'INACTIVAR_CLIENTE',
            casa.nombre_formateado()
        )
    else:
        casa.activo = True
        casa.inactivado_por = None
        casa.fecha_inactivacion = None
        registrar_auditoria(
            current_user.username,
            'ACTIVAR_CLIENTE',
            casa.nombre_formateado()
        )

    db.session.commit()
    return redirect(url_for("casas.listar_casas"))

@casa_bp.route("/delete/<int:id>", methods=["POST"])
@login_required
@admin_required
def eliminar_casa(id):
    casa = Casa.query.get_or_404(id)
    nombre_casa = casa.nombre_formateado()
    try:
        # --- AUDITORÍA (antes de borrar) ---
        registrar_auditoria(
            current_user.username,
            'ELIMINAR_CLIENTE',
            f"{nombre_casa} — Precio base: ${format_money(float(casa.precio_base or 0))}"
        )

        AbonoHistorico.query.filter_by(casa_id=id).delete()
        visitas = Visit.query.filter_by(casa_id=id).all()
        for visita in visitas:
            VisitProduct.query.filter_by(visit_id=visita.id).delete()
        Visit.query.filter_by(casa_id=id).delete()
        db.session.delete(casa)
        db.session.commit()
        flash("Cliente eliminado definitivamente.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {str(e)}", "error")
    return redirect(url_for("casas.listar_casas"))

#==============================================================================================
# AUMENTO PERSONALIZADO (Individual)
#==============================================================================================
@casa_bp.route("/aumento-individual/<int:id>", methods=["POST"])
@login_required
@admin_required
def aumento_individual(id):
    casa = Casa.query.get_or_404(id)
    tipo = request.form.get("tipo_aumento")
    mes_desde = int(request.form.get("mes_desde", datetime.now().month))
    anio_desde = int(request.form.get("anio_desde", datetime.now().year))
    
    try:
        valor = float(request.form.get("valor_aumento", 0).replace(',', '.'))
    except ValueError:
        flash("Valor inválido", "error")
        return redirect(request.referrer or url_for('casas.listar_casas'))
    
    precio_actual = float(casa.precio_base) if casa.precio_base else 0.0

    if valor > 0 and precio_actual > 0:
        db.session.query(Casa).update({Casa.precio_anterior: None})
        
        casa.precio_anterior = precio_actual
        if tipo == "porcentaje":
            nuevo_bruto = precio_actual * (1 + (valor / 100))
        else:
            nuevo_bruto = precio_actual + valor
            
        nuevo_precio = aplicar_redondeo(nuevo_bruto)
        casa.precio_base = nuevo_precio
        
        asegurar_historial_pasado(casa, precio_actual, mes_desde, anio_desde)
        actualizar_historial_futuro(casa, nuevo_precio, mes_desde, anio_desde)
            
        db.session.commit()
        
        # --- GUARDAR EN EL TXT DE AUDITORÍA ---
        diferencia = nuevo_precio - precio_actual
        log_aumento_txt(casa.nombre_formateado(), precio_actual, diferencia, nuevo_precio, mes_desde)

        # --- REGISTRO DEL AUMENTO ---
        if tipo == "porcentaje":
            texto_valor = f"{valor}%"
        else:
            texto_valor = f"${format_money(valor)}"
        desc = f"Aumento Indiv. ({texto_valor}) a {casa.nombre_formateado()}"
        log = HistorialAumento(fecha=datetime.now(), descripcion=desc, casas_afectadas=1, mes_desde=mes_desde, anio_desde=anio_desde)
        db.session.add(log)

        # --- AUDITORÍA ---
        diferencia_indiv = nuevo_precio - precio_actual
        registrar_auditoria(
            current_user.username,
            'AUMENTO',
            f"{casa.nombre_formateado()} — Antes: ${format_money(precio_actual)} → +${format_money(diferencia_indiv)} → Nuevo: ${format_money(nuevo_precio)} (desde {mes_desde}/{anio_desde})"
        )

        db.session.commit()
        
        flash(f"Aumento aplicado correctamente a {casa.nombre_formateado()} a partir de {mes_desde}/{anio_desde}", "success")
    else:
        flash("El cliente debe tener un abono mayor a $0 para aplicarle un aumento.", "warning")
        
    return redirect(request.referrer or url_for('casas.listar_casas'))

@casa_bp.route("/create_form", methods=["GET"]) 
@login_required
@admin_required
def form_crear_casa():
    return crear_casa()