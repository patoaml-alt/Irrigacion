"""Balance hídrico poblacional de Luján de Cuyo.

Cruza:
  - Dotaciones superficiales empadronadas de plantas potabilizadoras (DGI, planillas 2020)
  - Registro de pozos de la provincia ("Perforaciones sin área de cobertura cloacal")
  - Población (Censo 2022) y cobertura cloacal departamental

Genera datos_lujan.json, que consume index.html.
Uso: python3 analisis.py
"""
import json
import math
import re
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).parent
POZOS = AQUI.parent / "Pozos de Abastecimiento Poblacional (1).xlsx"

# ---------------------------------------------------------------- plantas
# Fuente: PLANTAS_POTABILIZADORAS (hojas EMPADRONAMIENTOS RIO MENDOZA y AFORADORES DE PLANTAS).
# Coordenadas convertidas de las planillas (Luján II corregida: 66º53' -> 68º53').
PLANTAS = [
    # nombre, operador, l/s empadronado, población beneficiada, dotación pedida 2035, lat, lon
    ("Luján I", "AYSAM", 2100, 370266, 3000, -33.0407, -68.9060),
    ("Luján II", "AYSAM", 800, 71959, 583, -33.0417, -68.8985),
    ("Anexo Luján", "AYSAM", 583, None, None, -33.0425, -68.9030),
    ("Potrerillos", "AYSAM", 1100, 135771, 1100, -32.9643, -69.2230),
    ("Cipolletti", "Municipio Luján", 850, 45690, 1100, -33.0437, -68.9128),
    ("Santa Elena", "Municipio Luján", 60, 2546, 60, -33.0154, -68.9266),
]
TOTAL_RIO_MENDOZA = 7848.5  # l/s abastecidos a plantas del Río Mendoza (planilla 30-07-20)
GRAN_MENDOZA_HAB = 1_200_000  # misma planilla

# ---------------------------------------------------------------- población
POB_2010 = 119_888
POB_2022 = 175_056  # Censo 2022, INDEC
COBERTURA_CLOACAL = 0.55  # 2022, departamento

# Estimación por distrito (2022). Agrelo y Perdriel con dato censal 2022 publicado;
# el resto distribuido según 2010 y crecimiento reciente. Reemplazar con radios INDEC 2022.
# (lat, lon, población estimada, cobertura cloacal relativa antes de calibrar)
DISTRITOS = {
    "Ciudad": (-33.036, -68.878, 33000, 0.92),
    "Carrodilla": (-32.968, -68.853, 26000, 0.88),
    "Chacras de Coria": (-32.990, -68.880, 17000, 0.62),
    "Perdriel": (-33.075, -68.895, 19321, 0.30),
    "Mayor Drummond": (-33.005, -68.862, 12000, 0.82),
    "Vistalba": (-33.025, -68.925, 14000, 0.28),
    "La Puntilla": (-32.960, -68.875, 5000, 0.55),
    "Agrelo": (-33.120, -68.935, 5598, 0.06),
    "Ugarteche": (-33.205, -68.890, 9500, 0.18),
    "El Carrizal": (-33.300, -68.760, 4500, 0.0),
    "Industrial": (-33.010, -68.825, 6500, 0.40),
    "Las Compuertas": (-33.035, -68.975, 3500, 0.05),
    "Potrerillos": (-32.962, -69.200, 3000, 0.12),
    "Cacheuta": (-33.030, -69.110, 1000, 0.0),
    "Vertientes del Pedemonte": (-32.985, -68.955, 15137, 0.10),
}

# Cobertura cloacal informada por fuentes locales: se respeta tal cual y
# el resto de los distritos se recalibra para mantener el 55 % departamental.
CLOACA_INFORMADA = {
    "Agrelo": 0.90,  # informado por el usuario (fuente local), a confirmar con AYSAM/Municipio
}

ALIAS = {
    "El Carrizal": ["EL CARRIZAL", "CARRIZAL", "CARRIZAL DEL MEDIO", "CARRIZAL DE ABAJO",
                    "EL CARRIZAL DE ABAJO", "DE ARRIBA"],
    "Ugarteche": ["UGARTECHE", "UGARTECHE (COLONIA CANO)", "ANCHORIS"],
    "Agrelo": ["AGRELO"],
    "Perdriel": ["PERDRIEL", "PEDRIEL", "PERDIREL", "TRES ESQUINAS", "TRES ESQUINAS(PEDRIEL)", "LUNLUNTA"],
    "Vistalba": ["VISTALBA", "VISTALVA"],
    "Las Compuertas": ["LAS COMPUERTAS", "BLANCO ENCALADA"],
    "Carrodilla": ["CARRODILLA"],
    "Chacras de Coria": ["CH.DE CORIA", "CHACRAS DE CORIA", "C.DE CORIA"],
    "Potrerillos": ["POTRERILLOS"],
    "Cacheuta": ["CACHEUTA", "EL TROPEZON"],
    "Mayor Drummond": ["MAYOR DRUMMOND", "M.DRUMMOND", "MAYOR DRUMOND", "DRUMMOND", "M. DRUMMOND"],
    "Ciudad": ["CIUDAD", "LUJAN DE CUYO", "LUJAN", "CIUDAD DE LUJAN"],
    "Industrial": ["PARQUE INDUSTRIAL PROVINCIAL.", "INDUSTRIAL AGRELO", "AGRELO INDUSTRIAL"],
    "La Puntilla": ["LA PUNTILLA"],
}
LOC2DIST = {a: d for d, al in ALIAS.items() for a in al}


