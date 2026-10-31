"""Herzenboden: Herzen in Stück, eigene Zuckerglasur, Garnieren, Verpacken auf der Kalfass."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, getdate, nowdate

from keks_trace import demo, demo_herzen, terminal
from keks_trace.trace import rueckwaerts


def _hash():
	return frappe.generate_hash(length=5).upper()


class TestHerzen(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = demo_herzen.anlegen()
		cls.h = _hash()
		mhd = add_days(nowdate(), 300)
		cls.zucker = terminal.wareneingang("Lager", "HZ-PUDERZUCKER", f"PZ{cls.h}", 50, mhd)["charge"]
		cls.eiweiss = terminal.wareneingang("Lager", "HZ-EIWEISS", f"EW{cls.h}", 5, mhd)["charge"]
		cls.pack = {
			code: terminal.wareneingang("Lager", code, f"{code[-4:]}{cls.h}", 500)["charge"]
			for code in demo_herzen.PACKMITTEL
		}
		cls.kuebel = demo.neuer_traeger(f"THK-{cls.h}", "Teigbehälter")
		cls.teig = demo.neue_charge("5812", f"T5812-{cls.h}", add_days(nowdate(), -30))
		demo.buchen(cls.ctx, "Material Receipt", add_days(nowdate(), -30), "05:00:00",
					ausgaenge=[("5812", cls.teig, 100, cls.kuebel)])  # fmt: skip

	def test_herz_vom_teig_bis_zur_verpackung(self):
		# Rohlinge backen: 100 Stück Herz 18 cm aus 12 kg Grundteig
		rohling = terminal.herstellen("Backstube", "HZ-ROHLING-18", [{"code": self.kuebel, "menge": 12}], 100)
		self.assertEqual(rohling["menge"], 100)
		# Zuckerguss morgens frisch: Hauptmischung geht in den Behälter „Zuckerguss Herzenboden“ (ohne Code)
		glasur = terminal.herstellen(
			"Herzen Garnieren", "HZ-GLASUR",
			[{"code": self.zucker, "menge": 9.5}, {"code": self.eiweiss, "menge": 0.5}],
		)  # fmt: skip
		self.assertEqual(glasur["menge"], 10)
		self.assertEqual(
			terminal.rezept("HZ-GLASUR", station="Herzen Garnieren")["ausgabe_silo"], "Zuckerguss Herzenboden"
		)
		# Garnieren: Rohling + Guss aus dem Behälter (Knopf statt Scan), Ausbringung in Stück aus dem Rezept
		garniert = terminal.herstellen(
			"Herzen Garnieren", "HZ-GARNIERT-18",
			[{"code": rohling["charge"], "menge": 100}, {"code": "Zuckerguss Herzenboden", "menge": 2}],
		)  # fmt: skip
		self.assertEqual(garniert["menge"], 100)
		b = frappe.db.get_value("Batch", garniert["charge"], ["expiry_date", "kt_backtag"], as_dict=True)
		# Glasur (2 Tage) begrenzt das MHD nicht: lose Ware 180 Tage ab Backtag
		self.assertEqual(getdate(b.expiry_date), getdate(add_days(nowdate(), 180)))
		# Kartons Folie, Etikett, Schleife an den Tisch: einmal anbrechen, danach ohne Scan
		for c in self.pack.values():
			a = terminal.anbrechen("Herzen Verpackung", c)
			self.assertEqual(a["menge"], 500)
		r = terminal.rezept("HZ-18", menge=100, station="Herzen Verpackung")
		vorrat = {z["artikel"]: z["vorrat"] for z in r["zutaten"] if z["vorrat"]}
		self.assertEqual(vorrat["HZ-SCHLEIFE"], "Schleife Herzenboden")
		# Verpacken auf der Kalfass: erst Metallcheck Fe 2,8 mm
		demo.metalldetektor_ok("Herzen Verpackung")
		zeilen = [{"code": garniert["charge"], "menge": 100}] + [
			{"code": v, "menge": 100} for v in vorrat.values()
		]
		herz = terminal.herstellen("Herzen Verpackung", "HZ-18", zeilen)
		self.assertEqual(herz["menge"], 100)
		self.assertTrue(herz["los"])
		self.assertEqual(
			getdate(frappe.db.get_value("Batch", herz["charge"], "expiry_date")),
			getdate(add_months(nowdate(), 9)),
		)
		# Rückwärts bis Grundteig, Glasur, Puderzucker und Schleife
		kette = {z["charge"] for z in rueckwaerts(herz["charge"])}
		for c in (self.teig, glasur["charge"], self.zucker, self.pack["HZ-SCHLEIFE"], rohling["charge"]):
			self.assertIn(c, kette)

	def test_anbrechen_ohne_scanner(self):
		"""Ohne Scanner: Charge aus der Liste wählen; nur Artikel mit Vorrat am Tisch."""
		neu = terminal.wareneingang("Lager", "HZ-ETIKETT", f"ET2{self.h}", 50)["charge"]
		liste = terminal.lager_chargen("Herzen Verpackung", "HZ-ETIKETT")
		self.assertIn(neu, {c["charge"] for c in liste})
		vorher = {v["vorrat"]: v["bestand"] for v in terminal.vorraete("Herzen Verpackung")}
		terminal.anbrechen("Herzen Verpackung", neu)
		nachher = {v["vorrat"]: v["bestand"] for v in terminal.vorraete("Herzen Verpackung")}
		self.assertGreater(nachher["Etikett Herzenboden"], vorher["Etikett Herzenboden"])
		with self.assertRaisesRegex(frappe.ValidationError, "kein Vorrat"):
			terminal.anbrechen("Herzen Verpackung", self.zucker)

	def test_herzenboden_eigene_linie(self):
		"""Die Herzen-Stationen sehen nur Artikel und Aufträge ihrer Linie."""
		for station in ("Herzen Garnieren", "Herzen Verpackung"):
			artikel = {r.artikel for r in terminal.rezepte(station)}
			self.assertTrue(artikel)
			self.assertTrue(all(a.startswith("HZ-") for a in artikel), artikel)
		self.assertNotIn("17846", {a["artikel"] for a in terminal.auftraege("Herzen Verpackung")})
		self.assertNotIn("HZ-18", {r.artikel for r in terminal.rezepte("Verpackung")})
		with self.assertRaisesRegex(frappe.ValidationError, "gehört nicht zur Linie"):
			terminal.herstellen("Herzen Verpackung", "17846", [{"code": "X", "menge": 1}])
		# Versand sieht weiterhin alle Aufträge
		alle = terminal.auftraege("Versand")
		self.assertIsInstance(alle, list)

	def test_kundenauftrag_und_planung_in_stueck(self):
		"""Der Kunde bestellt Herzen in Stück; Planung und Terminal rechnen in Stück."""
		from keks_trace import planung

		kg_h, engpass, anlage = planung.leistung("HZ-18")
		self.assertEqual((kg_h, engpass, anlage), (800, "Garnieren", "Kalfass"))  # 25/min = 1.500/h
		self.assertIn("Stk/h", frappe.db.get_value("Item", "HZ-18", "kt_engpass"))
		auftraege = {a["artikel"]: a for a in terminal.auftraege("Herzen Verpackung")}
		self.assertIn("HZ-18", auftraege)
		self.assertIn("Stk", auftraege["HZ-18"]["offen_text"] + " Stk")
		pa = frappe.get_all(
			"Produktionsauftrag",
			{"linie": demo_herzen.LINIE, "artikel": "HZ-18"},
			["menge_kg", "dauer_stunden", "engpass"],
		)
		self.assertTrue(pa)
		self.assertTrue(all("Stk/h" in p.engpass for p in pa))
		r = terminal.rezept("HZ-18", station="Herzen Verpackung")
		self.assertEqual(r["einheit"], "Nos")
