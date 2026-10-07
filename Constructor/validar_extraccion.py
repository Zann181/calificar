#!/usr/bin/env python3
"""Valida una salida de extracción contra el Libro de códigos v2.

Uso:
    python3 validar_extraccion.py salida.json Libro_de_codigos_extraccion_v2.json [articulo.pdf]

Si se entrega el PDF (requiere pdftotext), comprueba además que cada cita_textual
fuera de tablas y figuras aparezca literal en el texto del artículo (V23).
Salida: lista de errores y advertencias con su código V; código de salida 1 si hay errores.
"""
import json, re, sys, subprocess, unicodedata

NI, NS, NA = "No indica", "No indica (no significativo)", "No aplica"
NUMERICAS = ["Covidence #", "Fiabilidad Alfa - Omega (desempeño)", "# Ítems", "Items instrumento1",
             "Fiabilidad Alfa - Omega (felicidad)", "Muestra", "Correlación Feli 1 - JP", "Beta Fel 1- JP"]
EXENTAS_ESTADO = {"Covidence #"}


def norm(t):
    t = unicodedata.normalize("NFKC", t)
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.replace("–", "-").replace("—", "-").replace("-\n", "")
    return re.sub(r"\s+", " ", t).strip().lower()


def numeros(texto):
    out = []
    for m in re.finditer(r"-?\d*[.,]\d+|-?\d+", texto or ""):
        try:
            out.append(abs(float(m.group().replace(",", "."))))
        except ValueError:
            pass
    return out


def arbol_inclusion(f, t):
    """Devuelve (categoría, condición) según instruccion_operativa de Incluir en meta análisi."""
    r, b = f["Correlación Feli 1 - JP"], f["Beta Fel 1- JP"]
    ns = t.get("sensibilidad_r_cero", False)
    if f["Muestra"] is None:
        return "No", 1
    if r is None and b is None and not ns and not t.get("otros_coeficientes") and t.get("r_derivado") is None:
        return "No", 2
    if f["Nivel"] == "Group":
        return "Organizacional", 3
    if f["Study design"] == "Randomised controlled trial":
        return "Experimental", 4
    if f["Nivel"] == "Multinivel":
        return "Multinivel", 5
    if (r is not None and t.get("metodo_obtencion_r") == "Pearson observado") or t.get("r_derivado") is not None:
        return "SI", 6
    if t.get("r_imputado_desde_beta") is not None:
        return "SI", 7
    if t.get("metodo_obtencion_r") == "Correlación entre compuestos PLS" or t.get("tecnica_del_beta") == "PLS":
        return "PLS", 8
    if t.get("metodo_obtencion_r") == "Correlación entre variables latentes CB-SEM" or t.get("tecnica_del_beta") == "CB-SEM latente":
        return "SEM latente", 9
    if ns:
        return "No", 10
    return "No", 11


