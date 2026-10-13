import { describe, expect, it } from "vitest";

import { formatoTiempo, porcentajeVisible } from "./avance";
import type { AvanceExtraccion } from "./tipos";

const T0 = Date.parse("2026-10-12T10:00:00Z");

function avance(cambios: Partial<AvanceExtraccion> = {}): AvanceExtraccion {
  return {
    progreso: 8,
    hasta: 45,
    segundos_tipicos: 300,
    paso_desde: new Date(T0).toISOString(),
    terminada_en: null,
    fallida: false,
    ...cambios,
  } as AvanceExtraccion;
}

describe("porcentajeVisible", () => {
  it("al empezar el paso muestra el porcentaje oficial", () => {
    expect(porcentajeVisible(avance(), T0)).toBe(8);
  });

  it("avanza con el tiempo típico del paso", () => {
    expect(porcentajeVisible(avance(), T0 + 150_000)).toBe(26); // mitad del paso: 8 + 37 × 0,5
  });

  it("nunca llega al tope del paso aunque se pase del tiempo típico", () => {
    expect(porcentajeVisible(avance(), T0 + 3_600_000)).toBeLessThan(45);
  });

  it("terminada o fallida: solo el oficial", () => {
    expect(porcentajeVisible(avance({ terminada_en: "x", progreso: 100 }), T0 + 999_999)).toBe(100);
    expect(porcentajeVisible(avance({ fallida: true }), T0 + 999_999)).toBe(8);
  });
});

describe("formatoTiempo", () => {
  it("minutos y segundos con dos cifras", () => {
    expect(formatoTiempo(0)).toBe("0:00");
    expect(formatoTiempo(65.4)).toBe("1:05");
    expect(formatoTiempo(-3)).toBe("0:00");
  });
});