def localidad(dom):
    m = re.findall(r" - ([^-]+?) - CP", str(dom))
    return m[-1].strip() if m else None


def main():
    df = pd.read_excel(POZOS, header=2)
    lu = df[df["Departamento"] == "LUJAN DE CUYO"].copy()
    lu["distrito"] = lu["Domicilio Real"].map(localidad).map(LOC2DIST).fillna("Sin localizar")
    # Caudal del registro en m3/h (capacidad declarada) -> l/s
    lu["ls"] = lu["Caudal"].fillna(0) / 3.6
    abast = lu["Uso"].eq("Abastecimiento Poblacion") | lu["Uso Secundario"].eq("Abastecimiento Poblacion")

    # calibra la cobertura cloacal por distrito para que el total pondere 55 %
    fijo = sum(DISTRITOS[n][2] * c for n, c in CLOACA_INFORMADA.items())
    peso = sum(p * c for n, (_, _, p, c) in DISTRITOS.items() if n not in CLOACA_INFORMADA)
    k = (COBERTURA_CLOACAL * POB_2022 - fijo) / peso

    distritos = []
    for nombre, (lat, lon, pob, c) in DISTRITOS.items():
        sub = lu[lu["distrito"] == nombre]
        sa = sub[abast.loc[sub.index]]
        cob = CLOACA_INFORMADA.get(nombre, min(0.97, c * k))
        distritos.append({
            "nombre": nombre, "lat": lat, "lon": lon, "pob": pob,
            "cloaca": round(cob, 3), "cloaca_fuente": "informada" if nombre in CLOACA_INFORMADA else "estimada", "sin_cloaca": round(pob * (1 - cob)),
            "pozos": int(len(sub)), "pozos_agricolas": int((sub["Uso"] == "Agricola").sum()),
            "pozos_abast": int(len(sa)), "abast_ls": round(float(sa["ls"].sum()), 1),
            "capacidad_ls": round(float(sub["ls"].sum()), 1),
        })

    usos = lu.groupby("Uso").agg(n=("ls", "size"), ls=("ls", "sum")).reset_index()
    pozos_abast = lu[abast][["Nro Pozo", "Persona", "distrito", "Fecha Ejecución", "Profundidad Bomba", "Caudal"]]
    pozos_abast = pozos_abast.assign(**{"Fecha Ejecución": pozos_abast["Fecha Ejecución"].dt.year})

    out = {
        "pob_2010": POB_2010, "pob_2022": POB_2022, "cloaca": COBERTURA_CLOACAL,
        "total_rio_mendoza": TOTAL_RIO_MENDOZA, "gran_mendoza_hab": GRAN_MENDOZA_HAB,
        "plantas": [dict(zip(["nombre", "operador", "ls", "pob", "ls_2035", "lat", "lon"], p)) for p in PLANTAS],
        "distritos": distritos,
        "pozos_total": int(len(lu)),
        "pozos_sin_localizar": int((lu["distrito"] == "Sin localizar").sum()),
        "usos": [{"uso": r.Uso, "n": int(r.n), "ls": round(float(r.ls), 1)} for r in usos.itertuples()],
        "pozos_abast": json.loads(pozos_abast.to_json(orient="records", force_ascii=False)),
    }
    (AQUI / "datos_lujan.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))

    # resumen por consola
    print(f"Pozos Luján: {len(lu)}  abastecimiento: {int(abast.sum())}  "
          f"caudal abast: {lu[abast]['ls'].sum():.0f} l/s")
    print(usos)
    print(pd.DataFrame(distritos)[["nombre", "pob", "cloaca", "sin_cloaca", "pozos", "pozos_abast", "abast_ls"]])
    print("calibración cloaca k =", round(k, 3),
          "sin cloaca total:", sum(d["sin_cloaca"] for d in distritos))


def build_html():
    datos = json.loads((AQUI / "datos_lujan.json").read_text())
    datos.pop("pozos_abast")
    html = (AQUI / "plantilla.html").read_text().replace(
        "__DATA__", json.dumps(datos, ensure_ascii=False, separators=(",", ":")))
    (AQUI / "index.html").write_text(html)


if __name__ == "__main__":
    main()
    build_html()
