"""Demo: Artikel, Allergene, Kennzeichnung, Silos, Rezepte, Rework-Regeln und Prüfpläne der Demo."""

ALLERGENGRUPPEN = {
	"Mürbeteig": "Gluten, Milch",
	"Mürbeteig Nuss": "Gluten, Milch, Haselnuss",
	"Nougat": "Milch, Haselnuss",
	"Kakao-Nougat": "Gluten, Milch, Haselnuss",
	"Nuss-Schoko": "Gluten, Milch, Haselnuss, Soja",
}


# Artikelnummer: (Bezeichnung, Stufe, Allergengruppe, Haltbarkeit in Tagen oder None)
ARTIKEL = {
	# gekauft
	"KT-MEHL": ("Weizenmehl Type 550 (Silo oder Sack)", "Rohstoff", None, 365),
	"KT-DINKEL": ("Dinkelmehl Type 630 (Silo)", "Rohstoff", None, 365),
	"KT-ZUCKER": ("Zucker (Silo)", "Rohstoff", None, 730),
	"KT-BUTTER": ("Butter", "Rohstoff", None, 60),
	"KT-HASELNUSS": ("Haselnüsse gehackt", "Rohstoff", None, 270),
	"KT-KAKAO": ("Kakaopulver", "Rohstoff", None, 540),
	"KT-SCHOKO": ("Zartbitter-Kuvertüre (gekauft)", "Rohstoff", None, 365),
	"KT-FOLIE": ("Verpackungsfolie", "Packmittel", None, None),
	# Bio-Linie (Öko-Zertifikat beim Lieferanten nötig)
	"KT-BIO-DINKEL": ("Bio-Dinkelmehl Type 630", "Rohstoff", None, 365),
	"KT-BIO-ZUCKER": ("Bio-Rohrzucker", "Rohstoff", None, 730),
	"KT-SALZ": ("Speisesalz (in Bio erlaubt)", "Rohstoff", None, None),
	# selbst hergestellt: Zuckersirup (Tank) und Füllung
	"KT-SIRUP": ("Zuckersirup (eigene Herstellung, Tank)", "Halbfabrikat", None, 14),
	"KT-NOUGAT": ("Nougatfüllung (eigene Herstellung)", "Halbfabrikat", "Nougat", 30),
	# Teige: Haltbarkeit = maximale Standzeit
	"KT-GT-MUERBE": ("Grundteig Mürbe", "Grundteig", "Mürbeteig", 3),
	"KT-TV-NUSS": ("Teig Haselnuss (veredelt)", "Teig veredelt", "Mürbeteig Nuss", 2),
	"KT-TV-KAKAO": ("Teig Kakao (veredelt)", "Teig veredelt", "Mürbeteig", 2),
	"KT-BIO-GT": ("Bio-Grundteig Dinkel (vegan)", "Grundteig", None, 3),
	# gebacken, noch ohne Füllung/Glasur
	"KT-BW-NUSS": ("Nusskeks gebacken", "Backware", "Mürbeteig Nuss", 7),
	"KT-BW-KAKAO": ("Kakaokeks gebacken", "Backware", "Mürbeteig", 7),
	# lose fertige Ware im Lager: Haltbarkeit = maximale Lagerdauer ab Backtag
	"KT-WL-NUSS-SCHOKO": ("Nusskeks mit Schokoboden lose", "Ware lose", "Nuss-Schoko", 180),
	"KT-WL-KAKAO-NOUGAT": ("Kakaokeks mit Nougat lose", "Ware lose", "Kakao-Nougat", 180),
	# Rework: Haltbarkeit = Höchstalter ab ältestem Tag der Kette
	"KT-RW-MUERBE": ("Rework Mürbeteig (Teigreste)", "Rework", "Mürbeteig", 7),
	"KT-RW-NUSS": ("Rework Nusskeks (Bruch)", "Rework", "Mürbeteig Nuss", 7),
	"KT-RW-SCHOKO": ("Rework schokoliert (Bruch)", "Rework", "Nuss-Schoko", 7),
	# verpackt: Haltbarkeit = MHD ab Backtag
	"KT-FW-NUSS-SCHOKO": ("Nuss-Schoko-Keks 200 g", "Fertigware", "Nuss-Schoko", 270),
	"KT-FW-KAKAO-NOUGAT": ("Kakao-Nougat-Keks 200 g", "Fertigware", "Kakao-Nougat", 270),
}


