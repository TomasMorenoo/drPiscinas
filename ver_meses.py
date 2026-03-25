from app import create_app
from app.models.cierre_mes import CierreMes

# Inicializamos la app para poder hablar con la base de datos
app = create_app()

with app.app_context():
    # Buscamos todos los registros de la tabla CierreMes
    meses_cerrados = CierreMes.query.order_by(CierreMes.anio, CierreMes.mes).all()
    
    print("\n" + "="*30)
    print("🔒 ESTADO DE MESES CERRADOS 🔒")
    print("="*30)
    
    if not meses_cerrados:
        print("🟢 No hay NINGÚN mes cerrado en la base de datos.")
    else:
        for cierre in meses_cerrados:
            print(f"🔴 CERRADO -> Mes: {cierre.mes:02d} | Año: {cierre.anio}")
            
    print("="*30 + "\n")