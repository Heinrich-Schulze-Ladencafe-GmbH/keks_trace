"""GS1-Codes lesen: GS1-128, GS1-DataMatrix/QR (Element-Strings) und einfache EAN/GTIN.

Nur was wir brauchen: SSCC (00), GTIN (01/02), Charge (10), Datumsfelder (11/13/15/17), Serie (21),
Anzahl (37), Nettogewicht kg (310n). Unbekannte Datenbezeichner beenden das Lesen; was davor stand,
bleibt gültig. Das Ergebnis wird am Terminal nur vorgeschlagen - der Mensch sieht es vor dem Buchen.

Trennzeichen FNC1 kommt vom Scanner als ASCII 29 (GS). Ohne GS kann ein Feld variabler Länge
(z. B. Charge) nur am Ende stehen; sonst würde es die folgenden Felder verschlucken.
"""

import calendar
import re
from datetime import date

GS = "\x1d"

# Vordefinierte feste Längen (Datenbezeichner + Daten) nach den ersten zwei Ziffern (GS1 General Specs 5.10)
FEST = {
	"00": 20, "01": 16, "02": 16, "03": 16, "04": 18, "11": 8, "12": 8, "13": 8, "14": 8, "15": 8, "16": 8,
	"17": 8, "18": 8, "19": 8, "20": 4, "31": 10, "32": 10, "33": 10, "34": 10, "35": 10, "36": 10, "41": 16,
}  # fmt: skip
# Variable Länge: Datenbezeichner -> Höchstlänge der Daten
VARIABEL = {
	"10": 20, "21": 20, "22": 20, "30": 8, "37": 8,
	"240": 30, "241": 30, "250": 30, "251": 30, "400": 30, "401": 30, "403": 30,
	**{str(n): 90 for n in range(90, 100)},
}  # fmt: skip
DATUM = {"11": "herstelldatum", "13": "packdatum", "15": "mhd", "16": "verkauf_bis", "17": "verfall"}
_PRAEFIX = re.compile(r"^\][A-Za-z][0-9]")  # Symbologie-Kennung, z. B. ]C1, ]d2, ]Q3


def pruefziffer_ok(ziffern: str) -> bool:
	if not ziffern.isdigit() or len(ziffern) < 2:
		return False
	summe = sum(int(z) * (3 if i % 2 == 0 else 1) for i, z in enumerate(reversed(ziffern[:-1])))
	return (10 - summe % 10) % 10 == int(ziffern[-1])


def gtin14(gtin: str) -> str:
	return gtin.zfill(14)


def gtin_varianten(gtin: str) -> list[str]:
	"""GTIN in den Schreibweisen, in denen sie am Artikel stehen kann (14, 13, 12 Stellen)."""
	g = gtin14(gtin)
	return list(dict.fromkeys([g, g[1:], g[2:]] + ([g[6:]] if g.startswith("000000") else [])))


def datum(jjmmtt: str, heute: date | None = None) -> date | None:
	"""JJMMTT nach GS1: Jahrhundert so, dass das Jahr -49 bis +50 Jahre um heute liegt; TT=00 = Monatsende."""
	if len(jjmmtt) != 6 or not jjmmtt.isdigit():
		return None
	heute = heute or date.today()
	jj, mm, tt = int(jjmmtt[:2]), int(jjmmtt[2:4]), int(jjmmtt[4:])
	if not 1 <= mm <= 12:
		return None
	jahr = heute.year // 100 * 100 + jj
	if jahr - heute.year > 50:
		jahr -= 100
	elif heute.year - jahr > 49:
		jahr += 100
	letzter = calendar.monthrange(jahr, mm)[1]
	if tt == 0:
		tt = letzter
	if tt > letzter:
		return None
	return date(jahr, mm, tt)


