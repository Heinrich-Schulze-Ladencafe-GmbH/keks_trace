"""Einwaage wie bei FOBIS: Lagerort je Zutat und Gebinde mit festem Inhalt (Sack, Kollo).

Ausführen:
	bench --site <site> run-tests --module keks_trace.tests.test_einwaage
"""

import frappe
from frappe.tests import IntegrationTestCase

from keks_trace import demo, terminal


class TestEinwaage(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = demo.stammdaten()
		if not frappe.db.exists("UOM", "Sack"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Sack"}).insert()
		butter = frappe.get_doc("Item", "KT-BUTTER")
		butter.uoms = [u for u in butter.uoms if u.uom != "Sack"]
		butter.append("uoms", {"uom": "Sack", "conversion_factor": 25})
		butter.item_defaults = [d for d in butter.item_defaults if d.company != cls.ctx.company]
		cls.lager = frappe.get_all(
			"Warehouse", filters={"company": cls.ctx.company, "is_group": 0}, pluck="name", limit=1
		)[0]
		butter.append("item_defaults", {"company": cls.ctx.company, "default_warehouse": cls.lager})
		butter.save()

	def test_lagerort_und_gebinde_im_rezept(self):
		r = terminal.rezept("KT-GT-MUERBE", 100)
		z = {x["artikel"]: x for x in r["zutaten"]}
		butter = z["KT-BUTTER"]
		self.assertEqual(butter["gebinde"], [{"einheit": "Sack", "faktor": 25.0}])
		self.assertEqual(butter["lager"], frappe.db.get_value("Warehouse", self.lager, "warehouse_name"))
		# Lagereinheit selbst ist kein Gebinde; ohne Umrechnung keine Gebinde
		self.assertFalse([g for g in butter["gebinde"] if g["einheit"] == butter["einheit"]])
		self.assertEqual(z["KT-ZUCKER"]["gebinde"], [])

	def test_quelllager_der_stueckliste_geht_vor(self):
		bom = frappe.get_doc("BOM", terminal.rezept("KT-GT-MUERBE")["bom"])
		anderes = frappe.get_all(
			"Warehouse",
			filters={"company": self.ctx.company, "is_group": 0, "name": ["!=", self.lager]},
			pluck="name",
			limit=1,
		)[0]
		zeile = next(x for x in bom.items if x.item_code == "KT-BUTTER")
		frappe.db.set_value("BOM Item", zeile.name, "source_warehouse", anderes)
		frappe.clear_document_cache("BOM", bom.name)
		z = {x["artikel"]: x for x in terminal.rezept("KT-GT-MUERBE")["zutaten"]}
		self.assertEqual(z["KT-BUTTER"]["lager"], frappe.db.get_value("Warehouse", anderes, "warehouse_name"))
