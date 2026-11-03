"""Versandkarton mit eigener NVE, auf einer Palette mit NVE (eine Ebene), NVE-Nummernkreis.

Ausführen:
	bench --site <site> run-tests --module keks_trace.tests.test_versandkarton
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from keks_trace import akte, demo, etiketten, gs1, palette, sperre, terminal
from keks_trace.palette import PalettenFehler
from keks_trace.utils import regel_nur_hinweis


def _hash():
	return frappe.generate_hash(length=6).upper() + "7"


class TestVersandkarton(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.enterClassContext(regel_nur_hinweis("fefo_rohstoffe"))
		cls.ctx = demo.stammdaten()
		demo.metalldetektor_ok("Verpackung")
		if not frappe.db.exists("NVE Nummernkreis", {"standard": 1}):
			frappe.get_doc(
				{
					"doctype": "NVE Nummernkreis",
					"kreis_name": f"Eigener {_hash()}",
					"art": "Eigener",
					"aktiv": 1,
					"standard": 1,
				}
			).insert()

	def _los(self, kartons=10):
		"""Fertigware lose im Lager (auf keiner Palette): kartons x 2,4 kg."""
		wl = demo.neue_charge("KT-WL-KAKAO-NOUGAT", f"WLV{_hash()}", nowdate())
		demo.buchen(
			self.ctx, "Material Receipt", nowdate(), "05:00:00", ausgaenge=[("KT-WL-KAKAO-NOUGAT", wl, 60)]
		)
		sperre.freigeben(wl, "Test")
		fol = demo.neue_charge("KT-FOLIE", f"FOLV{_hash()}")
		demo.buchen(self.ctx, "Material Receipt", nowdate(), "05:00:00", ausgaenge=[("KT-FOLIE", fol, 5)])
		e = terminal.herstellen(
			"Verpackung",
			"KT-FW-KAKAO-NOUGAT",
			[{"code": wl, "menge": 48}, {"code": fol, "menge": 1}],
			anzahl=kartons,
			einheit="Karton",
		)
		return e["charge"]

	def _karton(self, charge, n):
		k = terminal.palette_neu("Versand", palette.VERSANDKARTON)["nve"]
		terminal.palette_beladen("Versand", k, charge, n, "Karton")
		return k

	def test_nve_aus_dem_nummernkreis(self):
		k = terminal.palette_neu("Versand", palette.VERSANDKARTON)
		self.assertEqual(k["art"], palette.VERSANDKARTON)
		self.assertTrue(gs1.pruefziffer_ok(k["nve"]))
		self.assertEqual(frappe.db.get_value("Palette", k["nve"], "nve_kreis"), palette.standard_kreis())
		fremd = frappe.get_doc(
			{
				"doctype": "NVE Nummernkreis",
				"kreis_name": f"Kunde {_hash()}",
				"art": "Bereich vom Kunden",
				"aktiv": 1,
			}
		).insert()
		with self.assertRaisesRegex(PalettenFehler, "noch nicht freigeschaltet"):
			palette.nve_neu(fremd.name)
		with self.assertRaisesRegex(frappe.ValidationError, "7 bis 10 Ziffern"):
			frappe.get_doc(
				{"doctype": "NVE Nummernkreis", "kreis_name": f"X {_hash()}", "basisnummer": "12AB"}
			).insert()

	def test_karton_auf_palette_und_regeln(self):
		c = self._los(10)
		k1, k2 = self._karton(c, 3), self._karton(c, 2)
		p = terminal.palette_neu("Versand", "Versandpalette")["nve"]
		palette.etikett_gedruckt(p)  # Etikett der leeren Palette gedruckt
		terminal.karton_auf_palette("Versand", k1, p)
		i = terminal.karton_auf_palette("Versand", k2, p)
		self.assertEqual([x["nve"] for x in i["versandkartons"]], [k1, k2])
		self.assertTrue(i["kartons"].startswith("2 Versandkartons"))
		self.assertEqual([(x["charge"], x["anzahl"]) for x in i["positionen_gesamt"]], [(c, 5)])
		self.assertFalse(i["etikett_aktuell"])  # Kartons dazu: Etikett der Palette neu drucken
		self.assertEqual(frappe.db.get_value("Palette", k1, ["status", "auf_palette"]), ("Geschlossen", p))
		# Regeln: nur Versandkartons, nicht in einen Karton, nicht leer
		with self.assertRaisesRegex(PalettenFehler, "nicht in einen anderen Versandkarton"):
			terminal.karton_auf_palette("Versand", k2, k1)
		andere = terminal.palette_neu("Versand", "Versandpalette")["nve"]
		with self.assertRaisesRegex(PalettenFehler, "kein Versandkarton"):
			terminal.karton_auf_palette("Versand", andere, p)
		leer = terminal.palette_neu("Versand", palette.VERSANDKARTON)["nve"]
		with self.assertRaisesRegex(PalettenFehler, "leer"):
			terminal.karton_auf_palette("Versand", leer, p)
		# Etikett der Palette zeigt alles zusammen, der Karton sein eigenes
		e = palette.etikett(p)
		self.assertEqual(e["positionen"][0]["anzahl"], 5)
		self.assertIn("2 Versandkartons", etiketten.zpl_palette(e))
		# Umsetzen auf eine andere Palette protokolliert Ab und Auf
		terminal.karton_auf_palette("Versand", k2, andere)
		self.assertEqual(
			frappe.get_all(
				"Versandkarton Zuordnung", filters={"karton": k2}, pluck="richtung", order_by="creation"
			),
			["Auf", "Ab", "Auf"],
		)
		self.assertIn("Versandkarton", [x["art"] for x in akte.palette(p)["ereignisse"]])

	def test_ganze_palette_mit_kartons_liefern_und_storno(self):
		c = self._los(10)
		k1, k2 = self._karton(c, 3), self._karton(c, 2)
		p = terminal.palette_neu("Versand", "Versandpalette")["nve"]
		terminal.karton_auf_palette("Versand", k1, p)
		terminal.karton_auf_palette("Versand", k2, p)
		ls = terminal.lieferung("Versand", self.ctx.kunde, [{"palette": p, "ganz": 1}])
		zeilen = frappe.get_all(
			"Delivery Note Item", filters={"parent": ls["lieferschein"]}, fields=["kt_palette", "qty"]
		)
		self.assertEqual(sorted(z.kt_palette for z in zeilen), sorted([k1, k2]))  # gebucht je Karton
		for nve in (p, k1, k2):
			self.assertEqual(
				frappe.db.get_value("Palette", nve, ["status", "lieferschein"]),
				("Versendet", ls["lieferschein"]),
			)
		# Storno: alles wieder im Lager, die Kartons stehen weiter auf der Palette
		frappe.get_doc("Delivery Note", ls["lieferschein"]).cancel()
		for nve in (p, k1, k2):
			self.assertEqual(frappe.db.get_value("Palette", nve, "status"), "Geschlossen")
		self.assertEqual(palette.kartons(p), [k1, k2])

	def test_einzelnen_karton_von_der_palette_liefern(self):
		c = self._los(10)
		k1, k2 = self._karton(c, 3), self._karton(c, 2)
		p = terminal.palette_neu("Versand", "Versandpalette")["nve"]
		terminal.karton_auf_palette("Versand", k1, p)
		terminal.karton_auf_palette("Versand", k2, p)
		ls = terminal.lieferung("Versand", self.ctx.kunde, [{"palette": k1, "ganz": 1}])
		self.assertEqual(frappe.db.get_value("Palette", k1, ["status", "auf_palette"]), ("Versendet", None))
		self.assertEqual(palette.kartons(p), [k2])
		self.assertEqual(frappe.db.get_value("Palette", p, "status"), "Offen")  # bleibt im Lager
		ab = frappe.get_all(
			"Versandkarton Zuordnung", filters={"karton": k1, "richtung": "Ab"}, pluck="beleg"
		)
		self.assertEqual(ab, [ls["lieferschein"]])

	def test_paket_als_versandkarton(self):
		self._los(10)
		so = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"customer": self.ctx.kunde,
				"company": self.ctx.company,
				"transaction_date": nowdate(),
				"delivery_date": add_days(nowdate(), 3),
				"items": [
					{
						"item_code": "KT-FW-KAKAO-NOUGAT",
						"qty": 4,
						"uom": "Karton",
						"conversion_factor": 2.4,
						"rate": 10,
						"warehouse": self.ctx.fertig,
					}
				],
			}
		).insert()
		so.submit()
		a = terminal.paket_karton("Versand", so.name, "KT-FW-KAKAO-NOUGAT", 4.8, 5.2)
		b = terminal.paket_karton("Versand", so.name, "KT-FW-KAKAO-NOUGAT", 2.4, 2.7)
		self.assertEqual(
			(a["art"], a["status"], a["gewicht_kg"]), (palette.VERSANDKARTON, "Geschlossen", 5.2)
		)
		lose = sorted({x["charge"] for x in a["positionen"] + b["positionen"]})  # älteste Lose zuerst
		e = terminal.paket_lieferung(
			"Versand", so.name, kartons=[a["nve"], b["nve"]], sendungsnummer="00340434161234567890"
		)
		dn = frappe.db.get_value(
			"Delivery Note", e["lieferschein"], ["kt_pakete", "kt_gewicht_kg"], as_dict=True
		)
		self.assertEqual((dn.kt_pakete, dn.kt_gewicht_kg), (2, 7.9))
		self.assertEqual(frappe.db.get_value("Palette", a["nve"], "sendungsnummer"), "00340434161234567890")
		r = terminal.sendungsnummer("Versand", e["lieferschein"], "00340434161234567891")
		self.assertEqual(r["versandkarton"], b["nve"])
		self.assertEqual(e["lose"], lose)
		with self.assertRaisesRegex(frappe.ValidationError, "doppelt"):
			terminal.paket_lieferung("Versand", so.name, kartons=[b["nve"], b["nve"]])
