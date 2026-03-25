from app import create_app, db
from app.models.casa import Casa
from app.models.abono_historico import AbonoHistorico

app = create_app()

with app.app_context():
    print("🔍 Buscando saldos 'fantasma' en la base de datos...")
    casas = Casa.query.all()
    arregladas = 0
    
    for casa in casas:
        # Calculamos el saldo absoluto de la casa hasta el futuro (todo su historial real)
        saldo_total = casa.obtener_saldo_anterior(1, 3000)
        
        # Si el saldo total es 0 (o a favor), el cliente NO DEBE NADA.
        if saldo_total <= 0.01:
            # Buscamos si la base de datos le dejó meses colgados como impagos
            meses_impagos = AbonoHistorico.query.filter_by(casa_id=casa.id, pagado=False).all()
            
            if meses_impagos:
                for mes in meses_impagos:
                    mes.pagado = True  # Forzamos el tilde verde en el historial viejo
                arregladas += 1
                print(f"✔️ Arreglada: {casa.nombre_formateado()} (Tenía {len(meses_impagos)} meses colgados)")
                
    db.session.commit()
    print(f"\n🚀 ¡Limpieza terminada! Se corrigió el historial de {arregladas} propiedades.")