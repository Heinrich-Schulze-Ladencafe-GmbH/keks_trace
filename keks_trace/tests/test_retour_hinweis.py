"""Retour von der Linie, Hinweis des Büros am Auftrag und Tagesübersicht.

Ausführen:
	bench --site <site> run-tests --module keks_trace.tests.test_retour_hinweis
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, nowdate

from keks_trace import demo_linie, linienbuchung, terminal
from keks_trace.linienbuchung import LinienFehler
from keks_trace.utils import regel_nur_hinweis


def _hash():
	return frappe.generate_hash(length=5).upper() + "7"


class TestRetourHinweis(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.enterClassContext(regel_nur_hinweis("fefo_rohstoffe"))
		cls.ctx = demo_linie.stammdaten()
		cls.h = _hash()

	def _auftrag(self, **felder):
		return frappe.get_doc(
			{
				"doctype": "Produktionsauftrag",
				"linie": demo_linie.LINIE,
				"datum": nowdate(),
				"artikel": "17846",
				"menge": 20,
				"einheit": "Karton",
				"status": "Freigegeben",
				**felder,
			}
		).insert()

	def test_retour_ins_lager(self):
		pa = self._auftrag()
		linienbuchung.waehlen("Former", pa.name)
		we = terminal.wareneingang("Lager", "9101", f"B{self.h}", 100, add_days(nowdate(), 300))
		charge = we["charge"]
		herkunft = terminal.charge_lager(charge)
		terminal.linie_zufuehren("Former", charge, 100)
		self.assertEqual(sum(terminal.charge_lager(charge).values()), 100)

		liste = {z["charge"]: z for z in terminal.linie_retour_liste("Former")}
		self.assertIn(charge, liste)
		self.assertEqual(liste[charge]["menge"], 100)
		self.assertFalse(liste[charge]["silo"])
		self.assertEqual(liste[charge]["ziel"], next(iter(herkunft)))

		with self.assertRaisesRegex(LinienFehler, "nur 100"):
			terminal.linie_rueckgabe("Former", charge, 150)
		r = terminal.linie_rueckgabe("Former", charge, 60)
		self.assertEqual(r["menge"], 60)
		# 60 wieder im Lager, 40 noch auf der Linie
		self.assertAlmostEqual(terminal.charge_lager(charge)[next(iter(herkunft))], 60)
		self.assertAlmostEqual(
			sum(flt(z["menge"]) for z in linienbuchung.bestand(pa.name) if z["charge"] == charge), 40
		)
		# Beim Auftragsende wird nur noch der Rest als Linienrest ausgebucht
		ende = linienbuchung.beenden("Former", pa.name)
		rest = {z["charge"]: z["menge"] for z in ende["rest"]}
		self.assertAlmostEqual(rest[charge], 40)
		self.assertAlmostEqual(terminal.charge_lager(charge)[next(iter(herkunft))], 60)

	def test_hinweis_vom_buero(self):
		so = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"customer": self.ctx.kunde if self.ctx.get("kunde") else frappe.db.get_value("Customer", {}),
				"company": self.ctx.company,
				"delivery_date": add_days(nowdate(), 7),
				"transaction_date": nowdate(),
				"kt_hinweis_produktion": "Mit Clip, Folie 2026",
				"items": [
					{"item_code": "17846", "qty": 1, "rate": 1, "delivery_date": add_days(nowdate(), 7)}
				],
			}
		).insert()
		pa = self._auftrag(kundenauftrag=so.name, bemerkung="Neue Folie ab heute")
		texte = [h["text"] for h in linienbuchung.info(pa.name)["hinweise"]]
		self.assertEqual(texte, ["Neue Folie ab heute", "Mit Clip, Folie 2026"])
		zeile = next(a for a in terminal.linie_auftraege("Former") if a["name"] == pa.name)
		self.assertEqual(zeile["hinweis"], "Neue Folie ab heute · Mit Clip, Folie 2026")
		# ohne Hinweis: leer
		self.assertEqual(linienbuchung.info(self._auftrag().name)["hinweise"], [])

	def test_tagesuebersicht(self):
		heute = self._auftrag(bemerkung="Erst nach Reinigung")
		gestern = self._auftrag(datum=add_days(nowdate(), -1))
		fertig = self._auftrag(status="Fertig")
		t = terminal.tagesuebersicht("Former")
		self.assertTrue(t["heute"])
		linie = next(l for l in t["linien"] if l["linie"] == demo_linie.LINIE)
		namen = {a["auftrag"]: a for a in linie["auftraege"]}
		self.assertIn(heute.name, namen)
		self.assertIn(fertig.name, namen)
		self.assertTrue(namen[gestern.name]["vortag"])  # noch freigegeben von gestern: heute sichtbar
		self.assertEqual(namen[heute.name]["hinweis"], "Erst nach Reinigung")
		self.assertGreaterEqual(linie["fertig"], 1)
		# am Vortag selbst steht der Auftrag normal, ohne „vom“
		v = terminal.tagesuebersicht("Former", add_days(nowdate(), -1))
		self.assertFalse(v["heute"])
		self.assertFalse(
			next(a for l in v["linien"] for a in l["auftraege"] if a["auftrag"] == gestern.name)["vortag"]
		)
