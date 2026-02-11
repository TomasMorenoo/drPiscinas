from flask import Blueprint, render_template
from flask_login import login_required # <--- 1. IMPORTAR SEGURIDAD

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
@login_required # <--- CANDADO PUESTO (Rebota al Login si no entraste)
def home():
    return render_template("home.html")