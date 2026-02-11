from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required # <--- 1. IMPORTAR SEGURIDAD
from app import db
from app.models import Casa, Country, Barrio
import re 

casa_bp = Blueprint("casas", __name__, url_prefix="/casas")

# ==========================================
# LÓGICA DE ORDENAMIENTO
# ==========================================
def natural_sort_key(casa):
    k_country = casa.country.nombre.lower() if casa.country else "zzz"
    k_barrio = casa.barrio.nombre.lower() if casa.barrio else ""
    k_numero = [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', casa.numero)]
    return (k_country, k_barrio, k_numero)

# ==========================================
# LISTADO
# ==========================================
@casa_bp.route("/")
@login_required # <--- CANDADO PUESTO
def listar_casas():
    casas_db = Casa.query.all()
    casas = sorted(casas_db, key=natural_sort_key)
    return render_template("casas/list.html", casas=casas)

# ==========================================
# HERRAMIENTA DE AUMENTOS
# ==========================================
@casa_bp.route("/aumento", methods=["GET", "POST"])
@login_required # <--- CANDADO PUESTO
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
            # 1. SNAPSHOT (Convertimos a float para evitar conflictos)
            try:
                casa.precio_anterior = float(casa.precio_base) if casa.precio_base else 0.0
            except:
                casa.precio_anterior = 0.0
            
            # 2. CALCULAR
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
@login_required # <--- CANDADO PUESTO
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
# EDITAR CLIENTE (CORREGIDO ERROR DECIMAL)
# ==========================================
@casa_bp.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required # <--- CANDADO PUESTO
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

        # --- CORRECCIÓN CRÍTICA ---
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
# CREAR
# ==========================================
@casa_bp.route("/create", methods=["GET", "POST"])
@login_required # <--- CANDADO PUESTO
def crear_casa():
    if request.method == "POST":
        numero = request.form.get("numero", "").strip()
        precio_base = request.form.get("precio_base", "").strip()
        country_id = request.form.get("country_id")
        barrio_id = request.form.get("barrio_id") or None

        if not numero or not precio_base or not country_id:
            flash("Faltan datos obligatorios.", "error")
            return redirect(url_for("casas.crear_casa"))

        query = Casa.query.filter_by(numero=numero, country_id=country_id)
        if barrio_id:
            query = query.filter_by(barrio_id=barrio_id)
        else:
            query = query.filter_by(barrio_id=None)
            
        if query.first():
            flash("Esa casa ya existe.", "error")
            return redirect(url_for("casas.listar_casas"))

        nueva_casa = Casa(numero=numero, precio_base=precio_base, country_id=country_id, barrio_id=barrio_id)
        db.session.add(nueva_casa)
        db.session.commit()
        flash("Cliente creado.", "success")
        return redirect(url_for("casas.listar_casas"))

    countries = Country.query.filter_by(activo=True).order_by(Country.nombre).all()
    barrios = Barrio.query.filter_by(activo=True).order_by(Barrio.nombre).all()
    return render_template("casas/create.html", countries=countries, barrios=barrios)

@casa_bp.route("/create_form", methods=["GET"]) 
@login_required # <--- CANDADO PUESTO
def form_crear_casa():
    return crear_casa()

# ==========================================
# UTILIDADES
# ==========================================
@casa_bp.route("/barrios/<int:country_id>")
@login_required # <--- CANDADO PUESTO (Para que no espíen tu API interna)
def barrios_por_country(country_id):
    barrios = Barrio.query.filter_by(country_id=country_id, activo=True).order_by(Barrio.nombre).all()
    return jsonify([{"id": b.id, "nombre": b.nombre} for b in barrios])

@casa_bp.route("/toggle/<int:id>")
@login_required # <--- CANDADO PUESTO
def toggle_casa(id):
    casa = Casa.query.get_or_404(id)
    casa.activo = not casa.activo
    db.session.commit()
    return redirect(url_for("casas.listar_casas"))