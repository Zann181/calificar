// norm() debe dar lo mismo que app/compartido/normalizacion.py: si difieren, el visor busca la cita con una regla
// distinta de la que usó el anclaje y resalta otra cosa (o nada).
import { describe, expect, it } from "vitest";

import { norm } from "./normalizar";

describe("norm", () => {
  it("unifica comillas y guiones tipográficos", () => {
    expect(norm("“Happy” workers’ – performance — r")).toBe('"happy" workers\' - performance - r');
  });

  it("une las palabras cortadas con guion al final de línea", () => {
    expect(norm("perfor-\nmance")).toBe("performance");
  });

  it("colapsa espacios, recorta y pasa a minúsculas", () => {
    expect(norm("  Job\n\tSatisfaction   (α = .94) ")).toBe("job satisfaction (α = .94)");
  });

  it("aplica NFKC (ligaduras y anchos)", () => {
    expect(norm("ﬁnding ＡＢ")).toBe("finding ab");
  });
});
