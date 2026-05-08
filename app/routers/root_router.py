import os
import subprocess
import threading
import tempfile
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, Response, send_file, abort, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.decorators import root_required
from app.models.user import User
from app.models.casa import Casa, HistorialAumento
from app.models.abono_historico import AbonoHistorico
from app.models.configuracion import Configuracion
from app import db, cache
from datetime import datetime

ALLOWED_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp'}

root_bp = Blueprint("root", __name__, url_prefix="/root")

FLAG_PATH = os.path.join(os.getcwd(), 'mantenimiento.flag')
LOG_AUMENTOS = os.path.join(os.getcwd(), 'registro_aumentos.txt')

# Estado compartido del restore (single-instance, in-memory)
_restore_state = {"status": "idle", "message": ""}  # idle | running | ok | error
_restore_lock = threading.Lock()


_RESET_SEQUENCES_SQL = b"""
DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN
        SELECT sequence_name
        FROM information_schema.sequences
        WHERE sequence_schema = 'public'
    LOOP
        BEGIN
            EXECUTE format(
                'SELECT setval(%L, COALESCE((SELECT MAX(id) FROM %I), 1))',
                r.sequence_name,
                replace(r.sequence_name, '_id_seq', '')
            );
        EXCEPTION WHEN OTHERS THEN NULL;
        END;
    END LOOP;
END $$;
"""


_TRUNCATE_ALL_SQL = b"""
DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public'
    LOOP
        EXECUTE format('TRUNCATE TABLE %I CASCADE', r.tablename);
    END LOOP;
END $$;
"""


def _run_restore_bg(sql_path, cmd, env):
    """Ejecuta psql en background y actualiza _restore_state."""
    global _restore_state
    try:
        with open(sql_path, "rb") as f:
            sql_content = f.read()

        # Si el backup no trae DROP TABLE (backup viejo o de GDrive sin --clean),
        # vaciamos todas las tablas primero para que los INSERTs no fallen en duplicados.
        has_drop = b"DROP TABLE" in sql_content or b"drop table" in sql_content
        if not has_drop:
            pre = subprocess.run(
                cmd, input=_TRUNCATE_ALL_SQL, capture_output=True, env=env, timeout=30
            )
            if pre.returncode != 0:
                err = pre.stderr.decode("utf-8", errors="replace")
                with _restore_lock:
                    _restore_state = {"status": "error", "message": f"Error al limpiar tablas: {err[:200]}"}
                return

        # Deshabilitar FK triggers durante el restore para evitar errores de orden
        # (el backup puede copiar abonos antes que casas, etc.)
        # session_replication_role = replica requiere superusuario (drPiscinas lo es en Docker).
        sql_wrapped = (
            b"SET session_replication_role = replica;\n"
            + sql_content
            + b"\nSET session_replication_role = DEFAULT;\n"
        )

        resultado = subprocess.run(
            cmd, input=sql_wrapped, capture_output=True, env=env, timeout=600
        )
        if resultado.returncode != 0:
            error_msg = resultado.stderr.decode("utf-8", errors="replace")
            with _restore_lock:
                _restore_state = {"status": "error", "message": error_msg[:300]}
            return

        # Resetear secuencias para evitar UniqueViolation en futuros INSERTs
        subprocess.run(
            cmd, input=_RESET_SEQUENCES_SQL, capture_output=True, env=env, timeout=30
        )

        with _restore_lock:
            _restore_state = {"status": "ok", "message": ""}

    except subprocess.TimeoutExpired:
        with _restore_lock:
            _restore_state = {"status": "error", "message": "La restauración tardó más de 10 minutos y fue cancelada."}
    except Exception as e:
        with _restore_lock:
            _restore_state = {"status": "error", "message": str(e)}
    finally:
        try:
            os.unlink(sql_path)
        except OSError:
            pass


