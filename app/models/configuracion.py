from app import db
import json


class Configuracion(db.Model):
    """
    Tabla de clave-valor para guardar configuraciones persistentes de la app.
    Sobrevive reinicios del contenedor, F5 y cambios de sesión.
    """
    __tablename__ = "configuraciones"

    clave = db.Column(db.String(100), primary_key=True)
    valor = db.Column(db.Text, nullable=True)

    @classmethod
    def get(cls, clave, default=None):
        """Devuelve el valor ya decodificado desde JSON, o el default si no existe."""
        registro = cls.query.filter_by(clave=clave).first()
        if registro is None or registro.valor is None:
            return default
        try:
            return json.loads(registro.valor)
        except (ValueError, TypeError):
            return registro.valor

    @classmethod
    def set(cls, clave, valor):
        """Guarda o actualiza el valor (lo convierte a JSON automáticamente)."""
        registro = cls.query.filter_by(clave=clave).first()
        valor_serializado = json.dumps(valor, ensure_ascii=False)
        if registro:
            registro.valor = valor_serializado
        else:
            db.session.add(cls(clave=clave, valor=valor_serializado))
