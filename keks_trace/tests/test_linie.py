"""Backstraße: Leistung mit Engpass, Planung, Kübel einkippen, Palette fertig, Auftrag beenden."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, flt, getdate, nowdate

from keks_trace import demo, demo_linie, linienbuchung, planung, pruefung, terminal
from keks_trace.linienbuchung import LinienFehler


def _hash():
	return frappe.generate_hash(length=5).upper()


class TestLinie(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = demo_linie.stammdaten()
		cls.h = _hash()
		cls.alt = demo.neuer_traeger(f"TKA-{cls.h}", "Teigbehälter")
		cls.k1 = demo.neuer_traeger(f"TK1-{cls.h}", "Teigbehälter")
		cls.k2 = demo.neuer_traeger(f"TK2-{cls.h}", "Teigbehälter")
		for code, tage in ((cls.alt, -2), (cls.k1, -1), (cls.k2, 0)):
			tag = add_days(nowdate(), tage)
			c = demo.neue_charge("5888", f"T5888-{code}", tag)
			demo.buchen(cls.ctx, "Material Receipt", tag, "04:00:00", ausgaenge=[("5888", c, 200, code)])
		cls.pa = frappe.get_doc(
			{
				"doctype": "Produktionsauftrag",
				"linie": demo_linie.LINIE,
				"datum": nowdate(),
				"artikel": "17846",
				"menge": 50,
				"einheit": "Karton",
				"status": "Freigegeben",
			}
		).insert()

	def test_01_leistung_engpass(self):
		kg, engpass, anlage = planung.leistung("17846")
		self.assertEqual((kg, engpass, anlage), (125, "Trocknen", "InoTec"))
		# Thürlings 30 Beutel/min = 360 kg/h, Engpass bleibt Trocknen
		self.assertEqual(planung.leistung("17846", "Thürlings")[:2], (125, "Trocknen"))
		# Manuelles Band 30 Karton/h = 120 kg/h wird zum Engpass
		self.assertEqual(planung.leistung("17846", "Manuelles Band")[:2], (120, "Manuelles Band"))
		with self.assertRaisesRegex(frappe.ValidationError, "Carina"):
			planung.leistung("17846", "Carina")
		self.assertEqual(flt(self.pa.dauer_stunden, 2), 1.6)  # 50 Karton = 200 kg / 125 kg/h
		self.assertIn("Trocknen", self.pa.engpass)

	def test_02_linienrezept(self):
		r = linienbuchung.linienrezept("17846")
		self.assertAlmostEqual(r["5888"], 208.58 / 188.687, places=4)  # Teig durch lose Ware aufgelöst
		self.assertAlmostEqual(r["9101"], 5)  # 20 Beutel je 4 kg
		self.assertNotIn("5888-LOSE", r)

	def test_03_former_palette_beenden(self):
		info = linienbuchung.waehlen("Former", self.pa.name)
		self.assertEqual(info["status"], "Läuft")
		self.assertTrue(info["kuebel"])  # Vorschlag: belegte Kübel mit Honig Moppen Teig, ältester zuerst
		# falsche Ware am Former
		zucker = terminal.wareneingang("Lager", "KT-ZUCKER", f"Z{self.h}", 10, add_days(nowdate(), 100))[
			"charge"
		]
		with self.assertRaisesRegex(LinienFehler, "gehört nicht"):
			terminal.linie_zufuehren("Former", zucker)
		# jüngerer Kübel: gebucht, aber Hinweis auf den älteren
		r = terminal.linie_zufuehren("Former", self.k1)
		self.assertEqual(r["menge"], 200)
		self.assertTrue(any("Älter wäre" in h for h in r["hinweise"]))
		self.assertEqual(frappe.db.get_value("Produkttraeger", self.k1, "status"), "Frei")
		self.assertEqual(sum(z["menge"] for z in linienbuchung.bestand(self.pa.name)), 200)

		# Paletten-Terminal: 10 Karton = 40 kg Fertigware
		linienbuchung.waehlen("Paletten-Terminal", self.pa.name)
		nve = terminal.palette_neu("Paletten-Terminal")["nve"]
		# Metallcheck der Anlage (InoTec) ist fällig: erst prüfen, dann buchen
		demo.pruefungen_altern("Metallcheck InoTec", "Metallcheck Thürlings")
		faellig = [f["titel"] for f in pruefung.faellig("Paletten-Terminal") if f["faellig"]]
		self.assertIn("Metallcheck InoTec", faellig)
		self.assertNotIn("Metallcheck Thürlings", faellig)
		with self.assertRaisesRegex(pruefung.PruefFehler, "Metallcheck InoTec"):
			terminal.linie_palette("Paletten-Terminal", 10, "Karton", nve)
		demo_linie.metallcheck_ok("Paletten-Terminal")
		e = terminal.linie_palette("Paletten-Terminal", 10, "Karton", nve)
		self.assertEqual(e["menge"], 40)
		verbraucht = {v["charge"]: v["menge"] for v in e["verbraucht"]}
		self.assertAlmostEqual(verbraucht[f"T5888-{self.k1}"], 40 * 208.58 / 188.687, places=2)
		b = frappe.db.get_value("Batch", e["charge"], ["kt_backtag", "expiry_date"], as_dict=True)
		self.assertEqual(getdate(b.kt_backtag), getdate(nowdate()))  # Linie: heute gebacken
		self.assertEqual(getdate(b.expiry_date), getdate(add_months(nowdate(), 32)))
		self.assertTrue(
			frappe.db.exists(
				"Chargen Genealogie",
				{"input_batch": f"T5888-{self.k1}", "output_batch": e["charge"], "storniert": 0},
			)
		)
		self.assertEqual(flt(frappe.db.get_value("Produktionsauftrag", self.pa.name, "gebucht_kg")), 40)
		self.assertIn(
			e["charge"],
			[p["charge"] for p in frappe.get_all("Paletten Bewegung", {"palette": nve}, ["charge"])],
		)
		# Packmittel nicht an der Linie gebucht: kein Fehler, nur Teig verbraucht
		self.assertFalse(any("Schlauchbeutel" in h for h in e["hinweise"]))

		# Metallcheck an der Packstation nicht bestanden: Lose dieser Anlage seit dem letzten OK gesperrt
		frappe.db.set_value("Terminal Station", "Packstation", "aktueller_auftrag", self.pa.name)
		koerper = frappe.get_doc("Pruefplan", "Metallcheck InoTec").koerper()
		r = pruefung.erfassen(
			"Packstation",
			"Metallcheck InoTec",
			{"koerper": {k: k != koerper[0] for k in koerper}},
			"Fe nicht erkannt",
		)
		self.assertIn(e["charge"], r["gesperrt"])
		from keks_trace import sperre

		sperre.freigeben(e["charge"], "Test: nachgeprüft")
		demo_linie.metallcheck_ok("Packstation")

		# Packstation zeigt Los und MHD
		frappe.db.set_value("Terminal Station", "Packstation", "aktueller_auftrag", self.pa.name)
		p = terminal.packstation("Packstation")
		self.assertEqual(p["beutel_je_karton"], 20)
		self.assertEqual(p["verpackungsanlage"], "InoTec")

		# Auftrag beenden: Rest der Linie wird ausgebucht
		rest = 200 - verbraucht[f"T5888-{self.k1}"]
		b = terminal.linie_beenden("Paletten-Terminal", self.pa.name)
		self.assertAlmostEqual(b["rest"][0]["menge"], rest, places=2)
		self.assertEqual(frappe.db.get_value("Produktionsauftrag", self.pa.name, "status"), "Fertig")
		self.assertFalse(linienbuchung.bestand(self.pa.name))
		self.assertIsNone(frappe.db.get_value("Terminal Station", "Former", "aktueller_auftrag"))
		with self.assertRaisesRegex(LinienFehler, "Produktionsauftrag wählen"):
			terminal.linie_zufuehren("Former", self.k2)

	def test_04_palette_ohne_teig(self):
		pa = frappe.get_doc(
			{"doctype": "Produktionsauftrag", "linie": demo_linie.LINIE, "datum": nowdate(), "artikel": "17846",
			 "menge": 5, "einheit": "Karton", "status": "Freigegeben"}
		).insert()  # fmt: skip
		linienbuchung.waehlen("Paletten-Terminal", pa.name)
		with self.assertRaisesRegex(LinienFehler, "noch nichts auf der Linie"):
			terminal.linie_palette("Paletten-Terminal", 5, "Karton")
		linienbuchung.beenden("Paletten-Terminal", pa.name, abbrechen=True)

	def test_05_planung(self):
		kunde = demo_linie.GROSSKUNDEN[0][0]
		so = frappe.get_doc(
			{"doctype": "Sales Order", "customer": kunde, "company": self.ctx.company, "po_no": f"T-{self.h}",
			 "transaction_date": nowdate(), "delivery_date": add_days(nowdate(), 30),
			 "items": [{"item_code": "17846", "qty": 15000, "uom": "Beutel", "conversion_factor": 0.2, "rate": 0.6,
						"warehouse": self.ctx.fertig, "delivery_date": add_days(nowdate(), 30)}]}
		).insert()  # fmt: skip
		so.submit()
		linie = f"Testlinie-{self.h}"
		frappe.get_doc(
			{"doctype": "Linie", "linie_name": linie, "company": self.ctx.company, "laufzeit_stunden": 8,
			 "umruestzeit_minuten": 30, "lagerort": self.ctx.linienlager, "fertiglager": self.ctx.fertig}
		).insert()  # fmt: skip
		# 17846 vorübergehend dieser Testlinie zuordnen: geplant wird je Linie nur ihre Artikel
		frappe.db.set_value("Item", "17846", "kt_linie", linie)
		frappe.clear_document_cache("Item", "17846")

		def zurueck():
			frappe.db.set_value("Item", "17846", "kt_linie", demo_linie.LINIE)
			frappe.clear_document_cache("Item", "17846")

		self.addCleanup(zurueck)
		start = add_days(nowdate(), 400)
		planung.vorschlag(linie, ab=start)
		pas = frappe.get_all(
			"Produktionsauftrag",
			{"kt_so_detail": so.items[0].name},
			["datum", "menge_kg", "dauer_stunden", "status"],
			order_by="datum",
		)
		# 15.000 Beutel = 3.000 kg, höchstens 1.000 kg am Tag (125 kg/h x 8 h)
		self.assertAlmostEqual(sum(p.menge_kg for p in pas), 3000)
		self.assertGreaterEqual(len(pas), 3)
		self.assertTrue(all(p.status == "Geplant" for p in pas))
		self.assertTrue(all(frappe.get_doc("Linie", linie).ist_arbeitstag(p.datum) for p in pas))
		self.assertTrue(all(p.dauer_stunden <= 8 for p in pas))
		r = planung.tag_freigeben(linie, pas[0].datum)
		self.assertGreaterEqual(r["freigegeben"], 1)
		# geplant ist geplant: zweiter Vorschlag legt für diesen Auftrag nichts nach
		planung.vorschlag(linie, ab=start)
		self.assertEqual(frappe.db.count("Produktionsauftrag", {"kt_so_detail": so.items[0].name}), len(pas))
		bedarf = {b["artikel"]: b for b in planung.teigbedarf(linie, 500)}
		self.assertIn("5888", bedarf)

	def test_06_kneter_teig_direkt_auf_die_linie(self):
		"""Ein oder zwei Grundteig-Kübel + Zutaten in den Kneter; der Teig geht direkt in den Former."""
		from keks_trace.trace import rueckwaerts

		kuebel = []
		for i in (1, 2):
			code = demo.neuer_traeger(f"TGK{i}-{self.h}", "Teigbehälter")
			c = demo.neue_charge("5812", f"T5812-{i}-{self.h}", add_days(nowdate(), -40 * i))
			demo.buchen(self.ctx, "Material Receipt", add_days(nowdate(), -40 * i), "04:00:00",
						ausgaenge=[("5812", c, 200, code)])  # fmt: skip
			kuebel.append((code, c))
		abc = terminal.wareneingang("Lager", "4150", f"ABC{self.h}", 20, add_days(nowdate(), 300))["charge"]
		pa = frappe.get_doc(
			{"doctype": "Produktionsauftrag", "linie": demo_linie.LINIE, "datum": nowdate(), "artikel": "17846",
			 "menge": 20, "einheit": "Karton", "status": "Freigegeben"}
		).insert()  # fmt: skip
		frappe.db.set_value("Terminal Station", "Kneter", "aktueller_auftrag", None)
		with self.assertRaisesRegex(LinienFehler, "Produktionsauftrag wählen"):
			terminal.herstellen("Kneter", "5888", [{"code": kuebel[0][0], "menge": 200}])
		linienbuchung.waehlen("Kneter", pa.name)
		r = terminal.rezept("5888", station="Kneter")
		self.assertTrue(r["kuebel"])  # Vorschlag Grundteig-Kübel, ältester zuerst
		e = terminal.herstellen(
			"Kneter", "5888",
			[{"code": kuebel[0][0], "menge": 200}, {"code": kuebel[1][0], "menge": 200}, {"code": abc, "menge": 2}],
		)  # fmt: skip
		self.assertIsNone(e["behaelter"])
		auf_linie = {z["charge"]: z["menge"] for z in linienbuchung.bestand(pa.name)}
		self.assertIn(e["charge"], auf_linie)  # Teig liegt beim Auftrag auf der Linie
		for code, _c in kuebel:
			self.assertEqual(frappe.db.get_value("Produkttraeger", code, "status"), "Frei")
		linienbuchung.waehlen("Paletten-Terminal", pa.name)
		demo_linie.metallcheck_ok("Paletten-Terminal")
		p = terminal.linie_palette("Paletten-Terminal", 10, "Karton")
		kette = {z["charge"] for z in rueckwaerts(p["charge"])}
		self.assertIn(e["charge"], kette)
		for _code, c in kuebel:
			self.assertIn(c, kette)
		linienbuchung.beenden("Paletten-Terminal", pa.name)

	def test_07_reichweite_und_kontrakt(self):
		"""Einkauf: Kontrakt (Rahmenauftrag) mit Abrufen; Reichweite zeigt Bestand, bestellt, Kontrakt offen."""
		from keks_trace import demo_einkauf
		from keks_trace.keks_trace.report.reichweite_rohstoffe.reichweite_rohstoffe import execute

		k = demo_einkauf.anlegen()
		self.assertEqual(k["menge"], 50000)
		self.assertGreaterEqual(k["abgerufen"], 24000)
		zeilen = {z["artikel"]: z for z in execute({"stufe": "Rohstoff", "artikel": "KT-ZUCKER"})[1]}
		z = zeilen["KT-ZUCKER"]
		self.assertGreaterEqual(z["bestellt"], 24000)
		self.assertAlmostEqual(z["kontrakt"], 50000 - k["abgerufen"])
		# Bedarf aus offenen Kundenaufträgen geht bis auf Rohstoffe herunter
		alle = execute({"stufe": "Rohstoff und Packmittel"})[1]
		self.assertTrue(any(r["bedarf_auftraege"] > 0 for r in alle))