def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    salida = json.load(open(sys.argv[1], encoding="utf-8"))
    libro = json.load(open(sys.argv[2], encoding="utf-8"))
    texto_pdf = None
    if len(sys.argv) > 3:
        texto_pdf = norm(subprocess.run(["pdftotext", sys.argv[3], "-"], capture_output=True, text=True).stdout)

    E, A = [], []
    err = lambda v, i, m: E.append(f"[{v}] fila {i}: {m}")
    adv = lambda v, i, m: A.append(f"[{v}] fila {i}: {m}")

    # Esquema (tipos, vocabularios, V04, V05, V24)
    try:
        import jsonschema
        val = jsonschema.Draft202012Validator(libro["esquema_de_salida"]["json_schema"])
        for e in sorted(val.iter_errors(salida), key=lambda e: list(e.path)):
            E.append(f"[ESQUEMA] {'/'.join(map(str, e.path))}: {e.message[:200]}")
    except ImportError:
        A.append("[ESQUEMA] jsonschema no instalado (pip install jsonschema); se omite la validación de esquema.")
    if E:
        print("\n".join(E)); print(f"\n{len(E)} errores de esquema; corrija antes de las demás validaciones."); sys.exit(1)

    cols = libro["columnas"]
    nivel_doc = [k for k, c in cols.items() if c["instruccion_operativa"].get("nivel_de_registro") == "Documento"]
    requiere_ev = [k for k, c in cols.items() if c["instruccion_operativa"].get("requiere_evidencia")]
    corr = libro["vocabularios_controlados"]["columnas"]["Tipo de felicidad real"]["correspondencia_hedonica_eudaimonica"]

    estudios, por_doc, por_muestra = set(), {}, {}
    for i, row in enumerate(salida, 1):
        f, t = row["fila"], row["trazabilidad"]
        # V01
        if f["Estudio"] in estudios and f["Estudio"] != "PENDIENTE_EQUIPO":
            err("V01", i, f"Estudio {f['Estudio']} repetido")
        estudios.add(f["Estudio"])
        por_doc.setdefault(f["Documento"], []).append((i, f))
        por_muestra.setdefault(t["id_muestra"], []).append((i, f))
        # V03
        autores = [a.strip() for a in f["Author"].split(";") if a.strip()]
        ape = autores[0].split()[-1] if autores else ""
        m = re.match(r"^(.+?)(?: y (.+?)| et al\.)? \((\d{4})[a-z]?\)$", f["Cita"])
        if not m:
            err("V03", i, f"Cita con formato inválido: {f['Cita']}")
        else:
            if norm(m.group(1)) != norm(ape):
                err("V03", i, f"Cita '{f['Cita']}' no empieza con el apellido del primer autor '{ape}'")
            if int(m.group(3)) != f["Año"]:
                err("V03", i, "Año de la Cita distinto de Año")
            n = len(autores)
            forma = "et al." in f["Cita"] and "et" or (" y " in f["Cita"] and "y" or "uno")
            esperada = "uno" if n == 1 else ("y" if n == 2 else "et")
            if forma != esperada:
                err("V03", i, f"Cita no sigue la regla del número de autores ({n} autores)")
        # V06
        for k in NUMERICAS:
            if f[k] is None and k not in EXENTAS_ESTADO and k not in t["estado_del_dato"]:
                err("V06", i, f"'{k}' es null sin código en estado_del_dato")
        if f["Covidence #"] is None and t["via_de_identificacion"] == "Covidence":
            err("V06", i, "Covidence # vacío pero via_de_identificacion = Covidence")
        # V09
        if f["Muestra"] is None and f["Incluir en meta análisi"] != "No":
            err("V09", i, "Muestra null exige Incluir = No")
        # V10
        nums = numeros(f["Correlacion o Beta felicidad 1 - JP"])
        for k in ("Correlación Feli 1 - JP", "Beta Fel 1- JP"):
            v = f[k]
            if v is not None and not any(abs(abs(v) - x) < 0.0005 for x in nums):
                err("V10", i, f"{k} = {v} no aparece en la transcripción")
        # V11
        if f["# Ítems"] == 1 and not (f["Fiabilidad Alfa - Omega (desempeño)"] is None and t["estado_del_dato"].get("Fiabilidad Alfa - Omega (desempeño)") == NA):
            err("V11", i, "Desempeño de un ítem: la fiabilidad debe ser null con estado No aplica")
        if f["Items instrumento1"] == 1 and not (f["Fiabilidad Alfa - Omega (felicidad)"] is None and t["estado_del_dato"].get("Fiabilidad Alfa - Omega (felicidad)") == NA):
            err("V11", i, "Felicidad de un ítem: la fiabilidad debe ser null con estado No aplica")
        # V12
        cat, cond = arbol_inclusion(f, t)
        if f["Incluir en meta análisi"] != cat:
            err("V12", i, f"Incluir = {f['Incluir en meta análisi']} pero el árbol da {cat} (condición {cond})")
        elif not t["motivo_decision_inclusion"].startswith(f"Condición {cond}:"):
            err("V12", i, f"motivo_decision_inclusion debe empezar con 'Condición {cond}:'")
        # V13
        for k in requiere_ev:
            v = f[k]
            if v is None or v in (NI, NS, NA):
                continue
            if k not in t["evidencia"]:
                err("V13", i, f"'{k}' tiene valor sin evidencia")
        # V14
        b, ri = f["Beta Fel 1- JP"], t["r_imputado_desde_beta"]
        if ri is not None:
            ok = b is not None and abs(b) <= 0.5 and t["tecnica_del_beta"] == "Regresión" and t["tipo_de_efecto"] == "parcial"
            if not ok:
                err("V14", i, "r_imputado_desde_beta no permitido para este beta")
            elif abs(ri - (0.98 * b + (0.05 if b >= 0 else 0))) > 0.001:
                err("V14", i, "r_imputado_desde_beta no coincide con Peterson y Brown")
        # V15
        coef = f["Correlación Feli 1 - JP"] if f["Correlación Feli 1 - JP"] is not None else f["Beta Fel 1- JP"]
        dirc = f["Direccionalidad de la relación"]
        if coef is not None:
            if coef < 0 and "HP" in dirc:
                adv("V15", i, "Coeficiente negativo con HP")
            if coef > 0 and "Relación negativa" in dirc:
                adv("V15", i, "Coeficiente positivo con Relación negativa")
        # V16 y V17
        vde = f["Validez de las escalas"]
        if (f["Validez?"] == "Si") == (vde == NI):
            adv("V16", i, "Validez? y Validez de las escalas no son coherentes")
        if "Si" in (f["Validez CFA"], f["CFA"]) and not re.search(r"AFC|CFA|confirmator", vde, re.I):
            adv("V17", i, "CFA = Si pero Validez de las escalas no menciona AFC")
        # V18
        fechas = [x for x in (f["Start date"], f["End date"]) if x != NI]
        if len(fechas) == 2 and fechas[0] > fechas[1]:
            adv("V18", i, "Start date posterior a End date")
        if any(int(x[:4]) > f["Año"] for x in fechas):
            adv("V18", i, "Fecha de recolección posterior al año de publicación")
        # V19
        for k in ("Fiabilidad Alfa - Omega (desempeño)", "Fiabilidad Alfa - Omega (felicidad)"):
            if f[k] is not None and f[k] < 0.70:
                adv("V19", i, f"{k} = {f[k]} menor a 0.70: confirmar")
        # V22
        for k, v in f.items():
            if isinstance(v, str) and re.search(r"revisar|preguntar|no es claro|pendiente|\?\?", v, re.I):
                adv("V22", i, f"Posible nota de trabajo en '{k}'")
        # V23
        for k, lst in t["evidencia"].items():
            for e in lst:
                if len(e["cita_textual"].split()) > 25:
                    err("V23", i, f"Cita de '{k}' supera 25 palabras")
                if texto_pdf and not e["leido_de_figura"] and norm(e["cita_textual"]) not in texto_pdf:
                    err("V23", i, f"Cita de '{k}' no se encuentra literal en el PDF: {e['cita_textual'][:80]}")
        # V21
        if f["Study design"] == "Cross sectional study" and re.search(r"\bcaus|provoca|efecto causal", f["Conclusion"], re.I) \
                and not any("causal" in x.lower() for x in t["advertencias_pendientes"]):
            adv("V21", i, "Diseño transversal con lenguaje causal en Conclusion; anotarlo en advertencias_pendientes")
        # V27
        esperado = {6: "Principal", 7: "Sensibilidad", 8: "Sensibilidad", 9: "Sensibilidad", 5: "Sensibilidad", 10: "Sensibilidad"}.get(cond, "Narrativo")
        if t["conjunto_sugerido"] != esperado:
            err("V27", i, f"conjunto_sugerido = {t['conjunto_sugerido']}, esperado {esperado}")
        # V28
        rr = f["Correlación Feli 1 - JP"]
        if t["tipo_de_efecto"] == "simple" and rr is not None and b is not None and abs(rr - b) > 0.05:
            adv("V28", i, f"Efecto simple con r = {rr} y Beta = {b}: revisar")
        # V29
        if t["r_derivado"] is not None and t["tecnica_del_beta"] in ("CB-SEM latente", "PLS") and t["metodo_obtencion_r"] != "Pearson observado":
            err("V29", i, "r_derivado no puede provenir de un beta latente")
        # V25
        tf = f["Tipo de felicidad real"]
        if tf in corr and not tf.startswith("Orientación") and corr[tf] != f["Hedónica/eudaimónica"]:
            adv("V25", i, f"Tipo {tf} corresponde a {corr[tf]}, no a {f['Hedónica/eudaimónica']}")
        # V26
        if f["Beta Fel 1- JP"] is not None and abs(f["Beta Fel 1- JP"]) > 1:
            adv("V26", i, "|Beta| > 1: confirmar que es estandarizado")

    # V02
    for doc, filas in por_doc.items():
        for k in nivel_doc:
            vals = {json.dumps(f[k], ensure_ascii=False) for _, f in filas}
            if len(vals) > 1:
                E.append(f"[V02] Documento {doc}: '{k}' cambia entre filas")
    # V20
    for mu, filas in por_muestra.items():
        for k in ("Pais", "Población", "Study design", "Start date", "End date"):
            if len({f[k] for _, f in filas}) > 1:
                A.append(f"[V20] Muestra {mu}: '{k}' cambia entre filas")

    for x in E: print("ERROR  ", x)
    for x in A: print("AVISO  ", x)
    print(f"\n{len(salida)} filas | {len(E)} errores | {len(A)} advertencias")
    sys.exit(1 if E else 0)


if __name__ == "__main__":
    main()
