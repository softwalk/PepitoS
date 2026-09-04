/** Icono de UI: emoji o imagen (`img:/ruta.png`). Las imágenes viven en /public y quedan en el precache de la PWA. */
export default function Icon({ icon, className = 'ico' }: { icon: string; className?: string }) {
  if (icon.startsWith('img:')) {
    return <img src={icon.slice(4)} alt="" aria-hidden className={`${className} icon-img`} draggable={false} />;
  }
  return (
    <span className={className} aria-hidden>
      {icon}
    </span>
  );
}
