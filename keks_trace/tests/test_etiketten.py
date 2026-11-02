"""Etikettendrucker im Netz: ZPL (GS1-128, Text), Zuordnung an der Terminal Station, Versand per TCP.

Ein kleiner TCP-Empfänger auf 127.0.0.1 spielt den Drucker. Ob ein echter Drucker das Etikett richtig
setzt, zeigt erst der Testdruck aus der Druckermaske (Rahmen 90 x 50 mm nachmessen, Strichcode scannen).
"""

import socket
import threading
import typing
import unittest

import frappe
from frappe.tests import IntegrationTestCase

from keks_trace import demo, etiketten, gs1, terminal, zpl
from keks_trace.utils import einstellungen


class Empfaenger:
	"""Spielt einen Drucker an Port 9100: nimmt Verbindungen an und merkt sich, was ankommt."""

	def __init__(self):
		self.server = socket.socket()
		self.server.bind(("127.0.0.1", 0))
		self.server.listen()
		self.port = self.server.getsockname()[1]
		self.daten: list[bytes] = []
		self.faden = threading.Thread(target=self._laufen, daemon=True)
		self.faden.start()

	def _laufen(self):
		while True:
			try:
				verbindung, _ = self.server.accept()
			except OSError:
				return
			with verbindung:
				teile = []
				while block := verbindung.recv(65536):
					teile.append(block)
				self.daten.append(b"".join(teile))

	def warten(self, anzahl=1):
		for _ in range(100):
			if len(self.daten) >= anzahl:
				return
			threading.Event().wait(0.05)

	def schliessen(self):
		self.server.close()


def _freier_port():
	s = socket.socket()
	s.bind(("127.0.0.1", 0))
	port = s.getsockname()[1]
	s.close()
	return port


def _hash():
	return frappe.generate_hash(length=5).upper() + "7"


class TestCode128(unittest.TestCase):
	def test_sscc_ganz_in_zeichensatz_c(self):
		felder, symbole = zpl.code128("00340123450000000017", gs1=True)
		self.assertEqual(felder, ">;>800340123450000000017")
		self.assertEqual(symbole, 11)  # FNC1 + 10 Ziffernpaare

	def test_ungerade_ziffern_und_los_mit_buchstaben(self):
		daten = "02040327440000111527123137" + "120" + zpl.FNC1 + "10" + "AB12"
		felder, _ = zpl.code128(daten, gs1=True)
		# 29 Ziffern: 14 Paare in C, die letzte Ziffer in B (>6), FNC1, „10AB“ in B, „12“ am Ende in C (>5)
		self.assertEqual(felder, ">;>8" + "0204032744000011152712313712" + ">60" + ">8" + "10AB" + ">512")
		# zurückgelesen ergibt sich wieder dasselbe GS1-Etikett
		self.assertEqual(_lesen(felder), zpl.FNC1 + daten)  # GS1: FNC1 am Anfang

	def test_zurueckgelesen_gleich(self):
		for daten in ("00340123450000000017", "0204032744000011" + "15271231" + "37" + "7" + zpl.FNC1 + "106447",
		              "10L-2>X", "0104032744000011" + "10" + "A"):  # fmt: skip
			self.assertEqual(_lesen(zpl.code128(daten, gs1=True)[0]), zpl.FNC1 + daten.lstrip(zpl.FNC1))

	def test_groesser_als_zeichen_wird_verdoppelt(self):
		self.assertEqual(zpl.code128("A>B")[0], ">:A><B")

	def test_modulbreite_passt_sich_an(self):
		self.assertEqual(zpl.modul_punkte(200, 1000, 4), 4)
		self.assertEqual(zpl.modul_punkte(300, 1000, 4), 3)
		self.assertEqual(zpl.modul_punkte(5000, 1000, 4), 1)

	def test_text_steuerzeichen(self):
		self.assertEqual(zpl.feld("A^B~C_D"), "A_5EB_7EC_5FD")
		self.assertEqual(zpl.kuerzen("Butterkeks Vollkorn", 10), "Butterkek…")

	def test_aufloesung(self):
		self.assertIn("^PW840^LL1184", zpl.Etikett(105, 148, 203).zpl())
		self.assertIn("^PW1260^LL1776", zpl.Etikett(105, 148, 300).zpl())
		with self.assertRaises(ValueError):
			zpl.Etikett(100, 60, 600)


def _lesen(felder: str) -> str:
	"""ZPL-Felddaten (Modus N) zurück in die Zeichenfolge, FNC1 als GS. Nur für die Tests."""
	aus, i, satz = [], 0, None
	while i < len(felder):
		if felder[i] == ">":
			code = felder[i + 1]
			i += 2
			if code in ";5":
				satz = "C"
			elif code in ":6":
				satz = "B"
			elif code == "8":
				aus.append(zpl.FNC1)
			elif code == "<":
				aus.append(">")
			continue
		if satz == "C":
			aus.append(felder[i : i + 2])
			i += 2
		else:
			aus.append(felder[i])
			i += 1
	return "".join(aus)


