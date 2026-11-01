"""FEFO bei Rohstoffen und Packmitteln: jüngere Charge genommen, ältere im Lager -> Grund (Einstellung)."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from keks_trace import demo, terminal
from keks_trace.keks_trace.report.mhd_rohstoffe.mhd_rohstoffe import daten as mhd_daten
from keks_trace.terminal import TerminalFehler
from keks_trace.utils import einstellungen

TEST_ARTIKEL = "KT-TEST-FEFO"


def _hash():
	return frappe.generate_hash(length=5).upper() + "7"


def _einstellung(feld, wert):
	"""Nur im Speicher (utils.einstellungen), nie in der Datenbank: nichts bleibt im Testsystem hängen."""
	frappe.local.kt_einstellungen = {**(getattr(frappe.local, "kt_einstellungen", None) or {}), feld: wert}


class TestFefo(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.enterClassContext(einstellungen())  # Überschreibungen dieser Klasse am Ende verwerfen
		cls.ctx = demo.stammdaten()
		if not frappe.db.exists("Item", TEST_ARTIKEL):
			frappe.get_doc(
				{"doctype": "Item", "item_code": TEST_ARTIKEL, "item_name": "Test-Rohstoff FEFO",
				 "item_group": frappe.db.get_value("Item", "KT-HASELNUSS", "item_group"), "stock_uom": "Kg",
				 "is_stock_item": 1, "has_batch_no": 1, "has_expiry_date": 1, "kt_chargen_stufe": "Rohstoff"}
			).insert()  # fmt: skip
		# Eigener Test-Artikel: Demo-Bestände echter Rohstoffe stören die Erwartungen nicht
		h = _hash()
		cls.a = cls._eingang(f"FA{h}", 10)  # frühestes MHD
		cls.b = cls._eingang(f"FB{h}", 100)
		cls.c = cls._eingang(f"FC{h}", 50)  # gesperrt
		cls.d = cls._eingang(f"FD{h}", 5)  # wird abgelaufen
		frappe.db.set_value("Batch", cls.c, "kt_status", "Gesperrt")
		frappe.db.set_value("Batch", cls.d, "expiry_date", add_days(nowdate(), -1))

	@classmethod
	def _eingang(cls, charge, tage):
		terminal.wareneingang("Lager", TEST_ARTIKEL, charge, 10, add_days(nowdate(), tage))
		return charge

	def _zeile(self, charge):
		return {"artikel": TEST_ARTIKEL, "charge": charge, "typ": "charge", "name": "Test", "einheit": "Kg"}

	def _aeltere(self, charge, verwendet=()):
		# Nur die Chargen dieses Laufs betrachten (frühere Läufe liegen mit eigenem MHD im Lager)
		eigene = {self.a, self.b, self.c, self.d}
		return [
			x["charge"]
			for x in terminal._fefo_aeltere(TEST_ARTIKEL, charge, verwendet)
			if x["charge"] in eigene
		]

	def test_aeltere_ohne_gesperrte_und_abgelaufene(self):
		self.assertEqual(self._aeltere(self.b), [self.a])
		self.assertEqual(self._aeltere(self.a), [])
		self.assertEqual(self._aeltere(self.b, {self.a}), [])  # in derselben Buchung verbraucht

	def test_einstellung_grund_pflicht_hinweis_aus(self):
		_einstellung("fefo_rohstoffe", "Grund Pflicht")
		with self.assertRaisesRegex(TerminalFehler, "Älteres MHD"):
			terminal._pruefe_fefo([self._zeile(self.b)], None)
		text = terminal._pruefe_fefo([self._zeile(self.b)], "Anweisung QS")
		self.assertIn("Grund: Anweisung QS", text)
		self.assertIsNone(terminal._pruefe_fefo([self._zeile(self.b), self._zeile(self.a)], None))
		_einstellung("fefo_rohstoffe", "Nur Hinweis")
		self.assertIn("Ohne Grund", terminal._pruefe_fefo([self._zeile(self.b)], None))
		_einstellung("fefo_rohstoffe", "Aus")
		self.assertIsNone(terminal._pruefe_fefo([self._zeile(self.b)], None))

	def test_herstellen_speichert_grund(self):
		"""Echte Buchung: Nougat mit jüngerer Haselnuss-Charge, ältere liegt im Lager."""
		_einstellung("fefo_rohstoffe", "Grund Pflicht")
		_einstellung("vollstaendigkeit", "Warnen")
		h = _hash()
		terminal.wareneingang("Lager", "KT-HASELNUSS", f"HFA{h}", 20, add_days(nowdate(), 1))
		neu = terminal.wareneingang("Lager", "KT-HASELNUSS", f"HFN{h}", 20, add_days(nowdate(), 800))[
			"charge"
		]
		z = terminal.pruefe_zeile("Backstube", "KT-NOUGAT", neu, 10)
		self.assertTrue(z["fefo"] and z["fefo_pflicht"])
		with self.assertRaisesRegex(TerminalFehler, "Älteres MHD"):
			terminal.herstellen("Backstube", "KT-NOUGAT", [{"code": neu, "menge": 10}])
		e = terminal.herstellen(
			"Backstube",
			"KT-NOUGAT",
			[{"code": neu, "menge": 10}],
			fefo_grund="Ältere Charge nicht erreichbar",
		)
		text = frappe.db.get_value("Stock Entry", e["buchung"], "kt_fefo_abweichung")
		self.assertIn("Grund: Ältere Charge nicht erreichbar", text)
		self.assertIn(neu, text)

	def test_bericht_mhd_und_rest(self):
		"""Bericht: Charge A (MHD in 10 Tagen) ohne Verbrauch bleibt ganz übrig; abgelaufene D erscheint mit Minus-Tagen."""
		zeilen = {z["charge"]: z for z in mhd_daten(("Rohstoff",), 60, 60, TEST_ARTIKEL)}
		self.assertIn(self.a, zeilen)
		self.assertNotIn(self.b, zeilen)  # MHD in 100 Tagen, außerhalb von 60
		self.assertEqual(zeilen[self.a]["tage_bis_mhd"], 10)
		self.assertAlmostEqual(zeilen[self.a]["uebrig"], 10)  # kein Verbrauch -> alles übrig
		self.assertLess(zeilen[self.d]["tage_bis_mhd"], 0)
		self.assertEqual(zeilen[self.c]["status"], "Gesperrt")


class TestEinstellungenImSpeicher(IntegrationTestCase):
	def test_ueberschreibung_nie_in_der_datenbank(self):
		"""Demos und Tests stellen Regeln nur im Speicher um; die Datenbank bleibt unberührt (auch bei Commit)."""
		from keks_trace.utils import einstellung, regel_nur_hinweis

		db = frappe.db.get_single_value("Keks Trace Einstellungen", "fefo_rohstoffe")
		with regel_nur_hinweis("fefo_rohstoffe"):
			self.assertEqual(einstellung("fefo_rohstoffe"), "Nur Hinweis")
			self.assertEqual(frappe.db.get_single_value("Keks Trace Einstellungen", "fefo_rohstoffe"), db)
			with einstellungen(fefo_rohstoffe="Aus"):
				self.assertEqual(einstellung("fefo_rohstoffe"), "Aus")
			self.assertEqual(einstellung("fefo_rohstoffe"), "Nur Hinweis")
		self.assertEqual(einstellung("fefo_rohstoffe"), db)
