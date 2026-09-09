from app import create_app, db
from app.models.plantilla_mensaje import (
    PlantillaMensaje,
    DEFAULT_TEMPLATE_INDIVIDUAL,
    DEFAULT_TEMPLATE_GRUPO,
)


def actualizar_plantillas():
    app = create_app()
    with app.app_context():
        plantilla = PlantillaMensaje.query.filter_by(activa=True).first()
        if plantilla is None:
            plantilla = PlantillaMensaje(nombre="Dr. Piscinas", activa=True)
            db.session.add(plantilla)
        plantilla.template_individual = DEFAULT_TEMPLATE_INDIVIDUAL
        plantilla.template_grupo = DEFAULT_TEMPLATE_GRUPO
        db.session.commit()
        print("Plantillas individual y grupal actualizadas.")


if __name__ == "__main__":
    actualizar_plantillas()
