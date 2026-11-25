// Pantalla de acceso de la nube (ADR 0009, sección 8): solo entran los correos de la lista cerrada de lectores.
import { Icono } from "./Icono";

export function AccesoNube({ acceso }: { acceso: string | null }) {
  return (
    <div className="acceso-nube">
      <div className="tarjeta-acceso">
        <span className="marca">
          <Icono nombre="tabla" tam={22} />
        </span>
        <h1>Extractor de matriz</h1>
        <p className="tenue">
          Copia de solo lectura de la matriz de síntesis: felicidad y desempeño laboral. El acceso es por invitación.
        </p>
        <a className="boton-acceso primario" href={acceso ?? "/api/v1/auth/google/entrar"}>
          Entrar con Google
        </a>
        <p className="tenue pequeno">
          Los artículos son de terceros: el acceso se limita a la lista de lectores del proyecto. Si no puede entrar,
          pida que agreguen su correo.
        </p>
      </div>
    </div>
  );
}
