"""Netzbild der Rückverfolgung (/netz): Knoten, Kanten, Seiten, Kunden und Belegliste.

Ausführen:
	bench --site <site> run-tests --module keks_trace.tests.test_netz
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from keks_trace import demo, netz, sperre, terminal
from keks_trace.utils import regel_nur_hinweis


def _hash():
	return frappe.generate_hash(length=6).upper() + "7"


class TestNetz(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.enterClassContext(regel_nur_hinweis("fefo_rohstoffe"))
		cls.ctx = demo.stammdaten()
		demo.metalldetektor_ok("Verpackung")
		# Ware lose + Folie -> Fertigware, auf eine Palette, an den Kunden
		cls.wl = demo.neue_charge("KT-WL-KAKAO-NOUGAT", f"WLN{_hash()}", nowdate())
		demo.buchen(
			cls.ctx, "Material Receipt", nowdate(), "05:00:00", ausgaenge=[("KT-WL-KAKAO-NOUGAT", cls.wl, 60)]
		)
		sperre.freigeben(cls.wl, "Test")
		cls.folie = demo.neue_charge("KT-FOLIE", f"FOLN{_hash()}")
		demo.buchen(
			cls.ctx, "Material Receipt", nowdate(), "05:00:00", ausgaenge=[("KT-FOLIE", cls.folie, 5)]
		)
		e = terminal.herstellen(
			"Verpackung",
			"KT-FW-KAKAO-NOUGAT",
			[{"code": cls.wl, "menge": 24}, {"code": cls.folie, "menge": 1}],
			anzahl=5,
			einheit="Karton",
		)
		cls.fw = e["charge"]
		cls.palette = terminal.palette_neu("Versand", "Versandpalette")["nve"]
		terminal.palette_beladen("Versand", cls.palette, cls.fw, 3, "Karton")
		cls.ls = terminal.lieferung("Versand", cls.ctx.kunde, [{"palette": cls.palette, "ganz": 1}])[
			"lieferschein"
		]

	def _knoten(self, d):
		return {n["id"]: n for n in d["knoten"]}

	def test_rueckwaerts_und_vorwaerts(self):
		d = netz.netz(self.fw)
		k = self._knoten(d)
		self.assertEqual(d["start"], self.fw)
		self.assertEqual(k[self.fw]["seite"], "start")
		self.assertEqual((k[self.wl]["seite"], k[self.folie]["seite"]), ("rueck", "rueck"))
		kanten = {(x["von"], x["nach"]): x for x in d["kanten"]}
		self.assertAlmostEqual(kanten[(self.wl, self.fw)]["menge"], 24)
		# Kunde hängt am Lieferschein, rechts vom Los
		kunde = k["LS:" + self.ls]
		self.assertEqual((kunde["art"], kunde["seite"]), ("kunde", "vor"))
		self.assertIn((self.fw, "LS:" + self.ls), kanten)
		# Belegliste: Einkauf nur für Rohstoffe und Packmittel, Verkauf je Lieferschein
		arten = {(b["art"], b["charge"]) for b in d["belege"]}
		self.assertIn(("Einkauf", self.folie), arten)
		self.assertNotIn(("Einkauf", self.wl), arten)  # Ware lose ist kein Einkauf
		self.assertIn(("Verkauf", self.fw), arten)

	def test_vom_packmittel_bis_zum_kunden(self):
		d = netz.netz(self.folie)
		k = self._knoten(d)
		self.assertEqual(k[self.fw]["seite"], "vor")
		self.assertIn("LS:" + self.ls, k)
		self.assertNotIn(self.wl, k)  # Geschwister (andere Zutaten) gehören nicht dazu

	def test_scan_einer_palette_und_details(self):
		p = terminal.palette_neu("Versand", "Versandpalette")["nve"]
		terminal.palette_beladen("Versand", p, self.fw, 1, "Karton")
		d = netz.netz(p)  # nur ein Los auf der Palette: gleich zeichnen
		self.assertEqual(d["start"], self.fw)
		# schon versendete Palette: Inhalt aus ihrem Verlauf
		self.assertEqual(netz.netz(self.palette)["start"], self.fw)
		x = netz.details(self.fw)
		self.assertTrue(x["herstellung"]["beleg"])
		self.assertIn("fundstellen", x)
		with self.assertRaises(frappe.ValidationError):
			netz.netz("GIBT-ES-NICHT-" + _hash())

	def test_gesperrt_sichtbar(self):
		sperre.sperren(self.wl, "Test Sperre")
		try:
			self.assertTrue(self._knoten(netz.netz(self.fw))[self.wl]["gesperrt"])
		finally:
			sperre.freigeben(self.wl, "Test")
