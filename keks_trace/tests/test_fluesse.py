"""Flussschema F1 bis F20: die neuen Flüsse einzeln durchgespielt (lose Ware im Karton, Linienlager, Rework).

Siehe Artifact „Keks Flussschema“. Andere Flüsse prüfen test_terminal, test_linie und test_herzen.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from keks_trace import anfrage, demo, linienbuchung, terminal
from keks_trace import palette as paletten
from keks_trace.demo import linie as demo_linie
from keks_trace.linienbuchung import LinienFehler

VPC = "Verpackungs-PC"


def _hash():
	return frappe.generate_hash(length=5).upper() + "7"  # mit Ziffer: Chargen-Plausibilität


class TestFluesse(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = demo_linie.stammdaten()
		demo_linie.packmittel(cls.ctx)
		cls.linie = frappe.get_doc("Linie", demo_linie.LINIE)
		cls.kunde = demo_linie.GROSSKUNDEN[0][0]

	def _auftrag(self, kg_teig=200):
		"""Laufender Auftrag Honig Lebkuchen: Kübel 5888 am Kneter auf die Linie (F4), Verpackungs-PC dran."""
		kuebel = demo.neuer_traeger(f"TF-{_hash()}", "Teigbehälter")
		teig = demo.neue_charge("5888", f"T5888-F-{kuebel}", add_days(nowdate(), -1))
		demo.buchen(
			self.ctx,
			"Material Receipt",
			add_days(nowdate(), -1),
			"04:00:00",
			ausgaenge=[("5888", teig, kg_teig, kuebel)],
		)
		pa = frappe.get_doc(
			{"doctype": "Produktionsauftrag", "linie": demo_linie.LINIE, "datum": nowdate(), "artikel": "17846",
			 "menge": 50, "einheit": "Karton", "status": "Freigegeben"}
		).insert()  # fmt: skip
		linienbuchung.waehlen("Kneter", pa.name)
		linienbuchung.zufuehren("Kneter", kuebel)
		linienbuchung.waehlen(VPC, pa.name)
		return pa, teig

	def _auf_linie(self, pa):
		return sum(z["menge"] for z in linienbuchung.bestand(pa.name))

	def test_f07_lose_ware_im_karton_auf_palette_und_versand(self):
		"""F7: lose Ware im Karton (kg fest je Artikel) auf Palette ins Lager; F17: über den Versand zum Kunden."""
		pa, _teig = self._auftrag()
		self.assertEqual(linienbuchung.info(pa.name)["lose_einheit"], "Karton")
		nve = terminal.palette_neu(VPC)["nve"]
		e = terminal.linie_lose(VPC, 5, None, "lager", nve)
		self.assertEqual((e["einheit"], e["menge"], e["lager"]), ("Karton", 30, self.linie.fertiglager))
		self.assertEqual(paletten.inhalt(nve)[0]["anzahl"], 5)
		ls = terminal.lieferung("Versand", self.kunde, [{"palette": nve, "ganz": 1}])
		zeilen = frappe.get_all(
			"Delivery Note Item", {"parent": ls["lieferschein"]}, ["item_code", "qty", "batch_no"]
		)
		self.assertEqual([(z.item_code, z.batch_no) for z in zeilen], [("5888-LOSE", e["charge"])])

	def test_f08_f09_linienlager_und_zurueck_in_die_verpackung(self):
		"""F8: Kartons ins Linienlager (Wannen werden nicht gebucht); F9: zuerst aus dem Linienlager verpacken."""
		pa, _teig = self._auftrag()
		with self.assertRaisesRegex(LinienFehler, "keine Palette"):
			terminal.linie_lose(VPC, 1, None, "linienlager", terminal.palette_neu(VPC)["nve"])
		e = terminal.linie_lose(VPC, 3, None, "linienlager")
		self.assertEqual((e["lager"], e["menge"]), (self.linie.linienlager, 18))
		self.assertIn(e["charge"], {z["charge"] for z in linienbuchung.info(pa.name)["im_linienlager"]})
		liste = [q for q in terminal.zum_verpacken(VPC) if q["lose"] == "5888-LOSE"]
		self.assertTrue(liste[0]["linienlager"], "Linienlager steht vorne")
		self.assertIn(e["charge"], {q["charge"] for q in liste if q["linienlager"]})
		v = terminal.vorschlag(VPC, "17846", 12, e["charge"])
		self.assertFalse(v["hinweise"])
		self.assertEqual(v["zeilen"][0]["lager"], self.linie.linienlager)
		terminal.herstellen(
			VPC,
			"17846",
			[{"code": z["code"], "menge": z["menge"]} for z in v["zeilen"]],
			12,
			None,
			3,
			"Karton",
		)
		self.assertAlmostEqual(terminal.charge_lager(e["charge"]).get(self.linie.linienlager, 0), 6, places=3)

	def test_f18_f19_rework_von_der_backstube_zurueck_am_kneter(self):
		"""F18: Backstube bucht den gewogenen Behälter von der Linie (Filter Sorte, Teig der Linie wird Rework);
		F19: am Kneter zurück, höchstens bis zum Anteil laut Regel, und es geht in die Ware ein."""
		pa, teig = self._auftrag()
		sorten = {s["artikel"]: s["punkt"] for s in linienbuchung.rework_sorten(pa.name)}
		self.assertEqual(sorten.get("RW-HONIG-OFEN"), "Nach dem Ofen")
		self.assertIn("RW-HONIG", sorten)
		rb = demo.neuer_traeger(f"RBF-{_hash()}", "Rework-Behälter")
		with self.assertRaisesRegex(LinienFehler, "kein Rework-Behälter"):
			terminal.rework_linie(
				"Backstube", pa.name, "RW-HONIG", 6, demo.neuer_traeger(f"TX-{_hash()}", "Teigbehälter")
			)
		vorher = self._auf_linie(pa)
		r = terminal.rework_linie("Backstube", pa.name, "RW-HONIG-OFEN", 6, rb)
		self.assertAlmostEqual(vorher - self._auf_linie(pa), 6, places=3)  # zählt nicht als Linienrest
		quellen = frappe.get_all(
			"Stock Entry Detail", {"parent": r["buchung"], "s_warehouse": ["is", "set"]}, pluck="batch_no"
		)
		self.assertEqual(quellen, [teig])
		self.assertEqual(frappe.db.get_value("Produkttraeger", rb, "charge"), r["charge"])
		# F19: zu viel Rework wird abgewiesen
		rb2 = demo.neuer_traeger(f"RBF-{_hash()}", "Rework-Behälter")
		gross = terminal.rework_linie("Backstube", pa.name, "RW-HONIG-OFEN", 40, rb2)
		linienbuchung.zufuehren("Kneter", rb)
		with self.assertRaisesRegex(LinienFehler, "Zu viel Rework"):
			linienbuchung.zufuehren("Kneter", rb2)
		self.assertTrue(gross["charge"])
		# Alles verpacken: das Rework geht mit dem Teig in die Ware ein (Rückverfolgung)
		rest = self._auf_linie(pa)
		kartons = int(rest / linienbuchung.linienrezept("17846")["5888"] / 4)
		k = linienbuchung.palette_fertig(VPC, kartons, "Karton", terminal.palette_neu(VPC)["nve"])
		self.assertIn(r["charge"], {v["charge"] for v in k["verbraucht"]})
		self.assertLess(self._auf_linie(pa), 4.5)

	def test_doppelbuchung_wird_verhindert(self):
		"""Gleiche Anfrage zweimal (Antwort ging verloren, nochmal getippt): nur eine Buchung."""
		alt = anfrage._schluessel
		schluessel = f"kt_anfrage:test:{_hash()}"
		anfrage._schluessel = lambda methode: schluessel
		try:
			erste = terminal.palette_neu(VPC)["nve"]
			zweite = terminal.palette_neu(VPC)["nve"]
		finally:
			anfrage._schluessel = alt
		self.assertEqual(erste, zweite)
		self.assertNotEqual(terminal.palette_neu(VPC)["nve"], erste)  # ohne Anfrage-ID normal

	def test_f10_lose_ware_von_der_palette_verpacken(self):
		"""F10: lose Ware im Karton steht auf einer Palette und wird nach Bedarf verpackt; was verbraucht wird,
		geht automatisch von der Palette ab. Ziele: alle Artikel mit dieser losen Ware, Aufträge zuerst."""
		_pa, _teig = self._auftrag()
		nve = terminal.palette_neu(VPC)["nve"]
		e = terminal.linie_lose(VPC, 5, None, "lager", nve)
		ziele = terminal.verpacken_ziele(VPC, "5888-LOSE")
		self.assertTrue({"17846", "17847"} <= {z["artikel"] for z in ziele["artikel"]})
		self.assertTrue(all(a["artikel"] in ("17846", "17847") for a in ziele["auftraege"]))
		v = terminal.vorschlag(VPC, "17846", 12, e["charge"])
		self.assertFalse(v["hinweise"])
		terminal.herstellen(
			VPC,
			"17846",
			[{"code": z["code"], "menge": z["menge"]} for z in v["zeilen"]],
			12,
			None,
			3,
			"Karton",
		)
		pos = paletten.inhalt(nve)
		self.assertAlmostEqual(pos[0]["menge"], 18, places=3)  # 30 kg auf der Palette, 12 kg verpackt
		self.assertAlmostEqual(paletten.lose(e["charge"]), 0, places=3)

	def test_behaelter_nur_an_ihrer_linie(self):
		"""Leer melden und Karton anbrechen zeigen nur die Behälter der eigenen Linie (Herzenboden ≠ Backstube)."""
		from keks_trace.demo import herzen as demo_herzen

		demo_herzen.anlegen(vorrat=0)
		herzen = {s["silo"] for s in terminal.silos("Herzen Garnieren")}
		backstube = {s["silo"] for s in terminal.silos("Backstube")}
		self.assertIn("Zuckerguss Herzenboden", herzen)
		self.assertFalse(herzen & backstube)
		self.assertTrue(terminal.start("Herzen Verpackung")["vorraete"])
		self.assertFalse(terminal.start("Backstube")["vorraete"])
		einheit = {s["silo"]: s["einheit"] for s in terminal.silos("Herzen Verpackung")}
		self.assertEqual(einheit["Folie Herzenboden"], "Nos")  # nicht kg

	def test_stueckware_rest_in_stueck(self):
		"""Angebrochene Kartons mit Stückware: „19 Karton + 7 Stk“ statt „19,7 Karton“."""
		from keks_trace.demo import herzen as demo_herzen

		demo_herzen.anlegen(vorrat=0)
		je = demo_herzen.STK_JE_KARTON["9"]
		self.assertEqual(paletten.zerlegen("HZ-ROHLING-9", 3 * je + 7), "3 Karton + 7 Stk")

	def test_fefo_beim_zufuehren_an_der_linie(self):
		"""Lücke geschlossen: auch an der Linie braucht eine jüngere Charge einen Grund, wenn eine ältere da ist.
		Die Linienrezepte der Demo haben nur Packmittel ohne MHD, daher wird „ältere Charge“ hier vorgegeben."""
		from unittest import mock

		from keks_trace.utils import einstellungen

		pa, _teig = self._auftrag()
		folie = next(
			c
			for c in frappe.get_all(
				"Batch", {"item": "9101", "disabled": 0}, pluck="name", order_by="creation desc"
			)
			if terminal.charge_lager(c)
		)
		aelter = [{"charge": "ALT-TEST", "mhd": "01.01.2027", "menge": 5}]
		with (
			einstellungen(fefo_rohstoffe="Grund Pflicht"),
			# _fefo_aeltere dort ersetzen, wo es aufgerufen wird (Terminal-Paket, Modul zutaten)
			mock.patch.object(terminal.zutaten, "_fefo_aeltere", return_value=aelter),
		):
			f = terminal.fefo_pruefen("Kneter", folie)
			self.assertTrue(f["pflicht"] and f["aeltere"])
			with self.assertRaisesRegex(Exception, "Älteres MHD"):
				linienbuchung.zufuehren("Kneter", folie, 1)
			r = linienbuchung.zufuehren("Kneter", folie, 1, fefo_grund="Anweisung QS")
		text = frappe.db.get_value("Stock Entry", r["buchung"], "kt_fefo_abweichung")
		self.assertIn("Grund: Anweisung QS", text)
		self.assertIn("ALT-TEST", text)
		self.assertEqual(r["auftrag"], pa.name)

	def test_paletten_etikett_nach_entnahme_neu_drucken(self):
		"""Fotos 1.11.: „30“ auf dem Etikett von Hand zu „29“ korrigiert. Jetzt: das System merkt sich den gedruckten
		Inhalt, meldet beim Herunternehmen „Etikett neu drucken“, und das Etikett zeigt das Los wie der Karton."""
		pa, _teig = self._auftrag()
		terminal.linie_lose(VPC, 5, None, "linienlager")  # 30 kg lose Ware zum Verpacken
		nve = terminal.palette_neu(VPC)["nve"]
		v = terminal.vorschlag(VPC, "17846", 24)
		self.assertFalse(v["hinweise"])
		e = terminal.herstellen(
			VPC,
			"17846",
			[{"code": z["code"], "menge": z["menge"]} for z in v["zeilen"]],
			24,
			nve,
			6,
			"Karton",
		)
		los = frappe.db.get_value("Batch", e["charge"], "kt_los")
		self.assertTrue(los)
		pos = paletten.inhalt(nve)
		self.assertEqual(pos[0]["los"], los)  # Los wie auf dem Karton, nicht der interne Chargenname
		et = paletten.etikett(nve)
		if et["inhalt_text"]:
			self.assertIn(f"(10) {los}", et["inhalt_text"])
		self.assertIsNone(paletten.info(nve)["etikett_aktuell"])  # noch nie gedruckt
		paletten.etikett_gedruckt(nve)
		self.assertTrue(paletten.info(nve)["etikett_aktuell"])
		# einen Karton herunternehmen (auf eine andere Palette): Hinweis, Etikett passt nicht mehr
		frappe.flags.kt_etikett_hinweis = set()
		ziel = terminal.palette_neu(VPC)["nve"]
		r = terminal.palette_umpacken(VPC, nve, ziel, e["charge"], 1, "Karton")
		self.assertTrue(any("Etikett neu drucken" in h for h in r["hinweise"]))
		self.assertIs(paletten.info(nve)["etikett_aktuell"], False)
		paletten.etikett_gedruckt(nve)  # neu gedruckt
		self.assertTrue(paletten.info(nve)["etikett_aktuell"])
		self.assertEqual(pa.artikel, "17846")
