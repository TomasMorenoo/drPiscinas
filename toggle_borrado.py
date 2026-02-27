import os

ARCHIVO_FLAG = "borrado_activado.flag"

def toggle():
    print("========================================")
    print("   🛠️  CONTROL DE BORRADO DE CLIENTES   ")
    print("========================================\n")

    if os.path.exists(ARCHIVO_FLAG):
        # Si el archivo existe, lo borramos para APAGAR el botón
        os.remove(ARCHIVO_FLAG)
        print("🟢 RESULTADO: MODO LIMPIEZA APAGADO.")
        print("👉 El botón de borrar clientes ha sido OCULTADO de la web.")
    else:
        # Si no existe, creamos un archivo vacío para ENCENDER el botón
        with open(ARCHIVO_FLAG, "w") as f:
            f.write("activado")
        print("🔴 RESULTADO: MODO LIMPIEZA ENCENDIDO.")
        print("👉 El botón de borrar clientes ahora es VISIBLE en la web.")
    
    print("\n(Actualizá la página en tu navegador para ver el cambio)")

if __name__ == "__main__":
    toggle()