from app import db
from sqlalchemy import UniqueConstraint

class Casa(db.Model):
    __tablename__ = "casas"

    __table_args__ = (
        UniqueConstraint(
            "country_id",
            "barrio_id",
            "numero",
            name="uq_casa_country_barrio_numero"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), nullable=False)
    precio_base = db.Column(db.Numeric(10, 2), nullable=False)
    precio_anterior = db.Column(db.Float, nullable=True)
    activo = db.Column(db.Boolean, default=True)
    nombre_cliente = db.Column(db.String(100), nullable=True)
    telefono = db.Column(db.String(50), nullable=True)
    
    country_id = db.Column(
        db.Integer,
        db.ForeignKey("countries.id"),
        nullable=False
    )

    barrio_id = db.Column(
        db.Integer,
        db.ForeignKey("barrios.id"),
        nullable=True
    )
    
    grupo_id = db.Column(db.Integer, db.ForeignKey("grupos_clientes.id"), nullable=True)
    grupo = db.relationship("GrupoCliente", backref=db.backref("casas", lazy=True))

    def __repr__(self):
        return f"<Casa {self.numero}>"
    
    def obtener_gastos_mensuales(self, mes, anio):
        from app.models.abono_historico import AbonoHistorico
        total_extras = 0
        mes_cerrado = AbonoHistorico.query.filter_by(mes=mes, anio=anio).first() is not None

        for visita in self.visitas:
            if visita.fecha.month == mes and visita.fecha.year == anio:
                for vp in visita.productos:
                    if mes_cerrado and vp.precio_unitario:
                        total_extras += float(vp.cantidad) * float(vp.precio_unitario)
                    else:
                        total_extras += float(vp.cantidad) * float(vp.product.precio)
                
                if visita.promo:
                    total_extras += float(visita.promo.precio)
                    
        return {
            "abono": float(self.precio_base),
            "extras": round(total_extras, 2),
            "total": round(float(self.precio_base) + total_extras, 2)
        }

    def nombre_formateado(self):
        if self.barrio:
            return f"{self.barrio.nombre} {self.numero}"
        return f"{self.country.nombre} {self.numero}"
    
    def obtener_saldo_anterior(self, mes, anio):
        """Calcula la deuda o saldo a favor acumulado usando los precios históricos congelados"""
        saldo = 0.0
        
        # Ordenamos cronológicamente para que la plata fluya en el tiempo
        historiales_ordenados = sorted(self.historial_abonos, key=lambda x: (x.anio, x.mes))
        
        for hist in historiales_ordenados:
            if hist.anio < anio or (hist.anio == anio and hist.mes < mes):
                # FIX CRÍTICO: Usamos el MONTO HISTÓRICO CONGELADO, no el precio actual
                abono_hist = float(hist.monto)
                
                # Calculamos los extras usando solo las visitas de ese mes específico
                extras_hist = 0.0
                for visita in self.visitas:
                    if visita.fecha.month == hist.mes and visita.fecha.year == hist.anio:
                        for vp in visita.productos:
                            if vp.precio_unitario:
                                extras_hist += float(vp.cantidad) * float(vp.precio_unitario)
                            else:
                                extras_hist += float(vp.cantidad) * float(vp.product.precio)
                        if visita.promo:
                            extras_hist += float(visita.promo.precio)
                
                total_hist = abono_hist + extras_hist
                pagado_hist = float(getattr(hist, 'monto_pagado', 0) or 0)
                
                saldo += total_hist
                saldo -= pagado_hist
                
                # Compatibilidad: Si se marcó como pagado con el botón viejo (sin monto), reseteamos la deuda
                if getattr(hist, 'pagado', False) and pagado_hist == 0 and saldo > 0.01:
                    saldo = 0.0
                    
        return round(saldo, 2)