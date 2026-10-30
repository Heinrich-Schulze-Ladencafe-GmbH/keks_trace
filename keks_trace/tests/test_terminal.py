"""Tests für die Terminal-Schnittstelle (Backstube, Verpackung, Lager, Versand).

Ausführen:
	bench --site <site> run-tests --module keks_trace.tests.test_terminal
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from keks_trace import demo, palette, sperre, terminal
from keks_trace.terminal import TerminalFehler


def _hash():
	return frappe.generate_hash(length=6).upper()


class TestTerminal(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = demo.stammdaten()
		cls.h = _hash()
		cls.silo = demo.silos_anlegen(cls.ctx, "TT" + cls.h)
		frappe.cache.delete_value("kt_silo_lager")
		cls.tb = demo.neuer_traeger(f"TTB-{cls.h}", "Teigbehälter")
		cls.tb2 = demo.neuer_traeger(f"TTB2-{cls.h}", "Teigbehälter")
		cls.rb = demo.neuer_traeger(f"TRB-{cls.h}", "Rework-Behälter")
		mhd = add_days(nowdate(), 200)
		for artikel, menge in (("KT-MEHL", 500), ("KT-ZUCKER", 300)):
			terminal.wareneingang("Lager", artikel, f"L{cls.h}-{artikel}", menge, mhd, silo=cls.silo[artikel])
		cls.butter = terminal.wareneingang("Lager", "KT-BUTTER", f"BU{cls.h}", 100, add_days(nowdate(), 30))
		cls.nuss = terminal.wareneingang("Lager", "KT-HASELNUSS", f"HN{cls.h}", 50, mhd)["charge"]

	def _grundteig(self, behaelter=None):
		return terminal.herstellen(
			"Backstube",
			"KT-GT-MUERBE",
			[
				{"code": self.silo["KT-MEHL"], "menge": 60},
				{"code": self.silo["KT-ZUCKER"], "menge": 20},
				{"code": self.butter["charge"], "menge": 20},
			],
			ziel_behaelter=behaelter,
		)

	def _butter_frei(self):
		if frappe.db.get_value("Batch", self.butter["charge"], "kt_status") == "Gesperrt":
			sperre.freigeben(self.butter["charge"], "Test")

	# ------------------------------------------------------------------ Wareneingang
	def test_01_wareneingang_ins_silo_und_station(self):
		silo_lager = frappe.db.get_value("Silo", self.silo["KT-MEHL"], "warehouse")
		self.assertEqual(terminal.charge_lager(f"L{self.h}-KT-MEHL"), {silo_lager: 500})
		se = frappe.db.get_value(
			"Stock Entry Detail", {"batch_no": f"L{self.h}-KT-MEHL", "t_warehouse": silo_lager}, "parent"
		)
		self.assertEqual(frappe.db.get_value("Stock Entry", se, "kt_station"), "Lager")

	def test_02_wareneingang_freigabepflicht_und_pflichtfelder(self):
		self.assertTrue(self.butter["gesperrt"])
		with self.assertRaises(TerminalFehler):
			terminal.wareneingang("Lager", "KT-MEHL", "", 10, nowdate())
		with self.assertRaises(TerminalFehler):
			terminal.wareneingang("Lager", "KT-MEHL", "X1", 10, nowdate(), silo=self.silo["KT-ZUCKER"])

	# ------------------------------------------------------------------ Prüfen beim Scannen
	def test_03_scan_pruefungen(self):
		with self.assertRaisesRegex(TerminalFehler, "unbekannt"):
			terminal.pruefe_zeile("Backstube", "KT-GT-MUERBE", "GIBTSNICHT-" + self.h, 1)
		with self.assertRaisesRegex(TerminalFehler, "nicht zum Rezept"):
			terminal.pruefe_zeile("Backstube", "KT-GT-MUERBE", self.nuss, 1)
		if frappe.db.get_value("Batch", self.butter["charge"], "kt_status") == "Gesperrt":
			with self.assertRaisesRegex(TerminalFehler, "gesperrt"):
				terminal.pruefe_zeile("Backstube", "KT-GT-MUERBE", self.butter["charge"], 1)
		with self.assertRaises(TerminalFehler):
			terminal.pruefe_zeile("Backstube", "KT-GT-MUERBE", self.silo["KT-MEHL"], 99999)
		z = terminal.pruefe_zeile("Backstube", "KT-GT-MUERBE", self.silo["KT-MEHL"], 60)
		self.assertEqual(z["typ"], "silo")

	def test_04_falsche_station(self):
		self._butter_frei()
		with self.assertRaisesRegex(TerminalFehler, "nicht an der Station"):
			terminal.herstellen("Verpackung", "KT-GT-MUERBE", [{"code": self.silo["KT-MEHL"], "menge": 60}])

	# ------------------------------------------------------------------ Herstellen
	def test_05_grundteig_aus_silo_in_behaelter(self):
		self._butter_frei()
		e = self._grundteig(self.tb)
		self.assertEqual(e["menge"], 100)
		self.assertEqual(frappe.db.get_value("Stock Entry", e["buchung"], "kt_station"), "Backstube")
		t = frappe.db.get_value("Produkttraeger", self.tb, ["status", "charge"], as_dict=True)
		self.assertEqual((t.status, t.charge), ("Belegt", e["charge"]))
		eingaenge = set(
			frappe.get_all("Chargen Genealogie", filters={"output_batch": e["charge"]}, pluck="input_batch")
		)
		self.assertIn(f"L{self.h}-KT-MEHL", eingaenge)
		self.assertIn(f"L{self.h}-KT-ZUCKER", eingaenge)
		self.assertIn(self.butter["charge"], eingaenge)
		with self.assertRaises(frappe.ValidationError):
			self._grundteig(self.tb)  # Behälter ist belegt

	def test_06_veredeln_aus_behaelter_und_rework_allergene(self):
		self._butter_frei()
		gt = self._grundteig(self.tb2)
		tv = terminal.herstellen(
			"Backstube",
			"KT-TV-NUSS",
			[{"code": self.tb2, "menge": 50}, {"code": self.nuss, "menge": 10}],
		)
		self.assertAlmostEqual(frappe.db.get_value("Produkttraeger", self.tb2, "menge"), 50)
		# Nussteig darf nicht in den Mürbe-Rework (Haselnuss fehlt dort)
		with self.assertRaisesRegex(TerminalFehler, "Allergene"):
			terminal.rework_erfassen("Backstube", tv["charge"], 2, "KT-RW-MUERBE")
		rw = terminal.rework_erfassen("Backstube", self.tb2, 5, "KT-RW-MUERBE", self.rb)
		self.assertEqual(frappe.db.get_value("Produkttraeger", self.rb, "charge"), rw["charge"])
		self.assertEqual(
			frappe.get_all("Chargen Genealogie", filters={"output_batch": rw["charge"]}, pluck="input_batch"),
			[gt["charge"]],
		)
		# Rework zurück in einen neuen Grundteig, über den Rework-Behälter gescannt
		gt2 = terminal.herstellen(
			"Backstube",
			"KT-GT-MUERBE",
			[
				{"code": self.silo["KT-MEHL"], "menge": 55},
				{"code": self.silo["KT-ZUCKER"], "menge": 20},
				{"code": self.butter["charge"], "menge": 20},
				{"code": self.rb, "menge": 5},
			],
		)
		self.assertIn(
			rw["charge"],
			frappe.get_all(
				"Chargen Genealogie", filters={"output_batch": gt2["charge"]}, pluck="input_batch"
			),
		)

	# ------------------------------------------------------------------ Versand
	def test_07_lieferung(self):
		fw = demo.neue_charge("KT-FW-KAKAO-NOUGAT", f"FW{self.h}", nowdate())
		demo.buchen(
			self.ctx, "Material Receipt", nowdate(), "06:00:00", ausgaenge=[("KT-FW-KAKAO-NOUGAT", fw, 30)]
		)
		with self.assertRaisesRegex(TerminalFehler, "keine Fertigware"):
			terminal.pruefe_lieferzeile("Versand", self.nuss, 1)
		e = terminal.lieferung("Versand", self.ctx.kunde, [{"code": fw, "menge": 12}])
		self.assertEqual(frappe.db.get_value("Delivery Note", e["lieferschein"], "kt_station"), "Versand")
		self.assertAlmostEqual(sum(terminal.charge_lager(fw).values()), 18)

	# ------------------------------------------------------------------ Silo leer
	def test_08_silo_leer(self):
		e = terminal.silo_leer("Lager", self.silo["KT-ZUCKER"])
		self.assertTrue(e["ausbuchung"])
		self.assertEqual(frappe.db.get_value("Stock Entry", e["ausbuchung"], "kt_station"), "Lager")
		self.assertEqual(terminal.info(self.silo["KT-ZUCKER"])["bestand"], [])

	def test_09_info(self):
		i = terminal.info(self.butter["charge"])
		self.assertEqual(i["typ"], "charge")
		self.assertEqual(i["artikel"], "KT-BUTTER")

	# ------------------------------------------------------------------ Paletten
	def _verpacken(self, kartons=20, palette=None):
		wl = demo.neue_charge("KT-WL-KAKAO-NOUGAT", f"WLP{_hash()}", nowdate())
		demo.buchen(
			self.ctx, "Material Receipt", nowdate(), "05:00:00", ausgaenge=[("KT-WL-KAKAO-NOUGAT", wl, 60)]
		)
		sperre.freigeben(wl, "Test")
		fol = demo.neue_charge("KT-FOLIE", f"FOLP{_hash()}")
		demo.buchen(self.ctx, "Material Receipt", nowdate(), "05:00:00", ausgaenge=[("KT-FOLIE", fol, 5)])
		return terminal.herstellen(
			"Verpackung",
			"KT-FW-KAKAO-NOUGAT",
			[{"code": wl, "menge": 48}, {"code": fol, "menge": 1}],
			anzahl=kartons,
			einheit="Karton",
			ziel_behaelter=palette,
		)

	def test_10_nve(self):
		nve, _test = palette.nve_neu()
		self.assertEqual(len(nve), 18)
		self.assertTrue(nve.isdigit())
		self.assertEqual(int(nve[-1]), palette.pruefziffer(nve[:-1]))
		self.assertEqual(palette.pruefziffer("37610425002123456"), 9)  # Beispiel aus der GS1-Spezifikation
		self.assertEqual(palette.nve_aus_scan("]C100" + nve), nve)
		self.assertEqual(palette.nve_aus_scan("(00)" + nve), nve)

	def test_11_verpacken_auf_palette_umpacken_liefern(self):
		lp = terminal.palette_neu("Verpackung")["nve"]
		e = self._verpacken(20, lp)
		self.assertEqual(e["palette"], lp)
		self.assertAlmostEqual(e["menge"], 48)
		self.assertTrue(e["charge"].startswith("L"))
		i = terminal.palette_info(lp)
		self.assertEqual(
			[(p["charge"], p["anzahl"], p["einheit"]) for p in i["positionen"]], [(e["charge"], 20, "Karton")]
		)
		bewegung = frappe.db.get_value(
			"Paletten Bewegung", {"palette": lp}, ["art", "beleg", "station"], as_dict=True
		)
		self.assertEqual(
			(bewegung.art, bewegung.beleg, bewegung.station), ("Verpackung", e["buchung"], "Verpackung")
		)

		# Alles steht auf der Palette: ohne Palette kann nichts geliefert werden
		with self.assertRaises(TerminalFehler):
			terminal.lieferung(
				"Versand", self.ctx.kunde, [{"code": e["charge"], "anzahl": 1, "einheit": "Karton"}]
			)
		# Fertigung kann nicht storniert werden, solange das Los auf der Palette steht
		with self.assertRaisesRegex(frappe.ValidationError, "steht auf Palette"):
			frappe.get_doc("Stock Entry", e["buchung"]).cancel()

		# Kommissionieren: 5 Kartons auf eine Versandpalette
		vp = terminal.palette_neu("Versand", "Versandpalette")["nve"]
		terminal.palette_umpacken("Versand", lp, vp, e["charge"], 5, "Karton")
		self.assertEqual(terminal.palette_info(lp)["positionen"][0]["anzahl"], 15)
		with self.assertRaises(palette.PalettenFehler):
			terminal.palette_umpacken("Versand", lp, vp, e["charge"], 99, "Karton")

		# Liefern: ganze Versandpalette und 3 Kartons von der Lagerpalette (Anbruch), per GS1-Scan
		ls = terminal.lieferung(
			"Versand",
			self.ctx.kunde,
			[
				{"palette": "]C100" + vp, "ganz": 1},
				{"palette": lp, "charge": e["charge"], "anzahl": 3, "einheit": "Karton"},
			],
		)
		dn = frappe.get_doc("Delivery Note", ls["lieferschein"])
		self.assertEqual(
			sorted((r.kt_palette, r.qty, r.uom) for r in dn.items),
			sorted([(vp, 5, "Karton"), (lp, 3, "Karton")]),
		)
		self.assertAlmostEqual(sum(r.stock_qty for r in dn.items), 8 * 2.4)
		self.assertEqual(
			frappe.db.get_value("Palette", vp, ["status", "lieferschein"]), ("Versendet", dn.name)
		)
		self.assertEqual(terminal.palette_info(lp)["positionen"][0]["anzahl"], 12)
		with self.assertRaises(TerminalFehler):
			terminal.lieferung("Versand", self.ctx.kunde, [{"palette": vp, "ganz": 1}])

		# Rückverfolgung zeigt die Paletten des Loses
		pal = {p.palette for p in palette.paletten_fuer([e["charge"]])}
		self.assertEqual(pal, {lp, vp})

		# Storno des Lieferscheins: Kartons sind wieder auf den Paletten
		dn.cancel()
		self.assertEqual(frappe.db.get_value("Palette", vp, "status"), "Geschlossen")
		self.assertEqual(terminal.palette_info(vp)["positionen"][0]["anzahl"], 5)
		self.assertEqual(terminal.palette_info(lp)["positionen"][0]["anzahl"], 15)

	def test_12_lose_kartons_und_palette_geschlossen(self):
		e = self._verpacken(20)  # ohne Palette: 20 lose Kartons
		lp = terminal.palette_neu("Verpackung")["nve"]
		terminal.palette_beladen("Verpackung", lp, e["charge"], 12, "Karton")
		with self.assertRaisesRegex(palette.PalettenFehler, "lose"):
			terminal.palette_beladen("Verpackung", lp, e["charge"], 9, "Karton")
		terminal.palette_schliessen("Verpackung", lp)
		with self.assertRaisesRegex(palette.PalettenFehler, "geschlossen"):
			terminal.palette_beladen("Verpackung", lp, e["charge"], 1, "Karton")
		# 8 Kartons sind noch lose und dürfen ohne Palette raus, 9 nicht
		with self.assertRaises(TerminalFehler):
			terminal.lieferung(
				"Versand", self.ctx.kunde, [{"code": e["charge"], "anzahl": 9, "einheit": "Karton"}]
			)
		ls = terminal.lieferung(
			"Versand", self.ctx.kunde, [{"code": e["charge"], "anzahl": 16, "einheit": "Beutel"}]
		)
		self.assertTrue(ls["lieferschein"])
		# Bewegungen sind unveränderbar
		b = frappe.get_last_doc("Paletten Bewegung", filters={"palette": lp})
		b.anzahl = 1
		with self.assertRaises(frappe.ValidationError):
			b.save()