# Bio / V-Label je Artikel (Haken am Artikel)
KENNZEICHNUNG = {
	"KT-BIO-DINKEL": {"kt_bio": 1, "kt_vegan": 1},
	"KT-BIO-ZUCKER": {"kt_bio": 1, "kt_vegan": 1},
	"KT-SALZ": {"kt_bio_erlaubt": 1, "kt_vegan": 1},
	"KT-BIO-GT": {"kt_bio": 1, "kt_vegan": 1},
}


BIO_LIEFERANT = ("KT Bio Mühle", "DE-ÖKO-006")


ROHSTOFF_PREIS = {
	"KT-MEHL": 0.6,
	"KT-DINKEL": 0.9,
	"KT-ZUCKER": 0.9,
	"KT-BUTTER": 6.5,
	"KT-HASELNUSS": 9.0,
	"KT-KAKAO": 7.0,
	"KT-SCHOKO": 8.0,
	"KT-FOLIE": 4.0,
	"KT-BIO-DINKEL": 1.4,
	"KT-BIO-ZUCKER": 1.6,
	"KT-SALZ": 0.3,
}


# Fertigware: Beutel à 200 g, Karton à 12 Beutel. GTIN aus dem Nummernkreis 20 bis 29 (nur intern, Demo).
VERPACKUNG = {
	"KT-FW-NUSS-SCHOKO": {"Beutel": (0.2, "2000000000015"), "Karton": (2.4, "2000000000022")},
	"KT-FW-KAKAO-NOUGAT": {"Beutel": (0.2, "2000000000039"), "Karton": (2.4, "2000000000046")},
}


# Neue Chargen dieser Artikel sind gesperrt, bis die QS sie freigibt.
FREIGABE_PFLICHT = {"KT-BUTTER", "KT-WL-NUSS-SCHOKO", "KT-WL-KAKAO-NOUGAT"}


# Rezepte (Stücklisten): Ausbringung in kg, Zutaten in kg. Backverlust steckt im Verhältnis.
# (Silo/Tank, Artikel, Nachlauf kg). Jeder Demo-Lauf legt eigene Silos mit seinem Kürzel an,
# damit sich Läufe nicht vermischen. Im Echtbetrieb gibt es jedes Silo genau einmal.
SILOS = [
	("Silo Weizenmehl 550", "KT-MEHL", 100),
	("Silo Dinkelmehl 630", "KT-DINKEL", 100),
	("Silo Zucker", "KT-ZUCKER", 50),
	("Tank Zuckersirup", "KT-SIRUP", 20),
]


# Weitere Lager (Demo-Namen, bitte durch die echten ersetzen)
UMLAGER_LAGER = ["Außenlager (Demo)"]


REZEPTE = {
	"KT-GT-MUERBE": (100, [("KT-MEHL", 60), ("KT-ZUCKER", 20), ("KT-BUTTER", 20)]),
	"KT-NOUGAT": (30, [("KT-ZUCKER", 10), ("KT-HASELNUSS", 10), ("KT-KAKAO", 5), ("KT-BUTTER", 5)]),
	"KT-TV-NUSS": (60, [("KT-GT-MUERBE", 50), ("KT-HASELNUSS", 10)]),
	"KT-TV-KAKAO": (100, [("KT-GT-MUERBE", 85), ("KT-DINKEL", 5), ("KT-KAKAO", 5), ("KT-SIRUP", 5)]),
	# Wasser wird nicht als Charge geführt, daher Ausbringung größer als Einsatz
	"KT-SIRUP": (100, [("KT-ZUCKER", 60)]),
	"KT-BIO-GT": (100, [("KT-BIO-DINKEL", 70), ("KT-BIO-ZUCKER", 25), ("KT-SALZ", 5)]),
	"KT-BW-NUSS": (85, [("KT-TV-NUSS", 100)]),
	"KT-BW-KAKAO": (85, [("KT-TV-KAKAO", 100)]),
	"KT-WL-NUSS-SCHOKO": (54, [("KT-BW-NUSS", 48), ("KT-SCHOKO", 6)]),
	"KT-WL-KAKAO-NOUGAT": (100, [("KT-BW-KAKAO", 80), ("KT-NOUGAT", 20)]),
	"KT-FW-NUSS-SCHOKO": (40, [("KT-WL-NUSS-SCHOKO", 40), ("KT-FOLIE", 1)]),
	"KT-FW-KAKAO-NOUGAT": (50, [("KT-WL-KAKAO-NOUGAT", 50), ("KT-FOLIE", 1)]),
}