class TestLayouts(unittest.TestCase):
	PALETTE: typing.ClassVar[dict] = {
		"absender": "Keks Test GmbH",
		"nve": "340327440000000012",
		"art": "Kundenpalette",
		"datum": "01.11.2026",
		"kunde": "KT Demo Handel",
		"positionen": [{"name": "Butterkeks 200 g", "los": "6447", "mhd": "31.12.2027", "anzahl_text": "40", "einheit": "Karton"}],
		"kartons": "40 Karton",
		"menge": 96.0,
		"barcode_sscc": "00340327440000000012",
		"text_sscc": "(00) 340327440000000012",
		"inhalt_barcode": "0204032744000011152712313740Ï106447",
		"inhalt_text": "(02) 04032744000011 (15) 271231 (37) 40 (10) 6447",
	}  # fmt: skip

	def test_palette(self):
		self.assertTrue(gs1.pruefziffer_ok(self.PALETTE["nve"]) and gs1.pruefziffer_ok("04032744000011"))
		z = etiketten.zpl_palette(self.PALETTE)
		self.assertTrue(z.startswith("^XA^CI28") and z.rstrip().endswith("^XZ"))
		self.assertIn(">;>800340327440000000012", z)  # SSCC als GS1-128
		self.assertIn("(00) 340327440000000012", z)
		self.assertNotIn("Ï", z)  # FNC1 von JsBarcode wird zu >8
		self.assertIn(">8", z.split(">;>802")[1])
		self.assertIn("Butterkeks 200 g", z)

	def test_karton_mit_menge_und_ean(self):
		d = {"name": "Butterkeks", "inhalt": "12 x 200 g", "los_vorschau": "6447", "mhd_vorschau": "31.12.27", "artikel": "BK-200", "ean": "4032744000011"}  # fmt: skip
		z = etiketten.zpl_karton(d, 20)
		self.assertIn("^PQ20^XZ", z)
		self.assertIn("^BEN", z)
		self.assertIn("^FD403274400001^FS", z)  # EAN-13: zwölf Ziffern, Prüfziffer setzt der Drucker

	def test_gebinde_je_code_ein_etikett(self):
		e = [
			{"code": "GB-0001", "name": "Weizenmehl Type 550", "charge": "L123", "menge": 25},
			{"code": "GB-0002"},
		]
		z = etiketten.zpl_gebinde(e)
		self.assertEqual(z.count("^XA"), 2)
		self.assertIn("^BXN,", z)  # Data Matrix wie am Kübel
		self.assertIn(",200,14,14,6,_,1^FDGB-0001^FS", z)  # 7 Zeichen: 14 x 14 Module, quadratisch
		self.assertNotIn("^BQ", z)

	def test_data_matrix_groesse_und_zeichen(self):
		self.assertEqual(zpl.dm_module("KL-H1-ACF4"), 16)  # 10 Zeichen
		self.assertEqual(zpl.dm_module("TR-ABCDEFGHIJKLM"), 18)  # 16 Zeichen (längster Code heute)
		z = zpl.Etikett(100, 70, 203)
		punkte = z.datamatrix(5, 5, "KL-H1-ACF4", groesse_mm=30)
		self.assertEqual(punkte, 240 // 18)  # 30 mm = 240 Punkte, 16 Module + Ruhezone
		for falsch in ("KL H1", "A_B", "Ä1", "x^y", ""):
			with self.assertRaises(ValueError):
				z.datamatrix(5, 5, falsch)


class TestDrucken(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = demo.stammdaten()

	def setUp(self):
		self.empfaenger = Empfaenger()
		self.addCleanup(self.empfaenger.schliessen)
		self.drucker = frappe.get_doc(
			{"doctype": "Etikettendrucker", "drucker_name": f"Test {_hash()}", "adresse": "127.0.0.1", "port": self.empfaenger.port, "dpi": "203", "etikett_breite": 105, "etikett_hoehe": 148}
		).insert()  # fmt: skip

	def _zuordnen(self, station, **felder):
		frappe.db.set_value("Terminal Station", station, felder)
		frappe.clear_document_cache("Terminal Station", station)

	def test_ohne_zuordnung_browserdruck(self):
		self._zuordnen("Lager", drucker_palette=None, drucker_karton=None, drucker_gebinde=None)
		self.assertEqual(
			terminal.start("Lager")["drucker"], {"palette": None, "karton": None, "gebinde": None}
		)
		with self.assertRaisesRegex(frappe.ValidationError, "kein Drucker"):
			etiketten.drucken("Lager", "palette", nve="1")

	def test_palette_auf_den_drucker(self):
		self._zuordnen("Lager", drucker_palette=self.drucker.name)
		self.assertEqual(terminal.start("Lager")["drucker"]["palette"], self.drucker.name)
		nve = terminal.palette_neu("Lager")["nve"]
		r = terminal.etikett_drucken("Lager", "palette", nve=nve)
		self.assertEqual(
			r, {"drucker": self.drucker.name, "art": "palette", "etiketten": 1, "grund": "Erstdruck"}
		)
		self.empfaenger.warten()
		zpl_text = self.empfaenger.daten[0].decode("utf-8")
		self.assertIn(f">;>800{nve}", zpl_text)
		self.assertTrue(gs1.pruefziffer_ok(nve))
		self.assertTrue(frappe.db.get_value("Palette", nve, "etikett_gedruckt"))  # wie beim Browserdruck

	def test_gebinde_auf_den_drucker(self):
		self._zuordnen("Backstube", drucker_gebinde=self.drucker.name)
		a, b = (
			demo.neuer_traeger(f"TR-{_hash()}", "Teigbehälter"),
			demo.neuer_traeger(f"TR-{_hash()}", "Teigbehälter"),
		)
		r = terminal.etikett_drucken("Backstube", "gebinde", codes=f"{a},{b}")
		self.assertEqual(r["etiketten"], 2)
		self.empfaenger.warten()
		self.assertEqual(self.empfaenger.daten[0].count(b"^XA"), 2)

	def test_inaktiv_heisst_browserdruck(self):
		self._zuordnen("Lager", drucker_palette=self.drucker.name)
		self.drucker.db_set("aktiv", 0)
		self.assertIsNone(etiketten.drucker_der_station("Lager")["palette"])

	def test_drucker_aus_klare_meldung(self):
		self.drucker.db_set("port", _freier_port())
		with self.assertRaisesRegex(frappe.ValidationError, "antwortet nicht"):
			etiketten.senden(self.drucker.name, "^XA^XZ")

	def test_testdruck_auch_vor_dem_einschalten(self):
		self.drucker.db_set("aktiv", 0)
		etiketten.testdruck(self.drucker.name)
		self.empfaenger.warten()
		self.assertIn(b"Rahmen genau 95 x 138 mm", self.empfaenger.daten[0])
		# Code 2 wechselt die Zeichensätze; zurückgelesen genau der Text, der darunter steht
		felder = zpl.code128(etiketten.TEST_GS1, gs1=True)[0]
		self.assertIn(">6", felder)
		self.assertIn(">5", felder)
		self.assertIn(felder.encode(), self.empfaenger.daten[0])
		self.assertEqual(_lesen(felder), zpl.FNC1 + etiketten.TEST_GS1)
		self.assertIn("ÄÖÜ".encode(), self.empfaenger.daten[0])  # UTF-8 mit ^CI28

	def test_adresse_geprueft(self):
		for falsch in ("http://10.0.0.5", "10.0.0.5:9100", "drucker eins", ""):
			with self.assertRaises(frappe.ValidationError):
				frappe.get_doc({"doctype": "Etikettendrucker", "drucker_name": f"X {_hash()}", "adresse": falsch, "port": 9100, "etikett_breite": 100, "etikett_hoehe": 60}).insert()  # fmt: skip
		with self.assertRaisesRegex(frappe.ValidationError, "Port"):
			frappe.get_doc({"doctype": "Etikettendrucker", "drucker_name": f"X {_hash()}", "adresse": "drucker-1", "port": 70000, "etikett_breite": 100, "etikett_hoehe": 60}).insert()  # fmt: skip

	def test_maske_zeigt_wo_genutzt(self):
		from keks_trace.keks_trace.doctype.etikettendrucker.etikettendrucker import genutzt

		self._zuordnen("Versand", drucker_palette=self.drucker.name, drucker_karton=self.drucker.name)
		self.assertEqual({(z["station"], z["etikett"]) for z in genutzt(self.drucker.name)},
		                 {("Versand", "Palettenetikett"), ("Versand", "Kartonlabel")})  # fmt: skip


def _logo_datei(pfad):
	"""Muster-Logo: transparenter Rand, rotes Quadrat in der Mitte (wie das Rot im Wappen)."""
	from PIL import Image

	bild = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
	for x in range(80, 120):
		for y in range(30, 70):
			bild.putpixel((x, y), (223, 0, 8, 255))
	bild.save(pfad)
	return pfad


class TestRolleUndLogo(unittest.TestCase):
	def test_layout_folgt_der_rolle(self):
		z = etiketten.zpl_palette(TestLayouts.PALETTE, 203, 100, 150)
		self.assertIn("^PW800^LL1200", z)
		# SSCC am unteren Rand: 117,5 + 2 mm (Rolle 2 mm höher als A6) = 119,5 mm = 956 Punkte
		self.assertIn(",956^BCN,184", z)

	def test_viele_positionen_auf_kleiner_rolle(self):
		e = {**TestLayouts.PALETTE, "positionen": TestLayouts.PALETTE["positionen"] * 12}
		z = etiketten.zpl_palette(e, 203, 100, 120)
		self.assertIn("weitere Positionen", z)
		self.assertEqual(z.count("Butterkeks 200 g"), 2)  # Platz für 3 Zeilen: 2 Positionen + „weitere“

	def test_mindestmass(self):
		self.assertIsNone(etiketten.zu_klein("palette", 105, 148))
		self.assertIsNone(etiketten.zu_klein("palette", 100, 120))
		self.assertIn("mindestens 100 x 120", etiketten.zu_klein("palette", 100, 60))
		self.assertIsNotNone(etiketten.zu_klein("gebinde", 100, 50))

	def test_logo_transparent_wird_weiss(self):
		import tempfile

		with tempfile.TemporaryDirectory() as ordner:
			g = zpl.bild(_logo_datei(ordner + "/logo.png"), 40)
		# Leerer Rand wird abgeschnitten: nur das Quadrat bleibt, also ganz schwarz
		self.assertEqual((g.breite, g.hoehe), (40, 40))
		self.assertEqual(g.hex, "FF" * 5 * 40)

	def test_logo_auf_dem_etikett(self):
		import tempfile

		with tempfile.TemporaryDirectory() as ordner:
			g = zpl.bild(_logo_datei(ordner + "/logo.png"), 80)
		z = etiketten.zpl_karton({"name": "Butterkeks"}, 1, 203, 100, 60, logo_grafik=g)
		self.assertIn(f"^GFA,{g.bytes},{g.bytes},{g.je_zeile},", z)
		self.assertIn("^FO688,24^GFA", z)  # oben rechts: 100 - 4 - 10 mm Logo = 86 mm = 688 Punkte


class TestRolleZuordnen(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = demo.stammdaten()

	def _drucker(self, b, h):
		return frappe.get_doc(
			{"doctype": "Etikettendrucker", "drucker_name": f"R {_hash()}", "adresse": "127.0.0.1", "port": 9100, "etikett_breite": b, "etikett_hoehe": h}
		).insert()  # fmt: skip

	def test_zu_kleine_rolle_nicht_zuordnen(self):
		klein = self._drucker(100, 60)
		s = frappe.get_doc("Terminal Station", "Lager")
		s.drucker_karton = klein.name  # passt
		s.save()
		s.drucker_palette = klein.name  # passt nicht
		with self.assertRaisesRegex(frappe.ValidationError, "mindestens 100 x 120"):
			s.save()

	def test_rolle_verkleinern_wenn_zugeordnet(self):
		gross = self._drucker(105, 148)
		s = frappe.get_doc("Terminal Station", "Lager")
		s.drucker_palette = gross.name
		s.save()
		gross.etikett_hoehe = 60
		with self.assertRaisesRegex(frappe.ValidationError, "zu klein"):
			gross.save()

	def test_rollengroesse_pflicht_und_plausibel(self):
		with self.assertRaises(frappe.ValidationError):
			self._drucker(100, 0)
		with self.assertRaises(frappe.ValidationError):
			self._drucker(400, 100)

	def test_behaelter_code_nur_scanbare_zeichen(self):
		with self.assertRaisesRegex(frappe.ValidationError, "nur aus Buchstaben"):
			demo.neuer_traeger(f"TR {_hash()}", "Teigbehälter")
		self.assertTrue(demo.neuer_traeger(f"TR-{_hash()}", "Teigbehälter"))

	def test_logo_aus_den_einstellungen(self):
		import os
		import tempfile

		with tempfile.TemporaryDirectory() as ordner:
			pfad = _logo_datei(os.path.join(ordner, "logo.png"))
			with open(pfad, "rb") as f:
				datei = frappe.get_doc({"doctype": "File", "file_name": f"logo-{_hash()}.png", "content": f.read(), "is_private": 0}).insert()  # fmt: skip
		with einstellungen(etikett_logo=datei.file_url):
			g = etiketten.logo(203, 10)
		self.assertEqual(g.hoehe, 80)
		with einstellungen(etikett_logo="/files/gibt-es-nicht.png"):
			self.assertIsNone(etiketten.logo(203, 10))  # ohne Logo drucken statt gar nicht
