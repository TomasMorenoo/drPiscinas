const erroresEstado = new Map();
let revisionEstados = 0;

function claveEstado(url) {
    const ruta = new URL(url, window.location.href).pathname;
    const id = ruta.split('/').pop();
    return `${ruta.includes('-grupo/') ? 'grupo' : 'casa'}-${id}`;
}

function mostrarMotivoEstado(clave) {
    const motivo = erroresEstado.get(clave);
    if (motivo) window.alert(`${motivo}\n\nActualizá la página para comprobar el estado guardado antes de repetir la acción.`);
}

function mostrarErroresEstado() {
    document.querySelectorAll('[data-estado-clave]').forEach(contenedor => {
        const clave = contenedor.dataset.estadoClave;
        const motivo = erroresEstado.get(clave);
        if (!motivo || contenedor.querySelector('[data-error-estado]')) return;
        const aviso = document.createElement('button');
        aviso.type = 'button';
        aviso.className = 'btn btn-danger btn-sm fw-bold ms-1 shadow-sm';
        aviso.textContent = '!';
        aviso.dataset.errorEstado = clave;
        aviso.title = `Cambio sin confirmar: ${motivo}`;
        aviso.setAttribute('aria-label', `Cambio sin confirmar. ${motivo}. Ver detalle`);
        aviso.setAttribute('role', 'alert');
        aviso.addEventListener('click', event => {
            event.preventDefault();
            event.stopPropagation();
            mostrarMotivoEstado(clave);
        });
        contenedor.appendChild(aviso);
    });
}

document.addEventListener('click', event => {
    const contenedor = event.target.closest('[data-estado-clave]');
    if (!contenedor || !erroresEstado.has(contenedor.dataset.estadoClave)) return;
    if (event.target.closest('[data-error-estado]')) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    mostrarMotivoEstado(contenedor.dataset.estadoClave);
}, true);

async function solicitarCambioEstado(url, opciones) {
    const clave = claveEstado(url);
    if (erroresEstado.has(clave)) throw new Error(erroresEstado.get(clave));
    revisionEstados++;
    const controlador = new AbortController();
    const timeout = setTimeout(() => controlador.abort(), 30000);
    let motivo = '';
    try {
        const respuesta = await fetch(url, { ...opciones, signal: controlador.signal });
        if (respuesta.redirected || respuesta.status === 401) {
            motivo = 'La sesión ya no es válida. Volvé a iniciar sesión.';
        } else if (!respuesta.ok) {
            if (respuesta.status === 400) {
                const texto = await respuesta.clone().text();
                motivo = /csrf.*expired/i.test(texto)
                    ? 'Venció el token de seguridad. Actualizá la página.'
                    : /csrf/i.test(texto)
                        ? 'El token de seguridad no es válido. Actualizá la página.'
                        : 'El servidor rechazó los datos del cambio (400).';
            } else if (respuesta.status === 403) {
                motivo = 'No tenés permiso para realizar este cambio (403).';
            } else if (respuesta.status === 429) {
                motivo = 'Se alcanzó el límite de solicitudes. Esperá unos minutos (429).';
            } else {
                motivo = `El servidor no confirmó el cambio (error ${respuesta.status}).`;
            }
        } else {
            let datos;
            try {
                datos = await respuesta.clone().json();
            } catch (_) {
                motivo = 'El servidor devolvió una respuesta inesperada. No se pudo confirmar el guardado.';
            }
            if (!motivo && datos?.success !== true) {
                motivo = typeof datos?.message === 'string'
                    ? datos.message.slice(0, 240)
                    : 'El servidor no confirmó el cambio.';
            }
        }
        if (motivo) throw new Error(motivo);
        return respuesta;
    } catch (error) {
        motivo = motivo || (error.name === 'AbortError'
            ? 'El servidor tardó demasiado. No se pudo confirmar el guardado.'
            : 'Falló la conexión. No se pudo confirmar el guardado.');
        erroresEstado.set(clave, motivo);
        mostrarErroresEstado();
        throw new Error(motivo);
    } finally {
        clearTimeout(timeout);
    }
}

function mostrarErrorActualizacion() {
    if (document.getElementById('error-actualizacion-panel')) return;
    const aviso = document.createElement('div');
    aviso.id = 'error-actualizacion-panel';
    aviso.className = 'alert alert-warning';
    aviso.setAttribute('role', 'alert');
    aviso.textContent = 'No se pudo actualizar el panel. Actualizá la página para consultar los estados guardados.';
    document.getElementById('collapseSueltas')?.before(aviso);
}
