"""Behälter: nach dem Leeren zur Reinigung (je Behälterart einstellbar), Meldung „gereinigt“ am Terminal.

Und: die Oberfläche schickt die Anfrage-ID (Doppelbuchung) genau an die Methoden, die der Server schützt.
"""

import os
import re

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from keks_trace import demo, terminal
from keks_trace.terminal import TerminalFehler
from keks_trace.utils import einstellungen


def _setze(**werte):
	"""Nur im Speicher (utils.einstellungen), nie in der Datenbank."""
	frappe.local.kt_einstellungen = {**(getattr(frappe.local, "kt_einstellungen", None) or {}), **werte}


def _hash():
	return frappe.generate_hash(length=5).upper() + "7"


class TestBehaelterReinigung(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = demo.stammdaten()
		cls.enterClassContext(einstellungen())  # Überschreibungen dieser Klasse am Ende verwerfen

	def _fuellen_und_leeren(self):
		kuebel = demo.neuer_traeger(f"TR-{_hash()}", "Teigbehälter")
		charge = demo.neue_charge("KT-GT-MUERBE", f"GTR-{_hash()}", nowdate())
		demo.buchen(
			self.ctx,
			"Material Receipt",
			nowdate(),
			"06:00:00",
			ausgaenge=[("KT-GT-MUERBE", charge, 20, kuebel)],
		)
		self.assertEqual(frappe.db.get_value("Produkttraeger", kuebel, "status"), "Belegt")
		with self.assertRaisesRegex(TerminalFehler, "enthält noch"):
			terminal.behaelter_reinigung("Backstube", kuebel, 0)
		demo.buchen(
			self.ctx,
			"Material Issue",
			nowdate(),
			"07:00:00",
			eingaenge=[("KT-GT-MUERBE", charge, 20, kuebel)],
		)
		return kuebel

	def test_ohne_einstellung_wie_bisher_frei(self):
		_setze(reinigung_teigbehaelter=0)
		kuebel = self._fuellen_und_leeren()
		self.assertEqual(frappe.db.get_value("Produkttraeger", kuebel, "status"), "Frei")
		self.assertEqual(terminal._ziel_behaelter(kuebel), kuebel)

	def test_mit_einstellung_erst_reinigen(self):
		_setze(reinigung_teigbehaelter=1)
		kuebel = self._fuellen_und_leeren()
		self.assertEqual(frappe.db.get_value("Produkttraeger", kuebel, "status"), "Reinigung")
		with self.assertRaisesRegex(TerminalFehler, "zur Reinigung"):
			terminal._ziel_behaelter(kuebel)
		r = terminal.behaelter_reinigung("Backstube", kuebel, 1)
		self.assertEqual(r["status"], "Frei")
		t = frappe.db.get_value("Produkttraeger", kuebel, ["gereinigt_am", "gereinigt_station"], as_dict=True)
		self.assertTrue(t.gereinigt_am)
		self.assertEqual(t.gereinigt_station, "Backstube")
		self.assertEqual(terminal._ziel_behaelter(kuebel), kuebel)
		self.assertTrue(terminal.info(kuebel)["gereinigt_am"])

	def test_von_hand_zur_reinigung_und_gebinde_nie(self):
		frei = demo.neuer_traeger(f"TR-{_hash()}", "Rework-Behälter")
		self.assertEqual(terminal.behaelter_reinigung("Backstube", frei, 0)["status"], "Reinigung")
		gebinde = terminal._neues_gebinde("Sack")
		with self.assertRaisesRegex(TerminalFehler, "Gebinde"):
			terminal.behaelter_reinigung("Backstube", gebinde, 1)


class TestAnfrageId(IntegrationTestCase):
	def test_anfrage_liste(self):
		"""MIT_ANFRAGE_ID in terminal.html == alle @einmalig-Methoden im Paket keks_trace.terminal."""
		paket = os.path.dirname(terminal.__file__)
		ordner = os.path.dirname(paket)
		py = "".join(open(os.path.join(paket, f)).read() for f in os.listdir(paket) if f.endswith(".py"))
		html = open(os.path.join(ordner, "www", "terminal.html")).read()
		einmalig = set(re.findall(r"@einmalig\ndef (\w+)", py))
		liste = set(
			re.findall(r'"(\w+)"', re.search(r"MIT_ANFRAGE_ID = new Set\(\[(.*?)\]\)", html).group(1))
		)
		self.assertEqual(liste, einmalig)

	def test_paket_bietet_alle_funktionen(self):
		"""Jede Funktion der Untermodule ist unter keks_trace.terminal.<name> erreichbar (API-Pfad)."""
		import importlib
		import inspect

		paket = os.path.dirname(terminal.__file__)
		for datei in sorted(os.listdir(paket)):
			if not datei.endswith(".py") or datei == "__init__.py":
				continue
			modul = importlib.import_module("keks_trace.terminal." + datei[:-3])
			for name, f in inspect.getmembers(modul, inspect.isfunction):
				if f.__module__ == modul.__name__:
					self.assertIs(getattr(terminal, name, None), f, f"{datei}: {name}")