# ================================================
# PANEL PRINCIPAL
# ================================================
@root_bp.route("/")
@login_required
@root_required
def panel():
    # ── Estado del sistema ───────────────────────────────────────────────────
    from app.models.configuracion import Configuracion
    modo_mantenimiento = os.path.exists(FLAG_PATH) or bool(Configuracion.get('mantenimiento', False))
    editar_countries = bool(Configuracion.get('editar_countries', False))

    total_clientes = Casa.query.filter_by(activo=True).count()
    total_inactivos = Casa.query.filter_by(activo=False).count()
    total_usuarios = User.query.filter(User.username != 'root').count()
    total_admins = User.query.filter(User.username != 'root', User.rol == 'admin').count()

    # ── Imagen de login ──────────────────────────────────────────────────────
    login_filename = Configuracion.get('login_image_filename', None)
    login_image_exists = False
    if login_filename:
        img_path = os.path.join(current_app.static_folder, 'uploads', login_filename)
        login_image_exists = os.path.exists(img_path)

    # ── Usuarios (sin root) ──────────────────────────────────────────────────
    usuarios = User.query.filter(User.username != 'root').order_by(User.rol, User.username).all()

    # ── Últimos 20 aumentos ──────────────────────────────────────────────────
    ultimos_aumentos = HistorialAumento.query.order_by(
        HistorialAumento.fecha.desc()
    ).limit(20).all()

    # ── Log de aumentos desde archivo ────────────────────────────────────────
    lineas_log = []
    if os.path.exists(LOG_AUMENTOS):
        with open(LOG_AUMENTOS, encoding='utf-8') as f:
            lineas = f.readlines()
        # Mostramos las últimas 50 líneas, sin el encabezado repetido
        lineas_log = [l.strip() for l in lineas if l.strip() and 'CLIENTE' not in l][-50:]
        lineas_log.reverse()

    tipo_dolar = Configuracion.get('tipo_dolar', 'blue')
    stock_activo_desde = Configuracion.get('stock_activo_desde', None)

    return render_template(
        "root/panel.html",
        modo_mantenimiento=modo_mantenimiento,
        editar_countries=editar_countries,
        login_image_exists=login_image_exists,
        total_clientes=total_clientes,
        total_inactivos=total_inactivos,
        total_usuarios=total_usuarios,
        total_admins=total_admins,
        usuarios=usuarios,
        ultimos_aumentos=ultimos_aumentos,
        lineas_log=lineas_log,
        tipo_dolar=tipo_dolar,
        config_stock_activo_desde=stock_activo_desde,
    )


# ================================================
# PREVISUALIZAR PÁGINA DE ERROR 500
# ================================================
@root_bp.route("/test-error-500")
@login_required
@root_required
def test_error_500():
    from flask import render_template as _rt
    return _rt('errors/500.html'), 500


# ================================================
# TOGGLE EDICIÓN DE COUNTRIES
# ================================================
@root_bp.route("/toggle-edicion-countries", methods=["POST"])
@login_required
@root_required
def toggle_edicion_countries():
    actual = bool(Configuracion.get('editar_countries', False))
    Configuracion.set('editar_countries', not actual)
    db.session.commit()
    flash(f"{'✅ Edición de countries activada.' if not actual else '🔒 Edición de countries desactivada.'}", "success" if not actual else "warning")
    return redirect(url_for('root.panel'))


# ================================================
# CONFIGURACIÓN TIPO DE DÓLAR
# ================================================
@root_bp.route("/tipo-dolar", methods=["POST"])
@login_required
@root_required
def set_tipo_dolar():
    tipo = request.form.get("tipo_dolar", "blue")
    if tipo not in ("blue", "mep"):
        flash("Tipo de dólar inválido.", "error")
    else:
        Configuracion.set("tipo_dolar", tipo)
        db.session.commit()
        labels = {"blue": "Dólar Blue", "mep": "Dólar MEP"}
        flash(f"Cotización cambiada a {labels[tipo]}.", "success")
    return redirect(url_for("root.panel"))


# ================================================
# ACTIVAR STOCK OFICIAL
# ================================================
@root_bp.route("/activar-stock", methods=["POST"])
@login_required
@root_required
def activar_stock():
    from app.models.products import Product
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    negativos = Product.query.filter(Product.stock_actual < 0).all()
    for p in negativos:
        p.stock_actual = 0
    Configuracion.set("stock_activo_desde", ahora)
    db.session.commit()
    msg = f"Stock activado desde {ahora}."
    if negativos:
        msg += f" Se resetearon {len(negativos)} producto(s) con stock negativo a 0."
    flash(msg, "success")
    return redirect(url_for("root.panel"))