# (Rework-Artikel, Ziel-Teig, max. Anteil %). Schokolierter Bruch hat bewusst keine Regel.
REWORK_REGELN = [
	("KT-RW-MUERBE", "KT-GT-MUERBE", 10),
	("KT-RW-MUERBE", "KT-TV-NUSS", 10),
	("KT-RW-MUERBE", "KT-TV-KAKAO", 10),
	("KT-RW-NUSS", "KT-TV-NUSS", 10),
]


# Prüfpläne nach der HACCP-Auflistung (2.1.1 FO, Version 5). Grenzwerte von dort übernommen.
PRUEFPLAENE = [
	{
		"titel": "Reinigung vor Bio",
		"lenkung": "CP",
		"ausloeser": "Bei Umstellung auf Bio",
		"art": "Ja/Nein",
		"frage": "Linie, Kessel und Behälter gereinigt bzw. Spülcharge gefahren?",
		"bei_abweichung": "Annahme verweigern",
		"korrekturmassnahme": "Erst reinigen oder Spülcharge fahren und als konventionell buchen",
		"dokument": "Bio-Handbuch: Trennung und Reinigung",
	},
	{
		"titel": "Metalldetektor Verpackung",
		"lenkung": "CCP",
		"ausloeser": "Regelmäßig an der Station",
		"intervall_minuten": 60,
		"sperrt_wenn_faellig": 1,
		"stationen": ["Verpackung"],
		"art": "Prüfkörper",
		"frage": "Prüfkörper durch den Metalldetektor geschickt: erkannt?",
		"pruefkoerper": "Fe 2,5 mm\nBronze 2,5 mm\nMessing 2,5 mm\nEdelstahl 2,5 mm",
		"bei_abweichung": "Sperren",
		"korrekturmassnahme": "Ware sperren, Sperrprotokoll, Metalldetektor prüfen lassen",
		"dokument": "FO 3.10.12 Prüfprotokoll",
	},
	{
		"titel": "Metalldetektor Herzenboden",
		"lenkung": "CCP",
		"ausloeser": "Regelmäßig an der Station",
		"intervall_minuten": 60,
		"sperrt_wenn_faellig": 1,
		"stationen": ["Herzen Verpackung"],
		"art": "Prüfkörper",
		"frage": "Kalfass (garnierte Herzen): Prüfkörper durch den Metalldetektor geschickt, erkannt?",
		"pruefkoerper": "Fe 2,8 mm",
		"bei_abweichung": "Sperren",
		"korrekturmassnahme": "Ware sperren, Sperrprotokoll",
		"dokument": "3.8.6 MC Herzenboden",
	},
	{
		"titel": "Brix Invertzuckersirup",
		"lenkung": "CP",
		"ausloeser": "Beim Herstellen",
		"artikel": ["KT-SIRUP"],
		"art": "Messwert",
		"frage": "Brix-Wert der Kochung",
		"einheit": "°Brix",
		"min_wert": "80",
		"max_wert": "84",
		"bei_abweichung": "Sperren",
		"korrekturmassnahme": "Ware sperren, weiter aufkochen, ggf. verwerfen, Sirup neu kochen",
		"dokument": "FO 3.7.5 Invertzuckersirup",
	},
	{
		"titel": "Temperatur Kühlware Wareneingang",
		"lenkung": "CP",
		"ausloeser": "Beim Wareneingang",
		"artikel": ["KT-BUTTER"],
		"art": "Messwert",
		"frage": "Kerntemperatur bei Anlieferung",
		"einheit": "°C",
		"max_wert": "6",
		"bei_abweichung": "Annahme verweigern",
		"korrekturmassnahme": "Warenannahme verweigern und retournieren, auf dem Lieferschein dokumentieren",
		"dokument": "3.3.4 FO Wareneingangskontrolle",
	},
]


# Etiketten-, Gewichts- und übrige Pflichtkontrollen laufen auf Papier (alle 20 min), nicht im ERP
AUF_PAPIER = ["Etikettencheck Verpackung", "Gewichtskontrolle VE"]
