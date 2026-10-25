"""
Catálogo de residuos de EcoQR: qué reconoce la app, en qué caneca va cada uno y por qué.

Las explicaciones están escritas para estudiantes y deben ser revisadas por el profesor
antes de la entrega (puedes editarlas aquí sin tocar nada más).

Colores de canecas (norma colombiana, Resolución 2184 de 2019):
    blanca = aprovechables (plástico, vidrio, metal, papel y cartón limpios)
    negra  = no aprovechables
    verde  = orgánicos aprovechables (restos de comida y de jardín)
"""

CATEGORIAS = ["Aprovechable", "No Aprovechable", "Orgánico"]

# Clase especial del modelo: "esto no es un residuo / no se reconoce" (manos, piso, mesa, objetos raros).
# No es un residuo del catálogo: si el modelo la elige, la app le pide al estudiante otra foto.
CLASE_OTRO = "otro"
NOMBRES_CLASE_OTRO = {"otro", "otros", "nada", "ninguno", "fondo", "no_residuo", "sin_residuo", "no_es_residuo"}

CANECA_POR_CATEGORIA = {
    "Aprovechable": "blanca",
    "No Aprovechable": "negra",
    "Orgánico": "verde",
}

# clave interna -> datos. La clave es lo que debe llamarse la clase en el modelo de IA
# (sin tildes ni espacios: "resto_comida"), o se traduce con modelo/mapa_clases.json.
RESIDUOS = {
    "botella": {
        "nombre": "Botella",
        "categoria": "Aprovechable",
        "explicacion": "Las botellas de plástico y de vidrio se pueden reciclar y convertir en productos nuevos. "
                       "Vacíalas y, si puedes, enjuágalas antes de botarlas.",
    },
    "empaque": {
        "nombre": "Empaque de snack o dulce",
        "categoria": "No Aprovechable",
        "explicacion": "Los empaques de papas, dulces y galletas están hechos de capas de plástico y aluminio pegadas "
                       "que no se pueden separar, por eso no se reciclan y van a la caneca negra.",
    },
    "resto_comida": {
        "nombre": "Resto de comida",
        "categoria": "Orgánico",
        "explicacion": "Los restos de comida se descomponen y pueden convertirse en abono (compost). "
                       "Van en la caneca verde, sin envolturas ni plásticos.",
    },
    "cascara_fruta": {
        "nombre": "Cáscara de fruta",
        "categoria": "Orgánico",
        "explicacion": "Las cáscaras son materia orgánica: se descomponen solas y se convierten en abono. "
                       "Por eso van a la caneca verde.",
    },
    "plastico": {
        "nombre": "Plástico",
        "categoria": "Aprovechable",
        "explicacion": "Los plásticos limpios (vasos, recipientes, bolsas) se pueden reciclar y van a la caneca blanca. "
                       "Vacíalos y enjuágalos antes de botarlos.",
    },
    "papel": {
        "nombre": "Papel",
        "categoria": "Aprovechable",
        "explicacion": "El papel limpio y seco (hojas, periódico, revistas) se recicla y va a la caneca blanca. "
                       "Mantenlo seco y sin comida para que siga sirviendo.",
    },
        # --- Otros residuos comunes en un colegio ---
    "lata": {
        "nombre": "Lata de metal",
        "categoria": "Aprovechable",
        "explicacion": "Las latas de gaseosa, atún o conservas son de metal y se reciclan una y otra vez. "
                       "Vacíalas y, si puedes, enjuágalas; van a la caneca blanca.",
    },
    "vidrio": {
        "nombre": "Vidrio",
        "categoria": "Aprovechable",
        "explicacion": "Los frascos y las botellas de vidrio enteros se reciclan muchas veces sin perder calidad. "
                       "Van a la caneca blanca. Si el vidrio está roto, avísale a un adulto y envuélvelo para no cortarte (va a la negra).",
    },
    "carton_bebida": {
        "nombre": "Cartón de bebida (leche o jugo)",
        "categoria": "Aprovechable",
        "explicacion": "Los envases de leche o jugo tipo Tetra Pak tienen cartón, plástico y aluminio, pero se pueden reciclar. "
                       "Vacíalos, aplástalos y llévalos a la caneca blanca.",
    },
    "icopor": {
        "nombre": "Icopor",
        "categoria": "No Aprovechable",
        "explicacion": "El icopor (vasos, platos y bandejas) casi no se recicla y ocupa mucho espacio. "
                       "Va a la caneca negra; lo mejor es usar menos.",
    },
    "otro_no_aprovechable": {
        "nombre": "Otro residuo no aprovechable",
        "categoria": "No Aprovechable",
        "explicacion": "Objetos como esferos, borradores, chicles, colillas, cintas adhesivas o vidrio roto no se pueden reciclar. "
                       "Van a la caneca negra.",
    },
        # --- Catálogo ampliado: plásticos y papeles específicos ---
    "tapa_plastica": {
        "nombre": "Tapa de plástico",
        "categoria": "Aprovechable",
        "explicacion": "Las tapas de botellas y frascos son de plástico reciclable. Van a la caneca blanca; "
                       "lo mejor es dejarlas puestas en la botella vacía y aplastada.",
    },
    "bolsa_plastica": {
        "nombre": "Bolsa plástica",
        "categoria": "Aprovechable",
        "explicacion": "Las bolsas plásticas limpias y secas se pueden reciclar y van a la caneca blanca. "
                       "Si están sucias o con comida, van a la negra. Y mejor aún: reutilízalas.",
    },
    "recipiente_plastico": {
        "nombre": "Vaso o recipiente de plástico",
        "categoria": "Aprovechable",
        "explicacion": "Los vasos, tarros, bandejas y cajas de plástico limpios se reciclan. "
                       "Vacíalos, enjuágalos y llévalos a la caneca blanca.",
    },
    "envase_aseo": {
        "nombre": "Envase de aseo",
        "categoria": "Aprovechable",
        "explicacion": "Los envases de jabón, champú, detergente o desinfectante son de plástico resistente y se reciclan. "
                       "Vacíalos, enjuágalos y van a la caneca blanca.",
    },
    "cuaderno_libro": {
        "nombre": "Cuaderno, libro o revista",
        "categoria": "Aprovechable",
        "explicacion": "Las hojas de cuadernos, libros, revistas y periódicos se reciclan mientras estén secas y limpias. "
                       "Van a la caneca blanca. Si puedes, quita el espiral antes de botarlos.",
    },
    "carton_huevos": {
        "nombre": "Cubeta de huevos o tubo de cartón",
        "categoria": "Aprovechable",
        "explicacion": "Las cubetas de huevos y los tubos de cartón (como el del papel higiénico) son cartón y se reciclan "
                       "si están secos y limpios. Van a la caneca blanca.",
    },
    "papel_aluminio": {
        "nombre": "Papel aluminio",
        "categoria": "Aprovechable",
        "explicacion": "El papel aluminio limpio es metal reciclable: haz una bolita y llévalo a la caneca blanca. "
                       "Si tiene grasa o comida pegada, va a la negra.",
    },
    "objeto_metal": {
        "nombre": "Objeto de metal",
        "categoria": "Aprovechable",
        "explicacion": "Las tapas de metal, los clips, las grapas y los utensilios de aluminio o hierro se reciclan. "
                       "Van a la caneca blanca.",
    },
    # --- Catálogo ampliado: no aprovechables ---
    "cubiertos_pitillo": {
        "nombre": "Pitillo o cubiertos desechables",
        "categoria": "No Aprovechable",
        "explicacion": "Los pitillos, cubiertos y revolvedores desechables son tan pequeños y livianos que las plantas de reciclaje "
                       "no alcanzan a separarlos. Van a la caneca negra; mejor usa los tuyos.",
    },
    "lapiz_esfero": {
        "nombre": "Lápiz, esfero o borrador",
        "categoria": "No Aprovechable",
        "explicacion": "Los lápices, esferos, marcadores, borradores y sacapuntas mezclan materiales que no se pueden separar. "
                       "Van a la caneca negra.",
    },
    "vidrio_roto": {
        "nombre": "Vidrio roto",
        "categoria": "No Aprovechable",
        "explicacion": "El vidrio roto no se recicla y puede cortar. No lo recojas con la mano: avísale a un adulto, "
                       "envuélvelo en papel o cartón y va a la caneca negra.",
    },
    "ceramica_espejo": {
        "nombre": "Cerámica, espejo o vidrio de ventana",
        "categoria": "No Aprovechable",
        "explicacion": "Los platos, tazas, espejos y vidrios de ventana no son como el vidrio de las botellas y dañan el reciclaje. "
                       "Van a la caneca negra; avísale a un adulto si están rotos.",
    },
    "tela_calzado": {
        "nombre": "Tela, ropa o zapatos",
        "categoria": "No Aprovechable",
        "explicacion": "La ropa, los trapos y los zapatos dañados no se reciclan en las canecas del colegio y van a la negra. "
                       "Si todavía sirven, mejor dónalos.",
    },
    "higiene_personal": {
        "nombre": "Residuo de higiene personal",
        "categoria": "No Aprovechable",
        "explicacion": "Los tapabocas, toallas higiénicas, pañales, algodones y cotonetes no se reciclan. "
                       "Van a la caneca negra, en una bolsa bien cerrada.",
    },
    "guante_globo": {
        "nombre": "Guante o globo",
        "categoria": "No Aprovechable",
        "explicacion": "Los guantes de látex y los globos son de caucho y no se reciclan. Van a la caneca negra.",
    },
    "esponja_estropajo": {
        "nombre": "Esponja o estropajo",
        "categoria": "No Aprovechable",
        "explicacion": "Las esponjas, estropajos y paños de limpieza usados no se reciclan. Van a la caneca negra.",
    },
    "vaso_carton_desechable": {
        "nombre": "Vaso o plato desechable de cartón",
        "categoria": "No Aprovechable",
        "explicacion": "Los vasos y platos desechables de cartón (de café, sopa o helado) tienen una capa de plástico por dentro "
                       "que no se puede separar. Van a la caneca negra.",
    },
    "chicle_colilla": {
        "nombre": "Chicle o colilla",
        "categoria": "No Aprovechable",
        "explicacion": "Los chicles y las colillas no se reciclan ni se descomponen fácilmente. Envuélvelos y bótalos en la caneca negra.",
    },
    "cinta_etiqueta": {
        "nombre": "Cinta, sticker o papel metalizado",
        "categoria": "No Aprovechable",
        "explicacion": "La cinta adhesiva, los stickers, el papel carbón y el papel de regalo metalizado tienen pegante o brillo "
                       "que daña el reciclaje. Van a la caneca negra.",
    },
    "pilas": {
        "nombre": "Pila o batería",
        "categoria": "No Aprovechable",
        "explicacion": "Las pilas tienen metales tóxicos que contaminan el agua y el suelo. No las botes en ninguna caneca común: "
                       "entrégaselas a tu profesor para llevarlas a un punto de recolección de pilas.",
    },
    "bombillo": {
        "nombre": "Bombillo o tubo fluorescente",
        "categoria": "No Aprovechable",
        "explicacion": "Los bombillos ahorradores y los tubos fluorescentes tienen mercurio, que es tóxico. No los botes en la caneca "
                       "común: avísale a un adulto para llevarlos a un punto de recolección especial.",
    },
    "electronico": {
        "nombre": "Aparato o cable electrónico",
        "categoria": "No Aprovechable",
        "explicacion": "Los cables, cargadores, audífonos, calculadoras y celulares dañados tienen metales que contaminan. "
                       "No los botes en la caneca común: entrégaselos a tu profesor para llevarlos a un punto de recolección de electrónicos.",
    },
    # --- Catálogo ampliado: orgánicos ---
    "hojas_ramas": {
        "nombre": "Hojas, ramas o pasto",
        "categoria": "Orgánico",
        "explicacion": "Las hojas secas, ramas, pasto y flores son materia orgánica y se convierten en abono. Van a la caneca verde.",
    },
    "cascara_huevo": {
        "nombre": "Cáscara de huevo",
        "categoria": "Orgánico",
        "explicacion": "La cáscara de huevo se descompone y le da calcio al abono. Va a la caneca verde.",
    },
    "cafe_te": {
        "nombre": "Borra de café o bolsita de té",
        "categoria": "Orgánico",
        "explicacion": "La borra de café y las bolsitas de té (sin grapa ni hilo de plástico) se descomponen y sirven para abono. "
                       "Van a la caneca verde.",
    },
    "madera": {
        "nombre": "Madera (palitos o aserrín)",
        "categoria": "Orgánico",
        "explicacion": "Los palitos de helado, palillos y el aserrín de madera sin pintar se descomponen. Van a la caneca verde.",
    },
    "panito_humedo": {
        "nombre": "Pañito húmedo o toallita",
        "categoria": "No Aprovechable",
        "explicacion": "Los pañitos húmedos y las toallitas están hechos de fibras sintéticas que no se reciclan ni se descomponen. "
                       "Van a la caneca negra; nunca los botes al inodoro.",
    },
    "blister_pastillas": {
        "nombre": "Blíster o sobre de pastillas",
        "categoria": "No Aprovechable",
        "explicacion": "Los blísteres y sobres de pastillas mezclan aluminio y plástico pegados, por eso no se reciclan y van a la caneca negra. "
                       "Si son medicamentos vencidos, entrégaselos a un adulto para llevarlos a un punto de recolección de medicamentos.",
    },
    "papel_sucio": {
        "nombre": "Papel sucio o mojado",
        "categoria": "No Aprovechable",
        "explicacion": "El papel con comida, grasa o mojado (como una servilleta usada o el papel higiénico) ya no se puede "
                       "reciclar y además ensucia el papel limpio. Por eso va a la caneca negra.",
    },
    "carton_sucio": {
        "nombre": "Cartón sucio o con grasa",
        "categoria": "No Aprovechable",
        "explicacion": "El cartón con grasa o restos de comida (como una caja de pizza usada) no se puede reciclar porque "
                       "la grasa daña el proceso. Va a la caneca negra; si una parte está limpia, puedes separarla y botarla en la blanca.",
    },
    "plastico_sucio": {
        "nombre": "Plástico con restos de comida",
        "categoria": "No Aprovechable",
        "explicacion": "Un plástico con comida pegada que no se puede enjuagar contamina el reciclaje, por eso va a la caneca negra. "
                       "Si lo enjuagas y queda limpio, va a la blanca.",
    },
    "carton": {
        "nombre": "Cartón",
        "categoria": "Aprovechable",
        "explicacion": "El cartón limpio y seco (cajas, empaques de cartón) se recicla y va a la caneca blanca. "
                       "Aplana las cajas para que ocupen menos espacio.",
    },
}


def datos_residuo(clave: str) -> dict:
    """Devuelve nombre, categoría, caneca y explicación de un residuo del catálogo."""
    r = RESIDUOS[clave]
    return {
        "residuo": clave,
        "nombre": r["nombre"],
        "categoria": r["categoria"],
        "caneca": CANECA_POR_CATEGORIA[r["categoria"]],
        "explicacion": r["explicacion"],
    }


def nombre_legible(clave: str) -> str:
    return RESIDUOS[clave]["nombre"] if clave in RESIDUOS else clave
