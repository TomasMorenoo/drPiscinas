from app import db
from datetime import datetime
import re

DEFAULT_TEMPLATE_INDIVIDUAL = """{saludo} como te va, te recuerdo el abono de la pile

{resumen_total}

Detalle:
Mes de mantenimiento: ${mantenimiento}
Productos Utilizados: ${extras}
{detalle_productos}
Proporcional mes de mantenimiento: ${proporcional}
Productos Utilizados: ${extras_proporcional}
{detalle_proporcional}
Proporcional mes pasado de mantenimiento: ${proporcional_anterior}
Productos Utilizados el mes pasado: ${extras_proporcional_anterior}
{detalle_proporcional_anterior}
Saldo adeudado de meses anteriores: ${saldo_anterior}
Saldo a favor aplicado: -${saldo_favor}
Entregado este mes: -${pagado}

Muchas Gracias."""

DEFAULT_TEMPLATE_RECORDATORIO = """{saludo}, le recordamos que aún tiene pendiente el pago de *${deuda}* correspondiente a {mes} {anio}.
Por favor regularice a la brevedad.
Muchas Gracias."""

DEFAULT_TEMPLATE_GRUPO = """{saludo} Te paso el resumen de las {cant} propiedades.

{resumen_total}

{lista_casas}
Saldo adeudado de meses anteriores: ${saldo_anterior}
Entregado este mes: *-${pagado}*
(*) El total ya incluye un descuento de ${saldo_favor} por saldo a favor acumulado.

Muchas Gracias."""

# Variables que ocultan su línea completa si el valor numérico es 0
VARS_CONDICIONALES = {'mantenimiento', 'extras', 'detalle_productos',
                      'proporcional', 'extras_proporcional', 'detalle_proporcional',
                      'proporcional_anterior', 'extras_proporcional_anterior', 'detalle_proporcional_anterior',
                      'saldo_anterior', 'pagado', 'saldo_favor'}


def renderizar_template(template_str, variables):
    """
    variables: dict { nombre_var: (str_valor, num_valor_o_None) }
    Si num_valor <= 0 y la variable es condicional, la línea se oculta.
    """
    lines = template_str.split('\n')
    result = []

    for line in lines:
        skip = False
        for var_name in VARS_CONDICIONALES:
            if '{' + var_name + '}' in line:
                _, num_val = variables.get(var_name, ('', 0))
                if num_val is None or float(num_val) <= 0.01:
                    skip = True
                    break
        if skip:
            continue

        for var_name, (str_val, _) in variables.items():
            line = line.replace('{' + var_name + '}', str_val)

        result.append(line)

    output = '\n'.join(result)
    output = re.sub(r'\n{3,}', '\n\n', output)
    return output.strip()


class PlantillaMensaje(db.Model):
    __tablename__ = "plantillas_mensaje"

    id          = db.Column(db.Integer, primary_key=True)
    nombre      = db.Column(db.String(100), nullable=False)
    activa      = db.Column(db.Boolean, default=False, nullable=False)
    creada_en   = db.Column(db.DateTime, default=datetime.utcnow)

    # Columnas legacy (ya no se usan en generación, se mantienen para no romper la tabla)
    texto_intro_individual  = db.Column(db.Text)
    label_al_dia            = db.Column(db.String(200))
    label_total             = db.Column(db.String(200))
    label_detalle           = db.Column(db.String(200))
    label_mantenimiento     = db.Column(db.String(200))
    label_productos         = db.Column(db.String(200))
    label_saldo_anterior    = db.Column(db.String(200))
    label_entregado         = db.Column(db.String(200))
    cierre                  = db.Column(db.String(200))
    texto_intro_grupo       = db.Column(db.Text)
    label_saldo_favor       = db.Column(db.Text)

    # Nuevas columnas: templates libres
    template_individual     = db.Column(db.Text)
    template_grupo          = db.Column(db.Text)
    template_recordatorio   = db.Column(db.Text)

    @classmethod
    def get_activa(cls):
        p = cls.query.filter_by(activa=True).first()
        return p if p else cls()

    def get_template_individual(self):
        return self.template_individual or DEFAULT_TEMPLATE_INDIVIDUAL

    def get_template_grupo(self):
        return self.template_grupo or DEFAULT_TEMPLATE_GRUPO

    def get_template_recordatorio(self):
        return self.template_recordatorio or DEFAULT_TEMPLATE_RECORDATORIO

    def activar(self):
        PlantillaMensaje.query.update({"activa": False})
        self.activa = True
