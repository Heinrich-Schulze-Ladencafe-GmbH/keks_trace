"""ZPL II für Etikettendrucker im Netz (Zebra; Honeywell PM43 und PX6i mit ZSim).

Reine Textbausteine ohne Frappe: Maße in mm, umgerechnet in Punkte je Auflösung (203 oder 300 dpi).
Strichcodes ohne Klartextzeile des Druckers; den Klartext mit Klammern setzt das Etikett selbst.

GS1-128: Code 128 im Modus N mit Startcodes; FNC1 als „>8“ (Zebra-Handbuch, ^BC, „Invocation Characters“).
Zeichensatz C für Ziffernpaare, B für alles andere. Das Trennzeichen nach Feldern variabler Länge (GS)
wird in den Daten als "\x1d" übergeben (wie in gs1.py) und als FNC1 gesetzt.
"""

import math
import re

FNC1 = "\x1d"
MODUL_GS1_MM = 0.495  # GS1: kleinste Modulbreite für Logistik-Etiketten (SSCC)


class Etikett:
	"""Ein Etikett aufbauen: ``e = Etikett(105, 148, 203); e.text(...); e.zpl()``."""

	def __init__(self, breite_mm: float, hoehe_mm: float, dpi: int = 203):
		if dpi not in (203, 300):
			raise ValueError("dpi muss 203 oder 300 sein")
		self.dpmm = 8 if dpi == 203 else 12  # Punkte je mm, wie die Drucker selbst rechnen
		self.breite, self.hoehe = breite_mm, hoehe_mm
		self.teile: list[str] = []

	def p(self, mm: float) -> int:
		return max(0, round(mm * self.dpmm))

	def text(self, x, y, hoehe, text, breite=None, zeilen=1, mitte=False):
		"""Text ab (x, y) in mm, Schrifthöhe in mm. Zu lang wird gekürzt (…), höchstens ``zeilen`` Zeilen."""
		text = str(text or "").replace("\n", " ").strip()
		if not text:
			return
		breite = breite if breite is not None else self.breite - x - 3
		text = kuerzen(text, zeichen_je_zeile(breite, hoehe) * zeilen)
		h = self.p(hoehe)
		block = f"^FB{self.p(breite)},{zeilen},0,{'C' if mitte else 'L'},0" if (zeilen > 1 or mitte) else ""
		self.teile.append(f"^FO{self.p(x)},{self.p(y)}^A0N,{h},{h}{block}^FH^FD{feld(text)}^FS")

	def umgekehrt(self, x, y, breite, hoehe, zeilen):
		"""Schwarzer Kasten mit weißer Schrift (z. B. TEST). ``zeilen``: [(Schrifthöhe mm, Text), ...]."""
		self.teile.append(f"^FO{self.p(x)},{self.p(y)}^GB{self.p(breite)},{self.p(hoehe)},{self.p(hoehe)}^FS")
		oben = y + 1
		for h, text in zeilen:
			text = kuerzen(str(text), zeichen_je_zeile(breite - 2, h))
			self.teile.append(
				f"^FO{self.p(x + 1)},{self.p(oben)}^A0N,{self.p(h)},{self.p(h)}"
				f"^FB{self.p(breite - 2)},1,0,C,0^FR^FH^FD{feld(text)}^FS"
			)
			oben += h + 0.8

	def linie(self, x, y, breite, staerke=0.4):
		s = max(1, self.p(staerke))
		self.teile.append(f"^FO{self.p(x)},{self.p(y)}^GB{self.p(breite)},{s},{s}^FS")

	def rahmen(self, x, y, breite, hoehe, staerke=0.4):
		s = max(1, self.p(staerke))
		self.teile.append(f"^FO{self.p(x)},{self.p(y)}^GB{self.p(breite)},{self.p(hoehe)},{s}^FS")

	def gs1_128(self, y, hoehe, daten, x=None, breite=None, modul_mm=MODUL_GS1_MM) -> float:
		"""GS1-128 mittig (oder ab x). Gibt die gewählte Modulbreite in mm zurück (kleiner, wenn sonst zu breit)."""
		felder, symbole = code128(daten, gs1=True)
		return self._code128(y, hoehe, felder, symbole, x, breite, modul_mm)

	def code128(self, y, hoehe, daten, x=None, breite=None, modul_mm=0.375) -> float:
		felder, symbole = code128(daten, gs1=False)
		return self._code128(y, hoehe, felder, symbole, x, breite, modul_mm)

	def _code128(self, y, hoehe, felder, symbole, x, breite, modul_mm):
		breite = breite if breite is not None else self.breite - 2 * (x if x is not None else 4)
		module = code128_module(symbole)
		punkte = modul_punkte(module, self.p(breite), self.p(modul_mm))
		links = self.p(x) if x is not None else max(0, (self.p(self.breite) - module * punkte) // 2)
		self.teile.append(f"^BY{punkte},3^FO{links},{self.p(y)}^BCN,{self.p(hoehe)},N,N,N,N^FD{felder}^FS")
		return punkte / self.dpmm

	def ean(self, y, hoehe, code, x=None):
		"""EAN-13 (mit Ziffern darunter) oder ITF-14 für Kartons; sonst Code 128."""
		code = str(code)
		if code.isdigit() and len(code) == 13:
			punkte = 3 if self.dpmm == 8 else 4  # 0,375 / 0,33 mm (EAN: 0,264-0,66 mm)
			links = self.p(x) if x is not None else max(0, (self.p(self.breite) - 113 * punkte) // 2)
			self.teile.append(f"^BY{punkte}^FO{links},{self.p(y)}^BEN,{self.p(hoehe)},Y,N^FD{code[:12]}^FS")
		elif code.isdigit() and len(code) == 14:
			punkte = 3 if self.dpmm == 8 else 5
			links = self.p(x) if x is not None else max(0, (self.p(self.breite) - 135 * punkte) // 2)
			self.teile.append(f"^BY{punkte},3^FO{links},{self.p(y)}^B2N,{self.p(hoehe)},Y,N,N^FD{code}^FS")
		else:
			self.code128(y, hoehe, code, x=x)

	def qr(self, x, y, code, groesse_mm=30, version=None):
		"""QR-Code ab (x, y), Fehlerkorrektur M. ``version`` (1-40) bestimmt die Modulzahl für die Größe."""
		module = 17 + 4 * (version or 2) + 2  # mit kleinem Rand
		vergroesserung = max(1, min(10, self.p(groesse_mm) // module))
		self.teile.append(f"^FO{self.p(x)},{self.p(y)}^BQN,2,{vergroesserung}^FDMA,{feld(str(code))}^FS")

	def datamatrix(self, x, y, code, groesse_mm=26) -> int:
		"""Data Matrix (ECC 200) ab (x, y), höchstens ``groesse_mm`` groß. Gibt die Modulgröße in Punkten zurück.

		Erlaubt sind Buchstaben, Ziffern und - . / (Nummern wie KL-H1-ACF4); sonst ValueError, denn das
		Escape-Zeichen von ^BX (_) und die ZPL-Steuerzeichen sollen nicht in den Daten stehen.
		"""
		code = str(code)
		if not DM_ZEICHEN.match(code):
			raise ValueError(f"Für Data Matrix nur Buchstaben, Ziffern und - . / erlaubt: {code!r}")
		kante = dm_module(code)
		punkte = max(2, self.p(groesse_mm) // (kante + 2))  # mit Ruhezone von je einem Modul
		# Spalten = Zeilen = Kante, Seitenverhältnis 1: quadratisch und so groß wie berechnet (_ ist das
		# Escape-Zeichen von ^BX; es kommt in den erlaubten Zeichen nicht vor)
		feld = f"^BXN,{punkte},200,{kante},{kante},6,_,1"
		self.teile.append(f"^FO{self.p(x + 1)},{self.p(y + 1)}{feld}^FD{code}^FS")
		return punkte

	def grafik(self, x, y, grafik: "Grafik"):
		"""Schwarz-Weiß-Bild (siehe ``bild``) ab (x, y) in mm."""
		self.teile.append(
			f"^FO{self.p(x)},{self.p(y)}^GFA,{grafik.bytes},{grafik.bytes},{grafik.je_zeile},{grafik.hex}^FS"
		)

	def zpl(self, anzahl: int = 1) -> str:
		kopf = f"^XA^CI28^PW{self.p(self.breite)}^LL{self.p(self.hoehe)}^LH0,0"
		fuss = f"^PQ{int(anzahl)}^XZ" if anzahl and int(anzahl) > 1 else "^XZ"
		return kopf + "".join(self.teile) + fuss + "\n"


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------


DM_ZEICHEN = re.compile(r"^[A-Za-z0-9./-]{1,60}$")
# ECC 200, quadratisch: Kantenlänge in Modulen und Datenwörter. Im ASCII-Modus braucht jedes Zeichen höchstens
# ein Datenwort (zwei Ziffern zusammen eins); so ist die Größe nie unterschätzt. Der Drucker wählt selbst.
DM_GROESSEN = (
	(10, 3),
	(12, 5),
	(14, 8),
	(16, 12),
	(18, 18),
	(20, 22),
	(22, 30),
	(24, 36),
	(26, 44),
	(32, 62),
)


def dm_module(code: str) -> int:
	"""Kantenlänge des Data-Matrix-Symbols in Modulen (höchstens; ASCII-Kodierung)."""
	n = len(str(code))
	for kante, zeichen in DM_GROESSEN:
		if n <= zeichen:
			return kante
	return 36


class Grafik:
	"""Bild für ^GFA: Hex-Daten, Bytes je Zeile, Größe in Punkten."""

	def __init__(self, hex_daten: str, je_zeile: int, breite: int, hoehe: int):
		self.hex, self.je_zeile, self.breite, self.hoehe = hex_daten, je_zeile, breite, hoehe
		self.bytes = je_zeile * hoehe


def bild(datei, hoehe_punkte: int, max_breite_punkte: int | None = None, schwelle: int = 160) -> Grafik:
	"""Bilddatei (PNG, JPG ...) als Schwarz-Weiß-Grafik in ``hoehe_punkte`` Höhe, Seitenverhältnis bleibt.

	Transparentes wird weiß (sonst würde ein transparenter Hintergrund ein schwarzer Kasten). Danach gilt:
	dunkler als ``schwelle`` (0-255) wird schwarz. Farben wie Rot oder Dunkelblau sind dunkel genug.
	"""
	from PIL import Image

	with Image.open(datei) as roh:
		quelle = roh.convert("RGBA")
	weiss = Image.new("RGBA", quelle.size, (255, 255, 255, 255))
	grau = Image.alpha_composite(weiss, quelle).convert("L")
	# Ränder ohne Inhalt abschneiden, damit die Höhe dem sichtbaren Logo entspricht
	rahmen = Image.eval(grau, lambda w: 255 - w).getbbox()
	if rahmen:
		grau = grau.crop(rahmen)
	breite = max(1, round(grau.width * hoehe_punkte / grau.height))
	if max_breite_punkte and breite > max_breite_punkte:
		breite = max_breite_punkte
		hoehe_punkte = max(1, round(grau.height * breite / grau.width))
	klein = grau.resize((breite, hoehe_punkte), Image.Resampling.LANCZOS)
	je_zeile = (breite + 7) // 8
	pixel = klein.load()
	zeilen = []
	for py in range(hoehe_punkte):
		werte = bytearray(je_zeile)
		for px in range(breite):
			if pixel[px, py] < schwelle:
				werte[px // 8] |= 0x80 >> (px % 8)
		zeilen.append(werte.hex().upper())
	return Grafik("".join(zeilen), je_zeile, breite, hoehe_punkte)


def feld(text: str) -> str:
	"""Text für ^FH^FD: Steuerzeichen ^ ~ und das Hex-Zeichen _ als _XX (UTF-8 mit ^CI28)."""
	aus = []
	for z in text:
		if z in "^~_":
			aus.append("_%02X" % ord(z))
		elif ord(z) < 32:
			aus.append(" ")
		else:
			aus.append(z)
	return "".join(aus)


def zeichen_je_zeile(breite_mm: float, hoehe_mm: float) -> int:
	"""Grobe Schätzung für Schrift 0 (schmal): Ziffern gut halb so breit wie hoch, Buchstaben schmaler."""
	return max(1, int(breite_mm / (hoehe_mm * 0.52)))


def kuerzen(text: str, zeichen: int) -> str:
	return text if len(text) <= zeichen else text[: max(1, zeichen - 1)].rstrip() + "…"


def code128(daten: str, gs1: bool = False) -> tuple[str, int]:
	"""Felddaten für ^BC Modus N und Zahl der Datensymbole (einschl. Wechsel und FNC1, ohne Start/Prüfz.).

	Zeichensatz C für Ziffernpaare (ab 4 Ziffern, oder ab 2 am Anfang, am Ende, oder wenn schon in C),
	sonst B. Bei GS1 steht FNC1 am Anfang; "\\x1d" in den Daten wird FNC1 (Trennzeichen).
	"""
	daten = str(daten)
	if gs1:
		daten = FNC1 + daten.lstrip(FNC1)
	aus: list[str] = []
	satz = None
	symbole = 0
	i, n = 0, len(daten)

	def ziffern(j):
		k = j
		while k < n and daten[k].isdigit():
			k += 1
		return k - j

	def wechsel(neu):
		nonlocal satz, symbole
		if satz == neu:
			return
		if satz is None:
			aus.append(">;" if neu == "C" else ">:")
		else:
			aus.append(">5" if neu == "C" else ">6")
			symbole += 1
		satz = neu

	while i < n:
		z = daten[i]
		if z == FNC1:
			if satz is None:
				wechsel("C" if ziffern(i + 1) >= 2 else "B")
			aus.append(">8")
			symbole += 1
			i += 1
			continue
		lauf = ziffern(i)
		paare = lauf - lauf % 2
		if paare and (lauf >= 4 or satz in (None, "C") or i + lauf == n):
			wechsel("C")
			aus.append(daten[i : i + paare])
			symbole += paare // 2
			i += paare
			continue
		if not (32 <= ord(z) <= 126):
			raise ValueError(f"Zeichen {z!r} ist in Code 128 B nicht darstellbar")
		wechsel("B")
		aus.append("><" if z == ">" else z)
		symbole += 1
		i += 1
	return "".join(aus), symbole


def code128_module(symbole: int) -> int:
	"""Breite in Modulen: Start + Daten + Prüfzeichen je 11, Stopp 13, Ruhezone je 10."""
	return (symbole + 2) * 11 + 13 + 20


def modul_punkte(module: int, max_punkte: int, wunsch: int) -> int:
	"""Größte Modulbreite in Punkten bis ``wunsch``, die in ``max_punkte`` passt (mindestens 1)."""
	p = max(1, wunsch)
	while p > 1 and module * p > max_punkte:
		p -= 1
	return p


def qr_version(code: str) -> int:
	"""QR-Version für Byte-Modus und Fehlerkorrektur M (reicht für kurze Codes; sonst grob geschätzt)."""
	kapazitaet_m = [14, 26, 42, 62, 84, 106, 122, 152, 180, 213]  # Bytes je Version 1-10
	laenge = len(str(code).encode())
	for v, k in enumerate(kapazitaet_m, start=1):
		if laenge <= k:
			return v
	return min(40, 10 + math.ceil((laenge - 213) / 30))
