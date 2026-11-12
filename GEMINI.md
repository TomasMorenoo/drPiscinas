# Reglas del Proyecto Dr. Piscinas

## Control de Versiones Continuo (Semantic Versioning)
- **Versión base actual**: `V2.1.0`.
- Cada vez que realices una tarea, corrección de bugs, mejora de UI o nueva funcionalidad en el código, **debes actualizar y nombrar explícitamente la versión del sistema** para no perder el hilo:
  1. **Parches y arreglos menores (`PATCH`)**: Incrementa el último dígito (ej: `V2.1.0` → `V2.1.1` → `V2.1.2`).
  2. **Nuevos módulos o features relevantes (`MINOR`)**: Incrementa el segundo dígito (ej: `V2.1.x` → `V2.2.0`).
  3. **Actualización en el código**: Asegura que el valor de `app_version` en `app/app/__init__.py` y/o en la base de datos (`Configuracion.set("app_version", "V...")`) refleje la nueva versión para que se visualice correctamente en la pantalla de login.
  4. **Respuesta obligatoria al usuario**: En cada entrega o respuesta final donde se hayan aplicado cambios, **debes comenzar o titular tu respuesta con la versión alcanzada**, por ejemplo:
     `### [V2.1.1] Descripción de los cambios...`
  5. **Commits de Git**: Si se realizan commits, incluir la versión resultante al final del mensaje de commit (ej: `fix(visitas): corregir orden natural de lotes (V2.1.1)`).