# ================================================
# TOGGLE MODO MANTENIMIENTO
# ================================================
@root_bp.route("/toggle-mantenimiento", methods=["POST"])
@login_required
@root_required
def toggle_mantenimiento():
    from app.models.configuracion import Configuracion
    if os.path.exists(FLAG_PATH):
        os.remove(FLAG_PATH)
        Configuracion.set('mantenimiento', False)
        db.session.commit()
        flash("✅ Modo mantenimiento desactivado. El sistema está en línea.", "success")
    else:
        with open(FLAG_PATH, 'w') as f:
            f.write(f"Mantenimiento activado por root el {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
        Configuracion.set('mantenimiento', True)
        db.session.commit()
        flash("🔧 Modo mantenimiento activado. Solo root puede navegar.", "warning")
    return redirect(url_for('root.panel'))


# ================================================
# CAMBIO DE ROL DE USUARIO
# ================================================
@root_bp.route("/usuario/<int:id>/toggle-rol", methods=["POST"])
@login_required
@root_required
def toggle_rol(id):
    usuario = User.query.get_or_404(id)
    if usuario.username == 'root':
        flash("No podés modificar al usuario root.", "error")
        return redirect(url_for('root.panel'))

    usuario.rol = 'empleado' if usuario.rol == 'admin' else 'admin'
    db.session.commit()
    nuevo = "Administrador" if usuario.rol == 'admin' else "Empleado"
    flash(f"Rol actualizado: {usuario.username} ahora es {nuevo}.", "success")
    return redirect(url_for('root.panel'))


# ================================================
# RESET DE CONTRASEÑA DE USUARIO
# ================================================
@root_bp.route("/usuario/<int:id>/reset-password", methods=["POST"])
@login_required
@root_required
def reset_password(id):
    usuario = User.query.get_or_404(id)
    if usuario.username == 'root':
        flash("No podés modificar al usuario root desde aquí.", "error")
        return redirect(url_for('root.panel'))

    nueva = request.form.get("nueva_password", "").strip()
    if not nueva:
        flash("La contraseña no puede estar vacía.", "error")
        return redirect(url_for('root.panel'))

    usuario.set_password(nueva)
    db.session.commit()
    flash(f"🔑 Contraseña actualizada para {usuario.username}.", "success")
    return redirect(url_for('root.panel'))


# ================================================
# CREAR USUARIO DESDE EL PANEL ROOT
# ================================================
@root_bp.route("/usuario/crear", methods=["POST"])
@login_required
@root_required
def crear_usuario():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    rol = request.form.get("rol", "empleado").strip()

    if not username or not password:
        flash("Usuario y contraseña son obligatorios.", "error")
        return redirect(url_for('root.panel'))

    if User.query.filter_by(username=username).first():
        flash(f"El usuario '{username}' ya existe.", "error")
        return redirect(url_for('root.panel'))

    nuevo = User(username=username, rol=rol)
    nuevo.set_password(password)
    db.session.add(nuevo)
    db.session.commit()
    flash(f"✅ Usuario '{username}' creado como {rol}.", "success")
    return redirect(url_for('root.panel'))


# ================================================
# ELIMINAR USUARIO
# ================================================
@root_bp.route("/usuario/<int:id>/eliminar", methods=["POST"])
@login_required
@root_required
def eliminar_usuario(id):
    usuario = User.query.get_or_404(id)
    if usuario.username == 'root':
        flash("No podés eliminar al usuario root.", "error")
        return redirect(url_for('root.panel'))

    nombre = usuario.username
    db.session.delete(usuario)
    db.session.commit()
    flash(f"Usuario '{nombre}' eliminado.", "info")
    return redirect(url_for('root.panel'))


# ================================================
# LIMPIAR LOG DE AUMENTOS
# ================================================
@root_bp.route("/limpiar-log", methods=["POST"])
@login_required
@root_required
def limpiar_log():
    if os.path.exists(LOG_AUMENTOS):
        os.remove(LOG_AUMENTOS)
        flash("Log de aumentos limpiado.", "info")
    return redirect(url_for('root.panel'))


# ================================================
# BACKUP DE LA BASE DE DATOS
# ================================================
@root_bp.route("/backup-db")
@login_required
@root_required
def backup_db():
    """
    Genera un pg_dump de la base de datos y lo devuelve como descarga directa.
    Requiere postgresql-client instalado en el container (dockerfile ya lo incluye).
    """
    import urllib.parse as _urlparse

    # Leer credenciales desde la DATABASE_URL o las variables individuales
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        parsed = _urlparse.urlparse(database_url)
        db_user = parsed.username
        db_pass = parsed.password
        db_host = parsed.hostname
        db_port = str(parsed.port or 5432)
        db_name = parsed.path.lstrip("/")
    else:
        db_user = os.getenv("DB_USER", "drPiscinas")
        db_pass = os.getenv("DB_PASS", "administrador")
        db_host = os.getenv("DB_HOST", "db")
        db_port = "5432"
        db_name = os.getenv("DB_NAME", "drPiscinas_db")

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"backup_{timestamp}.sql"

    env = os.environ.copy()
    env["PGPASSWORD"] = db_pass or ""

    try:
        resultado = subprocess.run(
            [
                "pg_dump",
                "-h", db_host,
                "-p", db_port,
                "-U", db_user,
                "-d", db_name,
                "--no-password",
                "--format=plain",
                "--encoding=UTF8",
                "--clean",       # genera DROP TABLE IF EXISTS antes de cada CREATE
                "--if-exists",   # evita errores si la tabla no existe al hacer DROP
            ],
            capture_output=True,
            env=env,
            timeout=60,
        )

        if resultado.returncode != 0:
            error_msg = resultado.stderr.decode("utf-8", errors="replace")
            flash(f"❌ Error al generar el backup: {error_msg[:200]}", "error")
            return redirect(url_for("root.panel"))

        sql_content = resultado.stdout

        # Guardar también una copia local en sueltos/
        backup_dir = os.path.join(os.getcwd(), "sueltos")
        os.makedirs(backup_dir, exist_ok=True)
        with open(os.path.join(backup_dir, filename), "wb") as f:
            f.write(sql_content)

        return Response(
            sql_content,
            mimetype="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": len(sql_content),
            }
        )

    except FileNotFoundError:
        flash("❌ pg_dump no está disponible. Reconstruí el container con 'docker compose build'.", "error")
        return redirect(url_for("root.panel"))
    except subprocess.TimeoutExpired:
        flash("❌ El backup tardó demasiado y fue cancelado.", "error")
        return redirect(url_for("root.panel"))
    except Exception as e:
        flash(f"❌ Error inesperado: {str(e)}", "error")
        return redirect(url_for("root.panel"))


