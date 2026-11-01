"""Wareneingang mit Scan des Lieferanten-Etiketts (GS1-128 / EAN) und Scan in der Backstube.

Etiketten-Inhalte nach echten Lieferungen (Fotos 1.11.2026), Nummern verfremdet bzw. GS1-Testbereich 2xx.
"""

import unittest
from datetime import date

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, nowdate

from keks_trace import demo, gs1, terminal
from keks_trace import palette as paletten
from keks_trace.terminal import TerminalFehler

HEUTE = date(2026, 11, 1)


def _gtin(koerper13: str) -> str:
	"""GTIN-14 aus 13 Ziffern mit Prüfziffer."""
	return koerper13 + str(paletten.pruefziffer(koerper13))


def _hash():
	return frappe.generate_hash(length=5).upper() + "7"


class TestGs1Lesen(unittest.TestCase):
	"""Der Leser allein, ohne Datenbank."""

	def test_lesbar_mit_klammern(self):
		g = gs1.lesen("(01)04032744535179(10)6442(15)280331", HEUTE)
		self.assertEqual((g["gtin"], g["charge"], g["mhd"]), ("04032744535179", "6442", date(2028, 3, 31)))

	def test_roh_mit_trennzeichen_und_praefix(self):
		g = gs1.lesen("]C10104030632522744" + "3102002500" + gs1.GS + "10214848", HEUTE)
		self.assertEqual((g["gtin"], g["netto_kg"], g["charge"]), ("04030632522744", 25.0, "214848"))
		self.assertEqual(g["rest"], "")

	def test_charge_am_ende_ohne_trennzeichen(self):
		g = gs1.lesen("01040327445351791528033110PEGVV-3212506119HEIN", HEUTE)
		self.assertEqual(g["charge"], "PEGVV-3212506119HEIN")
		self.assertEqual(g["mhd"], date(2028, 3, 31))

	def test_tag_00_ist_monatsende(self):
		self.assertEqual(gs1.datum("270200", HEUTE), date(2027, 2, 28))
		self.assertEqual(gs1.datum("280200", HEUTE), date(2028, 2, 29))

	def test_jahrhundert(self):
		self.assertEqual(gs1.datum("761231", HEUTE).year, 2076)
		self.assertEqual(gs1.datum("771231", HEUTE).year, 1977)
		self.assertIsNone(gs1.datum("261301", HEUTE))
		self.assertIsNone(gs1.datum("260231", HEUTE))

	def test_ungueltig_ist_kein_gs1(self):
		# FOBIS-Etikett mit leerem (01): nicht als GS1 lesen, sondern ablehnen
		self.assertIsNone(gs1.lesen("(01)(10)BP2610190150964(15)271019", HEUTE))
		self.assertIsNone(gs1.lesen("(01)04032744535178(10)1", HEUTE))  # falsche Prüfziffer
		self.assertIsNone(gs1.lesen("214848", HEUTE))  # Charge im Klartext
		self.assertIsNone(gs1.lesen("PEGVV-3212506119HEIN", HEUTE))

	def test_ean(self):
		self.assertEqual(gs1.ean("4030632522744"), "4030632522744")
		self.assertIsNone(gs1.ean("4030632522745"))
		self.assertIsNone(gs1.ean("214848"))
		self.assertEqual(gs1.gtin_varianten("04030632522744")[:2], ["04030632522744", "4030632522744"])

	def test_sscc(self):
		sscc = "34032744000000001" + str(paletten.pruefziffer("34032744000000001"))
		self.assertEqual(gs1.lesen(f"(00){sscc}", HEUTE)["sscc"], sscc)
		self.assertIsNone(gs1.lesen("(00)340327440000000010", HEUTE))  # falsche Prüfziffer


