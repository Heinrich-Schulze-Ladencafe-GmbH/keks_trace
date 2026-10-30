"""Tests für die Terminal-Schnittstelle (Backstube, Verpackung, Lager, Versand).

Ausführen:
	bench --site <site> run-tests --module keks_trace.tests.test_terminal
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, flt, getdate, nowdate

from keks_trace import demo, los, palette, sperre, terminal
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
	def test_99_silo_leer(self):
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
		frappe.db.set_single_value("Keks Trace Einstellungen", "los_format", "LJJMMTT-NN")
		lp = terminal.palette_neu("Verpackung")["nve"]
		e = self._verpacken(20, lp)
		self.assertEqual(e["palette"], lp)
		self.assertAlmostEqual(e["menge"], 48)
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
		# Eigenes Los je Vorgang, damit sich die Tests nicht ein Tages-Los teilen
		frappe.db.set_single_value("Keks Trace Einstellungen", "los_format", "LJJMMTT-NN")
		e = self._verpacken(20)  # ohne Palette: 20 lose Kartons
		self.assertTrue(e["charge"].startswith("L"))
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

	# ------------------------------------------------------------------ Los, MHD, Gebinde, Aufträge
	def test_13_jwwt(self):
		self.assertEqual(los.jwwt("2026-10-30"), "6445")  # Freitag KW 44
		self.assertEqual(los.jwwt("2027-01-01"), "6535")  # ISO: gehört noch zur KW 53 von 2026
		self.assertEqual(los.jwwt("2029-12-31"), "0011")  # Montag KW 1 von 2030

	def test_14_tages_los_und_mhd_in_monaten(self):
		frappe.db.set_single_value("Keks Trace Einstellungen", "los_format", "JWWT")
		frappe.db.set_value(
			"Item", "KT-FW-KAKAO-NOUGAT", {"kt_mhd_monate": 32, "kt_mhd_bezug": "Verpackungstag"}
		)
		frappe.clear_cache(doctype="Item")
		try:
			e1 = self._verpacken(10)
			e2 = self._verpacken(5)
			self.assertEqual(e1["charge"], e2["charge"])
			self.assertEqual(e1["los"], los.jwwt(nowdate()))
			b = frappe.db.get_value(
				"Batch", e1["charge"], ["expiry_date", "manufacturing_date"], as_dict=True
			)
			self.assertEqual(getdate(b.expiry_date), getdate(add_months(nowdate(), 32)))
			self.assertAlmostEqual(palette.lagerbestand(e1["charge"]), 15 * 2.4)
			v = terminal.vorschau("Verpackung", "KT-FW-KAKAO-NOUGAT", [])
			self.assertEqual((v["los"], v["los_vorhanden"]), (e1["los"], True))
			# Gesperrtes Tages-Los: nicht weiter verpacken
			sperre.sperren(e1["charge"], "Test")
			with self.assertRaisesRegex(frappe.ValidationError, "gesperrt"):
				self._verpacken(1)
		finally:
			frappe.db.set_value("Item", "KT-FW-KAKAO-NOUGAT", {"kt_mhd_monate": 0, "kt_mhd_bezug": None})
			frappe.clear_cache(doctype="Item")

	def test_15_gebinde(self):
		e = terminal.wareneingang(
			"Lager",
			"KT-HASELNUSS",
			f"HNG{self.h}",
			25,
			add_days(nowdate(), 100),
			gebinde=3,
			gebindeart="Sack",
		)
		self.assertEqual(len(e["gebinde"]), 3)
		self.assertAlmostEqual(e["menge"], 75)
		g = e["gebinde"][0]
		t = frappe.db.get_value("Produkttraeger", g, ["typ", "gebindeart", "charge", "menge"], as_dict=True)
		self.assertEqual((t.typ, t.gebindeart, t.charge, t.menge), ("Gebinde", "Sack", e["charge"], 25))
		# Teilentnahme aus dem Sack in der Backstube
		self._butter_frei()
		gt = self._grundteig(None)
		tv = terminal.herstellen(
			"Backstube", "KT-TV-NUSS", [{"code": gt["charge"], "menge": 50}, {"code": g, "menge": 10}]
		)
		self.assertAlmostEqual(frappe.db.get_value("Produkttraeger", g, "menge"), 15)
		self.assertIn(
			e["charge"],
			frappe.get_all("Chargen Genealogie", {"output_batch": tv["charge"]}, pluck="input_batch"),
		)
		with self.assertRaises(TerminalFehler):
			terminal.pruefe_zeile("Backstube", "KT-TV-NUSS", g, 16)
		# Ein Gebinde ist nie Zielbehälter
		with self.assertRaisesRegex(TerminalFehler, "Gebinde"):
			terminal._ziel_behaelter(e["gebinde"][2])

	def test_16_kundenauftrag(self):
		frappe.db.set_single_value("Keks Trace Einstellungen", "los_format", "LJJMMTT-NN")
		so = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"customer": self.ctx.kunde,
				"company": self.ctx.company,
				"transaction_date": nowdate(),
				"delivery_date": add_days(nowdate(), 3),
				"items": [{"item_code": "KT-FW-KAKAO-NOUGAT", "qty": 30, "uom": "Karton", "conversion_factor": 2.4,
				           "rate": 10, "warehouse": self.ctx.fertig}],
			}
		).insert()  # fmt: skip
		so.submit()
		a = [z for z in terminal.auftraege("Verpackung") if z.auftrag == so.name]
		self.assertEqual((a[0].offen_verpacken, a[0].einheit), (30, "Karton"))
		p = terminal.palette_neu("Verpackung")["nve"]
		wl = demo.neue_charge("KT-WL-KAKAO-NOUGAT", f"WLA{_hash()}", nowdate())
		demo.buchen(
			self.ctx, "Material Receipt", nowdate(), "05:00:00", ausgaenge=[("KT-WL-KAKAO-NOUGAT", wl, 60)]
		)
		sperre.freigeben(wl, "Test")
		fol = demo.neue_charge("KT-FOLIE", f"FOLA{_hash()}")
		demo.buchen(self.ctx, "Material Receipt", nowdate(), "05:00:00", ausgaenge=[("KT-FOLIE", fol, 5)])
		e = terminal.herstellen(
			"Verpackung", "KT-FW-KAKAO-NOUGAT", [{"code": wl, "menge": 48}, {"code": fol, "menge": 1}],
			anzahl=20, einheit="Karton", ziel_behaelter=p, kundenauftrag=so.name,
		)  # fmt: skip
		self.assertEqual(frappe.db.get_value("Stock Entry", e["buchung"], "kt_kundenauftrag"), so.name)
		self.assertEqual(frappe.db.get_value("Palette", p, "kundenauftrag"), so.name)
		a = next(z for z in terminal.auftraege("Verpackung") if z.auftrag == so.name)
		self.assertEqual((a.verpackt, a.offen_verpacken), (20, 10))
		ls = terminal.lieferung("Versand", self.ctx.kunde, [{"palette": p, "ganz": 1}], kundenauftrag=so.name)
		so.reload()
		self.assertAlmostEqual(so.items[0].delivered_qty, 20)
		self.assertEqual(
			frappe.db.get_value("Delivery Note Item", {"parent": ls["lieferschein"]}, "against_sales_order"),
			so.name,
		)
		with self.assertRaisesRegex(TerminalFehler, "nicht bestellt"):
			terminal.herstellen(
				"Verpackung", "KT-FW-NUSS-SCHOKO", [{"code": fol, "menge": 1}], kundenauftrag=so.name
			)

	def test_17_auftrag_in_paletten(self):
		frappe.db.set_single_value("Keks Trace Einstellungen", "los_format", "LJJMMTT-NN")
		item = frappe.get_doc("Item", "KT-FW-KAKAO-NOUGAT")
		if not any(u.uom == "Palette" for u in item.uoms):
			item.append("uoms", {"uom": "Palette", "conversion_factor": 24})  # 10 Karton à 2,4 kg
			item.save()
		self.assertEqual(palette.zerlegen("KT-FW-KAKAO-NOUGAT", 3 * 24 + 5 * 2.4), "3 Paletten + 5 Karton")
		self.assertEqual(
			palette.zerlegen("KT-FW-KAKAO-NOUGAT", 24 + 2.4 + 0.4), "1 Palette + 1 Karton + 2 Beutel"
		)
		# Palette ist nur Rechen-/Anzeigeeinheit, gezählt wird in Karton/Beutel
		self.assertNotIn("Palette", [e["einheit"] for e in palette.einheiten("KT-FW-KAKAO-NOUGAT")])

		so = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"customer": self.ctx.kunde,
				"company": self.ctx.company,
				"transaction_date": nowdate(),
				"delivery_date": add_days(nowdate(), 3),
				"items": [{"item_code": "KT-FW-KAKAO-NOUGAT", "qty": 2, "uom": "Palette", "conversion_factor": 24,
				           "rate": 100, "warehouse": self.ctx.fertig}],
			}
		).insert()  # fmt: skip
		so.submit()
		a = next(z for z in terminal.auftraege("Verpackung") if z.auftrag == so.name)
		self.assertEqual(a.menge_text, "2 Paletten")
		p = terminal.palette_neu("Verpackung")["nve"]
		e = self._verpacken(10, p)
		frappe.db.set_value("Stock Entry", e["buchung"], "kt_kundenauftrag", so.name)
		f = terminal.palette_info(p)["fuellung"]
		self.assertTrue(f["voll"])
		self.assertEqual(f["text"], "10 von 10 Karton")
		a = next(z for z in terminal.auftraege("Verpackung") if z.auftrag == so.name)
		self.assertEqual((a.verpackt_text, a.offen_text), ("1 Palette", "1 Palette"))

		ls = terminal.lieferung("Versand", self.ctx.kunde, [{"palette": p, "ganz": 1}], kundenauftrag=so.name)
		r = frappe.get_doc("Delivery Note", ls["lieferschein"]).items[0]
		self.assertEqual((r.uom, flt(r.qty, 3), r.kt_anzahl, r.kt_einheit), ("Palette", 1.0, 10, "Karton"))
		self.assertEqual(frappe.db.get_value("Palette", p, "status"), "Versendet")
		so.reload()
		self.assertAlmostEqual(so.items[0].delivered_qty, 1)
