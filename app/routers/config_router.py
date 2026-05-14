from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app import db
from app.decorators import admin_required
from app.models.plantilla_mensaje import PlantillaMensaje, DEFAULT_TEMPLATE_INDIVIDUAL, DEFAULT_TEMPLATE_GRUPO, DEFAULT_TEMPLATE_RECORDATORIO

config_bp = Blueprint("config", __name__, url_prefix="/config")


@config_bp.route("/mensajes")
@login_required
@admin_required
def listar_plantillas():
    plantillas = PlantillaMensaje.query.order_by(PlantillaMensaje.activa.desc(), PlantillaMensaje.creada_en.desc()).all()
    return render_template("config/mensajes.html", plantillas=plantillas)


@config_bp.route("/mensajes/nueva", methods=["GET", "POST"])
@login_required
@admin_required
def crear_plantilla():
    if request.method == "POST":
        p = PlantillaMensaje(
            nombre                = request.form.get("nombre", "").strip(),
            template_individual   = request.form.get("template_individual", "").strip() or None,
            template_grupo        = request.form.get("template_grupo", "").strip() or None,
            template_recordatorio = request.form.get("template_recordatorio", "").strip() or None,
        )
        if not p.nombre:
            flash("El nombre es obligatorio.", "error")
            return render_template("config/mensajes_form.html", plantilla=p,
                                   default_individual=DEFAULT_TEMPLATE_INDIVIDUAL,
                                   default_grupo=DEFAULT_TEMPLATE_GRUPO,
                                   default_recordatorio=DEFAULT_TEMPLATE_RECORDATORIO, accion="nueva")
        db.session.add(p)
        db.session.commit()
        flash(f"Plantilla '{p.nombre}' creada.", "success")
        return redirect(url_for("config.listar_plantillas"))

    defaults = PlantillaMensaje()
    return render_template("config/mensajes_form.html", plantilla=defaults,
                           default_individual=DEFAULT_TEMPLATE_INDIVIDUAL,
                           default_grupo=DEFAULT_TEMPLATE_GRUPO,
                           default_recordatorio=DEFAULT_TEMPLATE_RECORDATORIO, accion="nueva")


@config_bp.route("/mensajes/<int:id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def editar_plantilla(id):
    p = PlantillaMensaje.query.get_or_404(id)

    if request.method == "POST":
        p.nombre                = request.form.get("nombre", "").strip()
        p.template_individual   = request.form.get("template_individual", "").strip() or None
        p.template_grupo        = request.form.get("template_grupo", "").strip() or None
        p.template_recordatorio = request.form.get("template_recordatorio", "").strip() or None

        if not p.nombre:
            flash("El nombre es obligatorio.", "error")
            return render_template("config/mensajes_form.html", plantilla=p,
                                   default_individual=DEFAULT_TEMPLATE_INDIVIDUAL,
                                   default_grupo=DEFAULT_TEMPLATE_GRUPO,
                                   default_recordatorio=DEFAULT_TEMPLATE_RECORDATORIO, accion="editar")
        db.session.commit()
        flash(f"Plantilla '{p.nombre}' guardada.", "success")
        return redirect(url_for("config.listar_plantillas"))

    return render_template("config/mensajes_form.html", plantilla=p,
                           default_individual=DEFAULT_TEMPLATE_INDIVIDUAL,
                           default_grupo=DEFAULT_TEMPLATE_GRUPO,
                           default_recordatorio=DEFAULT_TEMPLATE_RECORDATORIO, accion="editar")


@config_bp.route("/mensajes/<int:id>/activar", methods=["POST"])
@login_required
@admin_required
def activar_plantilla(id):
    p = PlantillaMensaje.query.get_or_404(id)
    p.activar()
    db.session.commit()
    flash(f"Plantilla '{p.nombre}' activada.", "success")
    return redirect(url_for("config.listar_plantillas"))


@config_bp.route("/mensajes/<int:id>/eliminar", methods=["POST"])
@login_required
@admin_required
def eliminar_plantilla(id):
    p = PlantillaMensaje.query.get_or_404(id)
    if p.activa:
        flash("No podés eliminar la plantilla activa.", "error")
        return redirect(url_for("config.listar_plantillas"))
    nombre = p.nombre
    db.session.delete(p)
    db.session.commit()
    flash(f"Plantilla '{nombre}' eliminada.", "success")
    return redirect(url_for("config.listar_plantillas"))