class TestWareneingangScan(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = demo.stammdaten()
		cls.gtin = _gtin("0200000000901")  # Haselnuss, Sack (GS1-Bereich für interne Nummern)
		cls.ean_ohne_charge = _gtin("0200000000902")[1:]  # 13 Stellen, nur Artikel
		item = frappe.get_doc("Item", "KT-HASELNUSS")
		for code in (cls.gtin, cls.ean_ohne_charge):
			if not frappe.db.exists("Item Barcode", {"barcode": code}):
				item.append(
					"barcodes", {"barcode": code, "barcode_type": "GTIN-14" if len(code) == 14 else "EAN"}
				)
		item.save()

	def _etikett(self, charge, mhd="281231", kg=None):
		return f"(01){self.gtin}" + (f"(3102){int(kg * 100):06d}" if kg else "") + f"(15){mhd}(10){charge}"

	def test_scan_schlaegt_vor(self):
		r = terminal.wareneingang_scan(self._etikett(f"HN{_hash()}", kg=25))
		self.assertEqual(r["artikel"], "KT-HASELNUSS")
		self.assertEqual(r["menge_je_gebinde"], 25)
		self.assertEqual(r["mhd"], "2028-12-31")
		self.assertTrue(r["gs1"])
		self.assertFalse(r.get("charge_bekannt"))

	def test_unbekannter_code_und_klartext(self):
		r = terminal.wareneingang_scan(f"(01){_gtin('0200000000999')}(10)X1")
		self.assertTrue(r["unbekannt"])
		self.assertEqual(r["charge"], "X1")
		self.assertEqual(terminal.wareneingang_scan("214848")["charge"], "214848")

	def test_ohne_eigenes_etikett_und_backstube_scannt_lieferanten_etikett(self):
		lot = f"HN{_hash()}"
		e = terminal.wareneingang(
			"Lager", "KT-HASELNUSS", self._etikett(lot), 25, add_days(nowdate(), 300), gebinde=2, etiketten=0
		)
		self.assertEqual(e["charge"], lot)  # Charge = Lieferanten-Charge, keine Zweitnummer
		self.assertEqual(e["gebinde"], [])
		self.assertAlmostEqual(e["menge"], 50)
		r = terminal.aufloesen(self._etikett(lot))
		self.assertEqual((r["typ"], r["charge"], r["artikel"]), ("charge", lot, "KT-HASELNUSS"))
		self.assertAlmostEqual(r["inhalt"], 50)

	def test_mit_etiketten_wie_bisher(self):
		e = terminal.wareneingang(
			"Lager",
			"KT-HASELNUSS",
			f"HNE{_hash()}",
			25,
			add_days(nowdate(), 300),
			gebinde=2,
			gebindeart="Sack",
		)
		self.assertEqual(len(e["gebinde"]), 2)
		self.assertAlmostEqual(e["menge"], 50)

	def test_charge_muss_plausibel_sein(self):
		for text in ("Präsentkarton", "Haselnüsse gehackt", "KT-HASELNUSS", "x"):
			with self.assertRaisesRegex(TerminalFehler, "keine Charge|2 bis 60"):
				terminal.wareneingang("Lager", "KT-HASELNUSS", text, 25, add_days(nowdate(), 300))

	def test_etikett_eines_anderen_artikels(self):
		with self.assertRaisesRegex(TerminalFehler, "gehört zu KT-HASELNUSS"):
			terminal.wareneingang(
				"Lager", "KT-SALZ", self._etikett(f"S{_hash()}"), 25, add_days(nowdate(), 300)
			)

	def test_backstube_nur_ean_oder_nicht_gebucht(self):
		with self.assertRaisesRegex(TerminalFehler, "ohne Charge"):
			terminal.aufloesen(self.ean_ohne_charge)
		with self.assertRaisesRegex(TerminalFehler, "nicht im Wareneingang"):
			terminal.aufloesen(self._etikett(f"NIE{_hash()}"))

	def test_eigenes_karton_etikett_findet_das_los(self):
		"""Unsere Fertigware: (01) Karton-GTIN, (10) Los, (15) MHD -> unsere Charge mit Bestand."""
		los = f"9{frappe.generate_hash(length=6)}"
		charge = demo.neue_charge("KT-FW-KAKAO-NOUGAT", f"KT-FW-KAKAO-NOUGAT-T-{_hash()}", nowdate())
		mhd = add_days(nowdate(), 200)
		frappe.db.set_value("Batch", charge, {"kt_los": los, "expiry_date": mhd})
		demo.buchen(
			self.ctx,
			"Material Receipt",
			nowdate(),
			"05:00:00",
			ausgaenge=[("KT-FW-KAKAO-NOUGAT", charge, 24)],
		)
		# Karton-GTIN aus demo.VERPACKUNG (2000000000046) als GTIN-14
		code = f"(01)02000000000046(10){los}(15){getdate(mhd).strftime('%y%m%d')}"
		self.assertEqual(terminal.aufloesen(code)["charge"], charge)
