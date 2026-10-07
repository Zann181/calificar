// Igual que app/compartido/normalizacion.py: así la búsqueda de la cita en la capa de texto del visor
// usa la misma regla que el anclaje y el validador.
export function norm(t: string): string {
  return t
    .normalize("NFKC")
    .replace(/[’‘]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[–—]/g, "-")
    .replace(/-\n/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}
