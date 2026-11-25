import { describe, expect, it } from "vitest";

import { ETIQUETAS, mover, porcentaje, segmentos, textoPuntaje } from "./cobertura";
import type { CeldaPrevia, Evaluacion } from "./tipos";

const celda = (estado: CeldaPrevia["estado"], prioridad: CeldaPrevia["prioridad"]): CeldaPrevia => ({
  columna: "x",
  estado,
  valor: null,
  origen: "",
  frase: null,
  prioridad,
});

describe("segmentos", () => {
  it("reparte la barra con los mismos pesos que el servidor (5, 3 y 1)", () => {
    const s = segmentos([
      celda("INDICIO", "IMPRESCINDIBLE"), // 5 cubierto
      celda("PENDIENTE", "IMPORTANTE"), // 3 pendiente
      celda("AUSENTE", "DESEABLE"), // 1 ausente
    ]);
    expect(s.cubierto).toBeCloseTo(5 / 9);
    expect(s.pendiente).toBeCloseTo(3 / 9);
    expect(s.ausente).toBeCloseTo(1 / 9);
  });

  it("las columnas internas no cuentan y una lista vacía no divide por cero", () => {
    expect(segmentos([celda("NO_APLICA", "IMPRESCINDIBLE"), celda("METADATO", "DESEABLE")]).cubierto).toBe(1);
    expect(segmentos([])).toEqual({ cubierto: 0, pendiente: 0, ausente: 0 });
  });
});

describe("textos", () => {
  it("el puntaje muestra también el máximo posible", () => {
    const ev = { puntaje: 0.62, maximo: 1 } as Evaluacion;
    expect(textoPuntaje(ev)).toBe("62% (máx. 100%)");
    expect(porcentaje(0.333)).toBe("33%");
  });

  it("«pendiente» no se llama «ausente»", () => {
    expect(ETIQUETAS.NO_APLICA).toBe("No aplica");
    expect(ETIQUETAS.SIN_DATOS).toBe("Sin datos suficientes");
  });
});

describe("mover", () => {
  it("sube y baja sin salirse de los bordes y sin mutar", () => {
    const base = ["a", "b", "c"];
    expect(mover(base, 1, -1)).toEqual(["b", "a", "c"]);
    expect(mover(base, 1, 1)).toEqual(["a", "c", "b"]);
    expect(mover(base, 0, -1)).toBe(base);
    expect(mover(base, 2, 1)).toBe(base);
    expect(base).toEqual(["a", "b", "c"]);
  });
});
