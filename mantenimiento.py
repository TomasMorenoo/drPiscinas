import os

FLAG_FILE = "mantenimiento.flag"

if os.path.exists(FLAG_FILE):
    os.remove(FLAG_FILE)
    print("🟢 MODO MANTENIMIENTO DESACTIVADO. El sistema está online para todos los usuarios.")
else:
    with open(FLAG_FILE, 'w') as f:
        f.write("activo")
    print("🔴 MODO MANTENIMIENTO ACTIVADO. Los clientes verán la pantalla de pausa. Solo el usuario 'root' puede navegar.")