def _bereinigen(code: str) -> tuple[str, bool]:
	"""Gibt (Text, menschenlesbar) zurück. Menschenlesbar = (01)…(10)… mit Klammern."""
	c = (code or "").strip()
	c = _PRAEFIX.sub("", c)
	if c.startswith(GS):
		c = c[1:]
	if c.startswith("("):
		return c, True
	return c, False


def _klammern(c: str) -> list[tuple[str, str]] | None:
	teile = re.findall(r"\((\d{2,4})\)([^(]*)", c)
	if not teile or "".join(f"({a}){w}" for a, w in teile) != c:
		return None
	return [(a, w.strip().rstrip(GS)) for a, w in teile]


def _roh(c: str) -> tuple[list[tuple[str, str]], str]:
	"""Element-String ohne Klammern zerlegen. Gibt (Felder, nicht gelesener Rest) zurück."""
	felder = []
	i = 0
	while i < len(c):
		if c[i] == GS:
			i += 1
			continue
		zwei = c[i : i + 2]
		if zwei in FEST:
			laenge = FEST[zwei]
			ai_laenge = 4 if zwei in ("31", "32", "33", "34", "35", "36") else (3 if zwei == "41" else 2)
			stueck = c[i : i + laenge]
			if len(stueck) != laenge or GS in stueck:
				return felder, c[i:]
			felder.append((stueck[:ai_laenge], stueck[ai_laenge:]))
			i += laenge
			continue
		ai = next((c[i : i + n] for n in (2, 3) if c[i : i + n] in VARIABEL), None)
		if not ai:
			return felder, c[i:]
		ende = c.find(GS, i)
		ende = len(c) if ende < 0 else ende
		wert = c[i + len(ai) : ende]
		if not wert or len(wert) > VARIABEL[ai]:
			return felder, c[i:]
		felder.append((ai, wert))
		i = ende
	return felder, ""


def lesen(code: str, heute: date | None = None) -> dict | None:
	"""GS1-Element-String lesen. None, wenn es kein GS1-Code ist (dann ist es z. B. eine Charge im Klartext).

	Ergebnis: gtin, charge, mhd (date), herstelldatum, sscc, serie, anzahl, netto_kg, rest (nicht gelesen).
	"""
	c, lesbar = _bereinigen(code)
	if not c:
		return None
	if lesbar:
		felder, rest = _klammern(c), ""
		if felder is None:
			return None
	else:
		# Ohne Klammern nur, wenn es wie ein GS1-Code aussieht: beginnt mit 00/01/02 und ist lang genug
		if not (c[:2] in ("00", "01", "02") and len(c) >= 16 and c[:2].isdigit()):
			return None
		felder, rest = _roh(c)
		if not felder:
			return None
	erg: dict = {"felder": felder, "rest": rest}
	for ai, wert in felder:
		if ai in ("01", "02"):
			if not pruefziffer_ok(wert):
				return None
			erg["gtin"] = wert
			if ai == "02":
				erg["inhalt"] = True
		elif ai == "00":
			if not pruefziffer_ok(wert):
				return None
			erg["sscc"] = wert
		elif ai == "10":
			erg["charge"] = wert
		elif ai == "21":
			erg["serie"] = wert
		elif ai == "37":
			erg["anzahl"] = int(wert) if wert.isdigit() else None
		elif ai in DATUM:
			erg[DATUM[ai]] = datum(wert, heute)
		elif len(ai) == 4 and ai.startswith("310") and wert.isdigit():
			erg["netto_kg"] = int(wert) / 10 ** int(ai[3])
	# MHD: (15) Mindesthaltbarkeit, sonst (17) Verbrauchsdatum
	erg["mhd"] = erg.get("mhd") or erg.get("verfall")
	return erg


def ean(code: str) -> str | None:
	"""Einfache EAN/GTIN (8, 12, 13 oder 14 Ziffern mit gültiger Prüfziffer), sonst None."""
	c, _ = _bereinigen(code)
	if c.isdigit() and len(c) in (8, 12, 13, 14) and pruefziffer_ok(c):
		return c
	return None
