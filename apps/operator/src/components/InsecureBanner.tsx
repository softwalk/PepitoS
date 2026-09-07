// Aviso persistente cuando la app se abrió por http:// (sin conexión segura): el navegador no da cifrado ni GPS y nada
// se puede guardar. Se muestra en el login y arriba de todas las pantallas hasta que se abra por https://.
import { INSECURE_MESSAGE, insecureContext } from '../offline/errors';

export default function InsecureBanner() {
  if (!insecureContext()) return null;
  return (
    <div className="insecure-banner" role="alert" data-testid="insecure-banner">
      <span className="ico" aria-hidden>
        🔒
      </span>
      <div title={INSECURE_MESSAGE}>
        <b>Conexión no segura.</b> Abre la app desde la dirección <b>https://</b> que te dio el supervisor; así no se pueden guardar ventas ni avisos.
      </div>
    </div>
  );
}
