"""Bio (EU-Öko) und V-Label: Wareneingang, Zutatenprüfung, Kennzeichen der Charge, Umstellung, Abgleich."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from keks_trace import demo, kennzeichnung, pruefung, terminal
from keks_trace.kennzeichnung import KennzeichenFehler


def _hash():
	return frappe.generate_hash(length=5).upper()


class TestBio(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = demo.stammdaten()
		cls.h = _hash()
		cls.bio_lieferant = demo.BIO_LIEFERANT[0]
		mhd = add_days(nowdate(), 200)
		cls.dinkel = terminal.wareneingang(
			"Lager", "KT-BIO-DINKEL", f"BD{cls.h}", 1000, mhd, lieferant=cls.bio_lieferant
		)["charge"]
		cls.zucker = terminal.wareneingang(
			"Lager", "KT-BIO-ZUCKER", f"BZ{cls.h}", 500, mhd, lieferant=cls.bio_lieferant
		)["charge"]
		cls.salz = terminal.wareneingang("Lager", "KT-SALZ", f"SA{cls.h}", 100)["charge"]
		cls.konv_zucker = terminal.wareneingang("Lager", "KT-ZUCKER", f"KZ{cls.h}", 100, mhd)["charge"]

	def _zeilen(self, zucker=None):
		return [
			{"code": self.dinkel, "menge": 70},
			{"code": zucker or self.zucker, "menge": 25},
			{"code": self.salz, "menge": 5},
		]

	def _konventionell_backen(self):
		"""Eine konventionelle Fertigung an der Backstube (Zuckersirup aus konventionellem Zucker)."""
		return terminal.herstellen(
			"Backstube", "KT-SIRUP", [{"code": self.konv_zucker, "menge": 6}], 10,
			pruefwerte={"Brix Invertzuckersirup": {"wert": 82}},
		)  # fmt: skip

	def test_01_wareneingang_nur_mit_zertifikat(self):
		self.assertEqual(
			frappe.db.get_value("Batch", self.dinkel, "kt_kennzeichen"), "Bio, Vegan, Vegetarisch"
		)
		self.assertEqual(frappe.db.get_value("Batch", self.salz, "kt_kennzeichen"), "Vegan, Vegetarisch")
		with self.assertRaisesRegex(KennzeichenFehler, "kein Lieferant"):
			terminal.wareneingang("Lager", "KT-BIO-DINKEL", f"X{_hash()}", 10, add_days(nowdate(), 100))
		with self.assertRaisesRegex(KennzeichenFehler, "kein Öko-Zertifikat"):
			terminal.wareneingang(
				"Lager",
				"KT-BIO-DINKEL",
				f"X{_hash()}",
				10,
				add_days(nowdate(), 100),
				lieferant=self.ctx.lieferant,
			)
		frappe.db.set_value("Supplier", self.bio_lieferant, "kt_bio_gueltig_bis", add_days(nowdate(), -1))
		try:
			with self.assertRaisesRegex(KennzeichenFehler, "abgelaufen"):
				terminal.wareneingang(
					"Lager", "KT-BIO-DINKEL", f"X{_hash()}", 10, add_days(nowdate(), 100),
					lieferant=self.bio_lieferant,
				)  # fmt: skip
		finally:
			frappe.db.set_value(
				"Supplier", self.bio_lieferant, "kt_bio_gueltig_bis", add_days(nowdate(), 365)
			)
		# Terminal: Bio-Artikel bietet nur zertifizierte Lieferanten an
		art = next(a for a in terminal.wareneingang_artikel() if a["artikel"] == "KT-BIO-DINKEL")
		self.assertTrue(art["bio"])
		self.assertEqual({x["lieferant"] for x in art["lieferanten"]} & {self.ctx.lieferant}, set())
		self.assertIn(self.bio_lieferant, {x["lieferant"] for x in art["lieferanten"]})
		# Büro: Wareneingang über ERPNext prüft dasselbe
		with self.assertRaisesRegex(KennzeichenFehler, "Öko-Zertifikat"):
			kennzeichnung.pruefe_einkauf(
				frappe._dict(supplier=self.ctx.lieferant, items=[frappe._dict(item_code="KT-BIO-ZUCKER")])
			)

	def test_02_zutat_ohne_kennzeichen_wird_abgewiesen(self):
		self.assertEqual(terminal.pruefe_zeile("Backstube", "KT-BIO-GT", self.salz, 5)["artikel"], "KT-SALZ")
		# Salz nicht als „in Bio erlaubt“ markiert: Bio-Teig nimmt es nicht
		frappe.db.set_value("Item", "KT-SALZ", "kt_bio_erlaubt", 0)
		try:
			with self.assertRaisesRegex(KennzeichenFehler, "nicht Bio"):
				terminal.pruefe_zeile("Backstube", "KT-BIO-GT", self.salz, 5)
			with self.assertRaisesRegex(KennzeichenFehler, "nicht Bio"):
				terminal.herstellen(
					"Backstube", "KT-BIO-GT", self._zeilen(), pruefwerte={"Reinigung vor Bio": {"ok": True}}
				)
		finally:
			frappe.db.set_value("Item", "KT-SALZ", "kt_bio_erlaubt", 1)
		# Salz-Charge nicht vegan (z. B. alte Charge mit Kennzeichen „keine“): vegan verlangt
		frappe.db.set_value("Batch", self.salz, "kt_kennzeichen", "keine")
		try:
			with self.assertRaisesRegex(KennzeichenFehler, "Vegan"):
				terminal.pruefe_zeile("Backstube", "KT-BIO-GT", self.salz, 5)
		finally:
			frappe.db.set_value("Batch", self.salz, "kt_kennzeichen", "Vegan, Vegetarisch")

	def test_03_umstellung_braucht_reinigung(self):
		self._konventionell_backen()
		self.assertFalse(kennzeichnung.letzte_fertigung_bio("Backstube"))
		r = terminal.rezept("KT-BIO-GT", station="Backstube")
		self.assertTrue(r["umstellung_bio"])
		self.assertEqual(r["kennzeichen"], ["Bio", "Vegan", "Vegetarisch"])
		self.assertIn("Reinigung vor Bio", [p["pruefplan"] for p in r["pruefungen"]])
		with self.assertRaisesRegex(pruefung.PruefFehler, "Reinigung vor Bio"):
			terminal.herstellen("Backstube", "KT-BIO-GT", self._zeilen())
		with self.assertRaisesRegex(pruefung.PruefFehler, "Nicht gebucht"):
			terminal.herstellen(
				"Backstube", "KT-BIO-GT", self._zeilen(), pruefwerte={"Reinigung vor Bio": {"ok": False}}
			)
		e = terminal.herstellen(
			"Backstube", "KT-BIO-GT", self._zeilen(), pruefwerte={"Reinigung vor Bio": {"ok": True}}
		)
		self.assertEqual(
			frappe.db.get_value("Batch", e["charge"], "kt_kennzeichen"), "Bio, Vegan, Vegetarisch"
		)
		self.assertTrue(
			frappe.db.exists(
				"Pruefung", {"pruefplan": "Reinigung vor Bio", "charge": e["charge"], "ergebnis": "OK"}
			)
		)
		# Danach läuft Bio, die nächste Bio-Charge braucht keine Reinigung
		self.assertTrue(kennzeichnung.letzte_fertigung_bio("Backstube"))
		self.assertFalse(terminal.rezept("KT-BIO-GT", station="Backstube")["umstellung_bio"])
		e2 = terminal.herstellen("Backstube", "KT-BIO-GT", self._zeilen())
		self.assertIn("Bio", frappe.db.get_value("Batch", e2["charge"], "kt_kennzeichen"))

	def test_04_kennzeichen_aus_den_zutaten(self):
		# Konventioneller Sirup aus konventionellem Zucker: kein Bio
		e = self._konventionell_backen()
		self.assertEqual(frappe.db.get_value("Batch", e["charge"], "kt_kennzeichen"), "keine")
		# nur Bio-erlaubte Zutat reicht nicht für Bio (keine landwirtschaftliche Bio-Zutat)
		self.assertNotIn(kennzeichnung.BIO, kennzeichnung.charge_kennzeichen(self.salz))
		self.assertIn(kennzeichnung.BIO, kennzeichnung.wirksam(self.salz, "KT-SALZ"))

	def test_05_bio_mengenabgleich(self):
		if kennzeichnung.letzte_fertigung_bio("Backstube") is False:
			pw = {"Reinigung vor Bio": {"ok": True}}
		else:
			pw = None
		e = terminal.herstellen("Backstube", "KT-BIO-GT", self._zeilen(), pruefwerte=pw)
		zeilen = {z["artikel"]: z for z in kennzeichnung.bio_abgleich(nowdate(), nowdate())}
		self.assertGreaterEqual(zeilen["KT-BIO-DINKEL"]["wareneingang"], 1000)
		self.assertGreaterEqual(zeilen["KT-BIO-DINKEL"]["verbraucht"], 70)
		self.assertGreaterEqual(zeilen["KT-BIO-GT"]["hergestellt"], e["menge"])
		self.assertNotIn("KT-ZUCKER", zeilen)
		d = zeilen["KT-BIO-DINKEL"]
		self.assertAlmostEqual(
			d["ende"], d["anfang"] + d["wareneingang"] + d["hergestellt"] - d["verbraucht"] - d["ausgeliefert"]
			- d["lagerverkauf"] - d["entsorgt"] + d["sonstiges"], places=3,
		)  # fmt: skip
		from keks_trace.keks_trace.report.bio_mengenabgleich.bio_mengenabgleich import execute

		_spalten, daten, nachricht = execute({"von": nowdate(), "bis": nowdate()})
		self.assertTrue(daten)
		self.assertIn("Bio-Rohware", nachricht)
