from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from app import db
from app.models import Casa, Country, Barrio
import re 

casa_bp = Blueprint("casas", __name__, url_prefix="/casas")

# ==========================================
# LÓGICA DE ORDENAMIENTO (NATURAL)
# ==========================================
def natural_sort_key(casa):
    k_country = casa.country.nombre.lower() if casa.country else "zzz"
    k_barrio = casa.barrio.nombre.lower() if casa.barrio else ""
    # Aseguramos que numero sea string por si viene vacío o raro
    k_numero = [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(casa.numero))]
    return (k_country, k_barrio, k_numero)

# ==========================================
# LISTADO
# ==========================================
@casa_bp.route("/", methods=["GET"])
@login_required
def listar_casas():
    # 1. Atrapamos los parámetros
    buscar = request.args.get("buscar", "").strip()
    estado = request.args.get("estado", "todo")
    country_id = request.args.get("country_id", "")
    barrio_id = request.args.get("barrio_id", "")

    # 2. Empezamos a armar la consulta
    query = Casa.query

    # Filtro de texto libre (Lote/Número)
    if buscar:
        query = query.filter(Casa.numero.ilike(f"%{buscar}%"))

    # Filtro por Estado
    if estado == "activos":
        query = query.filter(Casa.activo == True)
    elif estado == "inactivos":
        query = query.filter(Casa.activo == False)

    # Filtro por Country
    if country_id:
        query = query.filter(Casa.country_id == country_id)

    # Filtro por Barrio
    if barrio_id:
        query = query.filter(Casa.barrio_id == barrio_id)

    # Ejecutamos la búsqueda Y ORDENAMOS
    casas = query.all()
    casas.sort(key=natural_sort_key)

    # 3. Traemos datos para los Selects
    countries = Country.query.filter_by(activo=True).order_by(Country.nombre).all()
    
    barrios = []
    if country_id:
        from app.models.country import Barrio 
        barrios = Barrio.query.filter_by(country_id=country_id, activo=True).order_by(Barrio.nombre).all()

    # Le pasamos todo al HTML
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
# HERRAMIENTA DE AUMENTOS
# ==========================================
@casa_bp.route("/aumento", methods=["GET", "POST"])
@login_required 
def herramienta_aumento():
    if request.method == "POST":
        tipo = request.form.get("tipo")
        country_id = request.form.get("country_id")
        
        try:
            valor = float(request.form.get("valor", 0))
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

        for casa in casas_afectadas:
            try:
                casa.precio_anterior = float(casa.precio_base) if casa.precio_base else 0.0
            except:
                casa.precio_anterior = 0.0
            
            precio_actual = float(casa.precio_base)
            
            if tipo == "porcentaje":
                nuevo = precio_actual * (1 + (valor / 100))
            else:
                nuevo = precio_actual + valor
            
            casa.precio_base = round(nuevo, 2)
            count += 1

        db.session.commit()
        flash(f"✅ Precios actualizados en {count} propiedades.", "success")
        return redirect(url_for("casas.listar_casas"))

    countries = Country.query.filter_by(activo=True).order_by(Country.nombre).all()
    hay_backup = Casa.query.filter(Casa.precio_anterior.isnot(None)).first() is not None
    
    return render_template("casas/aumento.html", countries=countries, hay_backup=hay_backup)

# ==========================================
# DESHACER (VOLVER A LISTA)
# ==========================================
@casa_bp.route("/deshacer_aumento")
@login_required
def deshacer_aumento():
    casas_modificadas = Casa.query.filter(Casa.precio_anterior.isnot(None)).all()
    
    if not casas_modificadas:
        flash("No hay cambios recientes para deshacer.", "warning")
        return redirect(url_for("casas.listar_casas"))
    
    count = 0
    for casa in casas_modificadas:
        casa.precio_base = casa.precio_anterior
        casa.precio_anterior = None
        count += 1
        
    db.session.commit()
    flash(f"⏪ Se deshicieron los cambios en {count} propiedades.", "info")
    return redirect(url_for("casas.listar_casas"))

# ==========================================
# EDITAR CLIENTE
# ==========================================
@casa_bp.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required 
def editar_casa(id):
    casa = Casa.query.get_or_404(id)

    if request.method == "POST":
        numero = request.form.get("numero", "").strip()
        try:
            nuevo_precio = float(request.form.get("precio_base", 0))
        except ValueError:
            flash("El precio debe ser un número válido.", "error")
            return redirect(url_for("casas.editar_casa", id=id))
            
        country_id = request.form.get("country_id")
        barrio_id = request.form.get("barrio_id") or None

        if not numero or not country_id or nuevo_precio < 0:
            flash("Datos inválidos.", "error")
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
        
        if abs(precio_actual_db - nuevo_precio) > 0.01:
            casa.precio_anterior = precio_actual_db
            casa.precio_base = nuevo_precio

        casa.numero = numero
        casa.country_id = country_id
        casa.barrio_id = barrio_id
        
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
def crear_casa():
    if request.method == "POST":
        numeros_input = request.form.get("numero", "").strip()
        precio_base = request.form.get("precio_base", "").strip()
        country_id = request.form.get("country_id")
        barrio_id = request.form.get("barrio_id") or None

        if not numeros_input or not precio_base or not country_id:
            flash("Faltan datos obligatorios.", "error")
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
                barrio_id=barrio_id
            )
            db.session.add(nueva_casa)
            creados += 1

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

@casa_bp.route("/create_form", methods=["GET"]) 
@login_required
def form_crear_casa():
    return crear_casa()

# ==========================================
# UTILIDADES
# ==========================================
@casa_bp.route("/barrios/<int:country_id>")
@login_required
def barrios_por_country(country_id):
    barrios = Barrio.query.filter_by(country_id=country_id, activo=True).order_by(Barrio.nombre).all()
    return jsonify([{"id": b.id, "nombre": b.nombre} for b in barrios])

@casa_bp.route("/toggle/<int:id>")
@login_required
def toggle_casa(id):
    casa = Casa.query.get_or_404(id)
    casa.activo = not casa.activo
    db.session.commit()
    return redirect(url_for("casas.listar_casas"))