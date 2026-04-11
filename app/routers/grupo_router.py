from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required
from app.decorators import admin_required
from app import db
from app.models.casa import Casa
from app.models.grupo import GrupoCliente

grupo_bp = Blueprint("grupos", __name__, url_prefix="/grupos")

@grupo_bp.route("/")
@login_required
@admin_required
def listar_grupos():
    grupos = GrupoCliente.query.all()
    return render_template("grupos/list.html", grupos=grupos)

@grupo_bp.route("/create", methods=["GET", "POST"])
@login_required
@admin_required
def crear_grupo():
    if request.method == "POST":
        nombre_grupo = request.form.get("nombre")
        nombre_id = request.form.get("nombre_identificador", "").strip() or None
        casas_seleccionadas = request.form.getlist("casas_ids[]")

        if not nombre_grupo or not casas_seleccionadas:
            flash("Debes ingresar un nombre y seleccionar al menos una casa.", "error")
            return redirect(url_for("grupos.crear_grupo"))

        nuevo_grupo = GrupoCliente(nombre=nombre_grupo, nombre_identificador=nombre_id)
        db.session.add(nuevo_grupo)
        db.session.commit()
        
        for casa_id in casas_seleccionadas:
            casa = Casa.query.get(casa_id)
            if casa:
                casa.grupo_id = nuevo_grupo.id
                
        db.session.commit()
        flash(f"Grupo '{nombre_grupo}' creado exitosamente.", "success")
        return redirect(url_for("grupos.listar_grupos"))
        
    # ESTO ES LO NUEVO: Le pasamos las casas sueltas al HTML para el select manual
    casas_libres = Casa.query.filter_by(grupo_id=None, activo=True).order_by(Casa.country_id).all()
    return render_template("grupos/create.html", casas_libres=casas_libres)

@grupo_bp.route("/editar/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def editar_grupo(id):
    grupo = GrupoCliente.query.get_or_404(id)
    if request.method == "POST":
        nuevo_nombre = request.form.get("nombre")
        nombre_id = request.form.get("nombre_identificador", "").strip() or None
        if nuevo_nombre:
            grupo.nombre = nuevo_nombre
            grupo.nombre_identificador = nombre_id
            db.session.commit()
            flash("Nombres del grupo actualizados.", "success")
        return redirect(url_for("grupos.editar_grupo", id=grupo.id))
        
    casas_libres = Casa.query.filter_by(grupo_id=None, activo=True).order_by(Casa.country_id).all()
    return render_template("grupos/edit.html", grupo=grupo, casas_libres=casas_libres)

@grupo_bp.route("/agregar_casa/<int:grupo_id>", methods=["POST"])
@login_required
@admin_required
def agregar_casa(grupo_id):
    casa_id = request.form.get("casa_id")
    casa = Casa.query.get(casa_id)
    if casa:
        casa.grupo_id = grupo_id
        db.session.commit()
        flash("Casa incorporada al grupo.", "success")
    return redirect(url_for("grupos.editar_grupo", id=grupo_id))

@grupo_bp.route("/quitar_casa/<int:casa_id>", methods=["POST"])
@login_required
@admin_required
def quitar_casa(casa_id):
    casa = Casa.query.get_or_404(casa_id)
    grupo_id = casa.grupo_id
    casa.grupo_id = None
    db.session.commit()
    flash("Casa removida del grupo.", "info")
    return redirect(url_for("grupos.editar_grupo", id=grupo_id))

@grupo_bp.route("/eliminar/<int:id>", methods=["POST"])
@login_required
@admin_required
def eliminar_grupo(id):
    grupo = GrupoCliente.query.get_or_404(id)
    # Liberamos a las casas primero
    for c in grupo.casas:
        c.grupo_id = None
    db.session.delete(grupo)
    db.session.commit()
    flash("Grupo desarmado. Las casas pasaron a ser individuales.", "success")
    return redirect(url_for("grupos.listar_grupos"))

@grupo_bp.route("/api/buscar_por_telefono")
@login_required
def buscar_por_telefono():
    telefono = request.args.get("telefono", "").strip()
    if not telefono:
        return jsonify([])
    casas = Casa.query.filter(Casa.telefono.ilike(f"%{telefono}%"), Casa.grupo_id == None).all()
    resultados = [{"id": c.id, "nombre": c.nombre_formateado(), "cliente": c.nombre_cliente or "Sin nombre", "abono": float(c.precio_base)} for c in casas]
    return jsonify(resultados)