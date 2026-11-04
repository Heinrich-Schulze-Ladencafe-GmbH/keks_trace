"""Wareneingang am Terminal zu einer Bestellung (Einkauf): Auswahl, Prüfungen, Verweis in Akte und Netzbild.

Ausführen:
	bench --site <site> run-tests --module keks_trace.tests.test_wareneingang_bestellung
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from keks_trace import akte, demo, netz, terminal
from keks_trace.terminal import TerminalFehler

ARTIKEL = "KT-SALZ"
STATION = "Backstube"


def _hash():
	return frappe.generate_hash(length=6).upper() + "7"


class TestWareneingangBestellung(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = demo.stammdaten()
		cls.anderer = "KT Test Lieferant Bestellung"
		if not frappe.db.exists("Supplier", cls.anderer):
			frappe.get_doc(
				{"doctype": "Supplier", "supplier_name": cls.anderer, "supplier_group": "All Supplier Groups"}
			).insert()

	def _bestellung(self, menge=100, artikel=ARTIKEL):
		po = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"supplier": self.ctx.lieferant,
				"company": self.ctx.company,
				"transaction_date": nowdate(),
				"schedule_date": add_days(nowdate(), 3),
				"items": [
					{
						"item_code": artikel,
						"qty": menge,
						"rate": 1,
						"schedule_date": add_days(nowdate(), 3),
						"warehouse": frappe.db.get_value("Terminal Station", STATION, "rohstofflager"),
					}
				],
			}
		).insert()
		po.submit()
		return po.name

	def _offen(self, bestellung):
		z = next((b for b in terminal._bestellungen(ARTIKEL) if b["bestellung"] == bestellung), None)
		return z["offen"] if z else 0

	def test_eingang_zur_bestellung(self):
		po = self._bestellung(100)
		art = next(a for a in terminal.wareneingang_artikel() if a["artikel"] == ARTIKEL)
		self.assertIn(po, [b["bestellung"] for b in art["bestellungen"]])
		self.assertEqual(self._offen(po), 100)
		# ohne Lieferant: der der Bestellung gilt
		e = terminal.wareneingang(STATION, ARTIKEL, f"S{_hash()}", 40, bestellung=po)
		self.assertEqual(e["bestellung"], po)
		self.assertEqual(frappe.db.get_value("Stock Entry", e["buchung"], "kt_bestellung"), po)
		self.assertEqual(frappe.db.get_value("Batch", e["charge"], "supplier"), self.ctx.lieferant)
		self.assertEqual(self._offen(po), 60)
		# Rest geliefert: nicht mehr in der Auswahl
		terminal.wareneingang(
			STATION, ARTIKEL, f"S{_hash()}", 60, lieferant=self.ctx.lieferant, bestellung=po
		)
		self.assertEqual(self._offen(po), 0)
		# in Akte und Belegliste sichtbar
		self.assertEqual(akte._wareneingang(e["charge"])["bestellung"], po)
		beleg = next(b for b in netz.netz(e["charge"])["belege"] if b["charge"] == e["charge"])
		self.assertEqual((beleg["art"], beleg["bestellung"]), ("Einkauf", po))

	def test_falsche_bestellung_abgelehnt(self):
		po = self._bestellung(10)
		with self.assertRaisesRegex(TerminalFehler, "nicht bei"):
			terminal.wareneingang(STATION, ARTIKEL, f"S{_hash()}", 5, lieferant=self.anderer, bestellung=po)
		with self.assertRaisesRegex(TerminalFehler, "nicht bestellt"):
			terminal.wareneingang(
				STATION, "KT-MEHL", f"M{_hash()}", 5, mhd=add_days(nowdate(), 90), bestellung=po
			)
		frappe.get_doc("Purchase Order", po).update_status("Closed")
		with self.assertRaisesRegex(TerminalFehler, "nicht mehr offen"):
			terminal.wareneingang(STATION, ARTIKEL, f"S{_hash()}", 5, bestellung=po)

	def test_ohne_bestellung_wie_bisher(self):
		e = terminal.wareneingang(STATION, ARTIKEL, f"S{_hash()}", 5)
		self.assertIsNone(frappe.db.get_value("Stock Entry", e["buchung"], "kt_bestellung"))
		self.assertIsNone(akte._wareneingang(e["charge"])["bestellung"])