# ================================================
# RESTAURAR BACKUP DE LA BASE DE DATOS
# ================================================
@root_bp.route("/restore-db", methods=["POST"])
@login_required
@root_required
def restore_db():
    """
    Recibe un archivo .sql y lo inyecta en la base de datos via psql en background.
    OPERACIÓN DESTRUCTIVA: sobreescribe datos existentes.
    """
    import urllib.parse as _urlparse
    global _restore_state

    with _restore_lock:
        if _restore_state["status"] == "running":
            flash("Ya hay una restauración en curso. Esperá a que termine.", "error")
            return redirect(url_for("root.panel"))

    archivo = request.files.get("backup_file")
    if not archivo or archivo.filename == "":
        flash("No se seleccionó ningún archivo.", "error")
        return redirect(url_for("root.panel"))

    ext = os.path.splitext(secure_filename(archivo.filename))[1].lower()
    if ext != ".sql":
        flash("Solo se aceptan archivos .sql", "error")
        return redirect(url_for("root.panel"))

    # Leer credenciales
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        parsed = _urlparse.urlparse(database_url)
        db_user = parsed.username
        db_pass = parsed.password
        db_host = parsed.hostname
        db_port = str(parsed.port or 5432)
        db_name = parsed.path.lstrip("/")
    else:
        db_user = os.getenv("DB_USER", "drPiscinas")
        db_pass = os.getenv("DB_PASS", "administrador")
        db_host = os.getenv("DB_HOST", "db")
        db_port = "5432"
        db_name = os.getenv("DB_NAME", "drPiscinas_db")

    # Guardar SQL en archivo temporal (el thread lo limpia al terminar)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sql")
    archivo.save(tmp.name)
    tmp.close()

    env = os.environ.copy()
    env["PGPASSWORD"] = db_pass or ""

    cmd = ["psql", "-h", db_host, "-p", db_port, "-U", db_user, "-d", db_name, "--no-password"]

    with _restore_lock:
        _restore_state = {"status": "running", "message": ""}

    t = threading.Thread(target=_run_restore_bg, args=(tmp.name, cmd, env), daemon=True)
    t.start()

    flash("⏳ Restauración iniciada. La página se actualizará automáticamente cuando termine.", "info")
    return redirect(url_for("root.panel"))


