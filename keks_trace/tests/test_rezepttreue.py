"""Rezepturtreue: Einwaage je Zutat gegen das Soll (auf die Sollmenge umgerechnet), Toleranz je Rezeptzeile."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from keks_trace import demo, terminal
from keks_trace.terminal import TerminalFehler
from keks_trace.utils import einstellungen


def _setze(**werte):
	"""Nur im Speicher (utils.einstellungen), nie in der Datenbank: nichts bleibt im Testsystem hängen."""
	frappe.local.kt_einstellungen = {**(getattr(frappe.local, "kt_einstellungen", None) or {}), **werte}


def _z(artikel, menge):
	return {"artikel": artikel, "menge": menge}


class TestRezepttreue(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.enterClassContext(einstellungen())  # Überschreibungen dieser Klasse am Ende verwerfen
		cls.ctx = demo.stammdaten()
		cls.bom = frappe.db.get_value(
			"BOM", {"item": "KT-GT-MUERBE", "is_default": 1, "is_active": 1, "docstatus": 1}
		)

	def setUp(self):
		_setze(rezept_abweichung="Grund Pflicht", rezept_toleranz_prozent=5, rezept_toleranz_min=0.01)

	def _mhalb(self, butter=10, zucker=10):
		"""Halbe Masse Mürbeteig: Soll 50 kg = Mehl 30, Zucker 10, Butter 10."""
		return [_z("KT-MEHL", 30), _z("KT-ZUCKER", zucker), _z("KT-BUTTER", butter)]

	def test_halbe_masse_in_toleranz(self):
		self.assertIsNone(terminal._pruefe_rezept("KT-GT-MUERBE", 50, self._mhalb(), None))
		self.assertIsNone(terminal._pruefe_rezept("KT-GT-MUERBE", 50, self._mhalb(butter=10.4), None))  # 4 %

	def test_ueber_toleranz_braucht_grund(self):
		with self.assertRaisesRegex(TerminalFehler, "außerhalb der Toleranz"):
			terminal._pruefe_rezept("KT-GT-MUERBE", 50, self._mhalb(butter=13), None)
		text = terminal._pruefe_rezept("KT-GT-MUERBE", 50, self._mhalb(butter=13), "Korrektur nach Prüfung")
		self.assertIn("Grund: Korrektur nach Prüfung", text)
		self.assertIn("+30 %", text)

	def test_fehlende_zutat_ist_abweichung(self):
		with self.assertRaisesRegex(TerminalFehler, "außerhalb der Toleranz"):
			terminal._pruefe_rezept("KT-GT-MUERBE", 50, [_z("KT-MEHL", 30), _z("KT-BUTTER", 10)], None)

	def test_toleranz_an_der_rezeptzeile(self):
		zeile = frappe.db.get_value("BOM Item", {"parent": self.bom, "item_code": "KT-BUTTER"})
		frappe.db.set_value("BOM Item", zeile, "kt_toleranz_prozent", 50)
		frappe.clear_document_cache("BOM", self.bom)
		try:
			self.assertIsNone(terminal._pruefe_rezept("KT-GT-MUERBE", 50, self._mhalb(butter=13), None))
			butter = next(
				z for z in terminal.rezept("KT-GT-MUERBE", 50)["zutaten"] if z["artikel"] == "KT-BUTTER"
			)
			self.assertAlmostEqual(butter["toleranz"], 5)
		finally:
			frappe.db.set_value("BOM Item", zeile, "kt_toleranz_prozent", 0)
			frappe.clear_document_cache("BOM", self.bom)

	def test_mindesttoleranz_bei_kleinen_mengen(self):
		_setze(rezept_toleranz_min=0.05)
		# Soll 0,5 kg -> Mehl 0,3; 5 % wären 15 g, Minimum 50 g gilt
		self.assertIsNone(
			terminal._pruefe_rezept(
				"KT-GT-MUERBE", 0.5, [_z("KT-MEHL", 0.34), _z("KT-ZUCKER", 0.1), _z("KT-BUTTER", 0.1)], None
			)
		)

	def test_einstellung_und_stufen(self):
		_setze(rezept_abweichung="Nur Hinweis")
		self.assertIn("Ohne Grund", terminal._pruefe_rezept("KT-GT-MUERBE", 50, self._mhalb(butter=13), None))
		_setze(rezept_abweichung="Aus")
		self.assertIsNone(terminal._pruefe_rezept("KT-GT-MUERBE", 50, self._mhalb(butter=13), None))
		_setze(rezept_abweichung="Grund Pflicht")
		self.assertIsNone(
			terminal._pruefe_rezept("KT-GT-MUERBE", None, self._mhalb(butter=13), None)
		)  # ohne Soll
		self.assertIsNone(
			terminal._pruefe_rezept("KT-FW-KAKAO-NOUGAT", 50, [_z("KT-FOLIE", 9)], None)
		)  # Fertigware

	def test_buchung_speichert_abweichung(self):
		_setze(fefo_rohstoffe="Aus", vollstaendigkeit="Warnen")
		h = frappe.generate_hash(length=5).upper() + "7"
		nuss = terminal.wareneingang("Lager", "KT-HASELNUSS", f"HRT{h}", 20, add_days(nowdate(), 300))[
			"charge"
		]
		with self.assertRaisesRegex(TerminalFehler, "außerhalb der Toleranz"):
			terminal.herstellen("Backstube", "KT-NOUGAT", [{"code": nuss, "menge": 10}], sollmenge=30)
		e = terminal.herstellen(
			"Backstube",
			"KT-NOUGAT",
			[{"code": nuss, "menge": 10}],
			sollmenge=30,
			rezept_grund="Rest aufgebraucht",
		)
		text = frappe.db.get_value("Stock Entry", e["buchung"], "kt_rezept_abweichung")
		self.assertIn("Grund: Rest aufgebraucht", text)
		self.assertIn("Sollmenge 30", text)
