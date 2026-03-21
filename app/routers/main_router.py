from flask import Blueprint, render_template, send_from_directory, current_app
from flask_login import login_required

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
@login_required
def home():
    return render_template("home.html")

# NUEVA RUTA PARA LA APP INSTALABLE
@main_bp.route('/sw.js')
def sw():
    return send_from_directory(current_app.static_folder, 'sw.js')