@root_bp.route("/restore-status")
@login_required
@root_required
def restore_status():
    """Devuelve el estado actual del restore en JSON para polling desde el frontend."""
    global _restore_state
    with _restore_lock:
        state = dict(_restore_state)
        if state["status"] in ("ok", "error"):
            _restore_state = {"status": "idle", "message": ""}
    return jsonify(state)


# ================================================
# GUARDAR NÚMERO WA NOTIFICACIÓN ERRORES
# ================================================
@root_bp.route("/wa-error", methods=["POST"])
@login_required
@root_required
def set_wa_error():
    import re
    numero = request.form.get("wa_numero_error", "").strip()
    numero = re.sub(r'\D', '', numero)
    numero = numero.lstrip('549') if numero.startswith('549') else numero
    nombre = request.form.get("wa_nombre_error", "").strip()
    Configuracion.set("wa_numero_error", numero)
    Configuracion.set("wa_nombre_error", nombre)
    db.session.commit()
    cache.delete("_cfg_data")
    flash("✅ Configuración de WhatsApp actualizada.", "success")
    return redirect(url_for("root.panel"))


# ================================================
# GUARDAR CONFIGURACIÓN DEL FOOTER
# ================================================
@root_bp.route("/footer", methods=["POST"])
@login_required
@root_required
def set_footer():
    texto    = request.form.get("footer_texto", "").strip()
    contacto = request.form.get("footer_contacto", "").strip()
    Configuracion.set("footer_texto", texto)
    Configuracion.set("footer_contacto", contacto)
    db.session.commit()
    flash("✅ Footer actualizado.", "success")
    return redirect(url_for("root.panel"))


# ================================================
# SERVIR ICONO 192px
# ================================================
@root_bp.route("/icon/192")
def icon_192():
    """Sirve el ícono de 192px de la app."""
    path = os.path.join(current_app.static_folder, 'drpiscina-192.png')
    if os.path.exists(path):
        return send_file(path, mimetype='image/png')
    abort(404)


# ================================================
# SERVIR IMAGEN DE LOGIN
# ================================================
@root_bp.route("/login-image")
def serve_login_image():
    """Sirve la imagen de fondo del login."""
    login_filename = Configuracion.get('login_image_filename', None)
    if not login_filename:
        abort(404)
    path = os.path.join(current_app.static_folder, 'uploads', login_filename)
    if not os.path.exists(path):
        abort(404)
    ext = os.path.splitext(login_filename)[1].lower()
    mimetypes = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}
    return send_file(path, mimetype=mimetypes.get(ext, 'image/jpeg'))


# ================================================
# SUBIR IMAGEN DE LOGIN
# ================================================
@root_bp.route("/login-image/upload", methods=["POST"])
@login_required
@root_required
def upload_login_image():
    """Recibe y guarda la imagen de fondo del login."""
    archivo = request.files.get('login_image')
    if not archivo or archivo.filename == '':
        flash("No se seleccionó ningún archivo.", "error")
        return redirect(url_for('root.panel'))

    ext = os.path.splitext(secure_filename(archivo.filename))[1].lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        flash("Formato no soportado. Usá JPG, PNG o WebP.", "error")
        return redirect(url_for('root.panel'))

    uploads_dir = os.path.join(current_app.static_folder, 'uploads')
    os.makedirs(uploads_dir, exist_ok=True)

    # Eliminar imagen anterior si existe
    old_filename = Configuracion.get('login_image_filename', None)
    if old_filename:
        old_path = os.path.join(uploads_dir, old_filename)
        if os.path.exists(old_path):
            os.remove(old_path)

    filename = f"login_bg{ext}"
    archivo.save(os.path.join(uploads_dir, filename))

    Configuracion.set('login_image_filename', filename)
    db.session.commit()

    flash("✅ Imagen del login actualizada correctamente.", "success")
    return redirect(url_for('root.panel'))


# ================================================
# ELIMINAR IMAGEN DE LOGIN
# ================================================
@root_bp.route("/login-image/remove", methods=["POST"])
@login_required
@root_required
def remove_login_image():
    """Elimina la imagen de fondo del login."""
    login_filename = Configuracion.get('login_image_filename', None)
    if login_filename:
        path = os.path.join(current_app.static_folder, 'uploads', login_filename)
        if os.path.exists(path):
            os.remove(path)
        Configuracion.set('login_image_filename', None)
        db.session.commit()
        flash("Imagen del login eliminada.", "info")
    else:
        flash("No había imagen para eliminar.", "warning")
    return redirect(url_for('root.panel'))
