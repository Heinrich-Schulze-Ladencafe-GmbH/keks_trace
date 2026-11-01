"""QS-Tagesliste: Abweichungen eines Tages an einer Stelle, Durchsicht je Tag als Nachweis."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from keks_trace import demo, qs_tagesliste, sperre, terminal
from keks_trace.keks_trace.report.qs_tagesliste.qs_tagesliste import execute
from keks_trace.utils import einstellungen


def _hash():
	return frappe.generate_hash(length=5).upper() + "7"


class TestQsTagesliste(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.enterClassContext(
			einstellungen(
				fefo_rohstoffe="Grund Pflicht", rezept_abweichung="Grund Pflicht", vollstaendigkeit="Warnen"
			)
		)
		cls.ctx = demo.stammdaten()
		h = _hash()
		# FEFO und Einwaage in einer Buchung: jüngere Haselnuss, nur eine von vier Zutaten
		terminal.wareneingang("Lager", "KT-HASELNUSS", f"QSA{h}", 20, add_days(nowdate(), 1))
		neu = terminal.wareneingang("Lager", "KT-HASELNUSS", f"QSN{h}", 20, add_days(nowdate(), 900))[
			"charge"
		]
		cls.buchung = terminal.herstellen(
			"Backstube", "KT-NOUGAT", [{"code": neu, "menge": 10}], sollmenge=30,
			fefo_grund="Anweisung QS", rezept_grund="Rest aufgebraucht",
		)["buchung"]  # fmt: skip
		# Prüfung außerhalb: Butter zu warm, Annahme verweigert
		terminal.wareneingang(
			"Lager", "KT-BUTTER", f"QSB{h}", 25, add_days(nowdate(), 30),
			pruefwerte={"Temperatur Kühlware Wareneingang": {"wert": 11}},
		)  # fmt: skip
		# Routinesperre: Butter mit Freigabe vor Verwendung, ordentlich gekühlt (keine Abweichung)
		cls.butter = terminal.wareneingang(
			"Lager", "KT-BUTTER", f"QSF{h}", 25, add_days(nowdate(), 30),
			pruefwerte={"Temperatur Kühlware Wareneingang": {"wert": 4}},
		)["charge"]  # fmt: skip
		# Sperre
		cls.gesperrt = terminal.wareneingang("Lager", "KT-SALZ", f"QSS{h}", 5)["charge"]
		sperre.sperren(cls.gesperrt, "Fremdkörper im Sack (Test)")

	def test_alle_arten_eines_tages(self):
		zeilen = qs_tagesliste.eintraege(nowdate())
		arten = {z["art"] for z in zeilen}
		self.assertTrue({"FEFO", "Einwaage", "Prüfung", "Sperre"} <= arten)
		fefo = [z for z in zeilen if z["art"] == "FEFO" and z["beleg"] == self.buchung]
		self.assertIn("Grund: Anweisung QS", fefo[0]["text"])
		self.assertEqual(fefo[0]["station"], "Backstube")
		einwaage = [z for z in zeilen if z["art"] == "Einwaage" and z["beleg"] == self.buchung]
		self.assertIn("Rest aufgebraucht", einwaage[0]["text"])
		pruef = [z for z in zeilen if z["art"] == "Prüfung" and "Annahme verweigert" in z["text"]]
		self.assertTrue(pruef and "11" in pruef[-1]["text"])
		self.assertIn(self.gesperrt, {z["charge"] for z in zeilen if z["art"] == "Sperre"})
		self.assertNotIn(self.butter, {z["charge"] for z in zeilen})  # Routinesperre ist keine Abweichung
		self.assertGreaterEqual(qs_tagesliste.offene_freigaben(), 1)
		self.assertEqual(zeilen, sorted(zeilen, key=lambda z: (z["zeit"], z["art"])))
		self.assertFalse(qs_tagesliste.eintraege(add_days(nowdate(), 1)))  # morgen: nichts

	def test_bericht_und_durchsicht(self):
		_spalten, zeilen, _m, _c, summe = execute({"von": nowdate()})
		self.assertTrue(zeilen)
		self.assertEqual(summe[-1]["indicator"], "Red")  # noch nicht durchgesehen
		_s, nur_sperren, *_ = execute({"von": nowdate(), "arten": ["Sperre"]})
		self.assertEqual({z["art"] for z in nur_sperren}, {"Sperre"})

		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				qs_tagesliste.durchsehen(nowdate())
		finally:
			frappe.set_user("Administrator")
		with self.assertRaisesRegex(frappe.ValidationError, "Zukunft"):
			qs_tagesliste.durchsehen(add_days(nowdate(), 1))

		vorhanden = qs_tagesliste.durchsicht(nowdate())
		if not vorhanden:
			r = qs_tagesliste.durchsehen(nowdate(), "alles geklärt")
			self.assertEqual(r["eintraege"], len(qs_tagesliste.eintraege(nowdate())))
			self.assertEqual(execute({"von": nowdate()})[4][-1]["indicator"], "Green")
		with self.assertRaisesRegex(frappe.ValidationError, "schon"):
			qs_tagesliste.durchsehen(nowdate())
		d = frappe.get_doc("QS Durchsicht", qs_tagesliste.durchsicht(nowdate()).name)
		d.bemerkung = "nachträglich geändert"
		with self.assertRaisesRegex(frappe.ValidationError, "Protokoll"):
			d.save()
