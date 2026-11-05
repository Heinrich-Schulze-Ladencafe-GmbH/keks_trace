"""Demo-Tag: frischer Demostand relativ zu heute, ein zweiter Lauf am selben Tag nimmt den vorhandenen.

Ausführen:
	bench --site <site> run-tests --module keks_trace.tests.test_demo_tag
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate, now_datetime, nowdate

from keks_trace import silo, terminal
from keks_trace.demo import tag as demo_tag


class TestDemoTag(IntegrationTestCase):
	def test_vorbereiten_und_wiederholen(self):
		a = demo_tag.vorbereiten()
		self.assertEqual(a["datum"], nowdate())
		# offene Bestellung Puderzucker für den Wareneingang live
		offen = {b["bestellung"]: b for b in terminal._bestellungen(demo_tag.BESTELLUNG_ARTIKEL)}
		self.assertIn(a["bestellung"], offen)
		# ein Herz bis zum Kunden, Puderzucker steckt drin
		d = a["durchlauf"]
		self.assertEqual(frappe.db.get_value("Delivery Note", d["lieferschein"], "docstatus"), 1)
		self.assertTrue(frappe.db.exists("Batch", d["puderzucker"]))
		# Zuckerguss im Tank ist von heute (nicht abgelaufen)
		lager = frappe.db.get_value("Silo", demo_tag.TANK, "warehouse")
		im_tank = silo.bestand(lager, now_datetime())
		self.assertTrue(im_tank)
		for c in im_tank:
			mhd = frappe.db.get_value("Batch", c["charge"], "expiry_date")
			self.assertGreaterEqual(getdate(mhd), getdate(nowdate()))
		self.assertTrue(frappe.db.get_value("Sales Order", a["kundenauftrag"], "kt_hinweis_produktion"))
		# zweiter Lauf am selben Tag: kein neues Herz, dieselbe Bestellung
		b = demo_tag.vorbereiten()
		self.assertEqual(b["durchlauf"]["lieferschein"], d["lieferschein"])
		self.assertEqual(b["bestellung"], a["bestellung"])
		s = demo_tag.stand()
		self.assertTrue(s["heute"])
		self.assertEqual(s["bestellung_offen"], demo_tag.BESTELLUNG_MENGE)

	def test_morgens_ohne_marke_tut_nichts(self):
		vorher = frappe.db.get_default(demo_tag.STAND)
		demo_tag.morgens()  # Testsite hat keine Marke der Testserver-Einrichtung
		self.assertEqual(frappe.db.get_default(demo_tag.STAND), vorher)
