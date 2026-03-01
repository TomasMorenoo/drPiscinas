from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required
from app.decorators import admin_required
from app import db
from app.models.casa import Casa
from app.models.grupo import GrupoCliente

grupo_bp = Blueprint("grupos", __name__, url_prefix="/grupos")

@grupo_bp.route("/create", methods=["GET", "POST"])
@login_required
@admin_required
def crear_grupo():
    if request.method == "POST":
        nombre_grupo = request.form.get("nombre")
        casas_seleccionadas = request.form.getlist("casas_ids[]")
        
        if not nombre_grupo or not casas_seleccionadas:
            flash("Debes ingresar un nombre y seleccionar al menos una casa.", "error")
            return redirect(url_for("grupos.crear_grupo"))
            
        nuevo_grupo = GrupoCliente(nombre=nombre_grupo)
        db.session.add(nuevo_grupo)
        db.session.commit() # Obtenemos el ID
        
        # Asignamos el grupo a las casas elegidas
        for casa_id in casas_seleccionadas:
            casa = Casa.query.get(casa_id)
            if casa:
                casa.grupo_id = nuevo_grupo.id
                
        db.session.commit()
        flash(f"Grupo '{nombre_grupo}' creado exitosamente.", "success")
        return redirect(url_for("dashboard.index"))
        
    return render_template("grupos/create.html")

@grupo_bp.route("/api/buscar_por_telefono")
@login_required
def buscar_por_telefono():
    telefono = request.args.get("telefono", "").strip()
    if not telefono:
        return jsonify([])
        
    # Buscamos casas que coincidan con el teléfono y que NO tengan grupo asignado
    casas = Casa.query.filter(Casa.telefono.ilike(f"%{telefono}%"), Casa.grupo_id == None).all()
    
    resultados = []
    for c in casas:
        resultados.append({
            "id": c.id,
            "nombre": c.nombre_formateado(),
            "cliente": c.nombre_cliente or "Sin nombre",
            "abono": float(c.precio_base)
        })
        
    return jsonify(resultados)