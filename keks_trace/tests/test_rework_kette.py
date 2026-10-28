"""Abnahmetests für den Rework-Prototyp (Testszenarien aus dem Konzept).

Ausführen:
	bench --site <site> run-tests --app keks_trace

Die Tests legen eigene Chargen an und rollen am Ende alles zurück.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, nowdate

from keks_trace import demo
from keks_trace.trace import rueckverfolgung


class TestReworkKette(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = demo.stammdaten()
		cls.k = demo.drei_tage_kette(cls.ctx, kuerzel="TEST" + frappe.generate_hash(length=5).upper())
		cls.heute = getdate(nowdate())

	# ------------------------------------------------------------------ Hilfen

	def _teig(self, item, charge_id, datum, zeit, rework=(), gesamt=100, submit=True):
		"""Teig aus Mehl/Zucker/Butter plus Rework buchen. Rohstoffe füllen auf 'gesamt' auf."""
		rw = sum(m for _i, _c, m in rework)
		rest = gesamt - rw
		charge = demo.neue_charge(item, charge_id, datum)
		return charge, demo.buchen(
			self.ctx,
			"Manufacture",
			datum,
			zeit,
			eingaenge=[
				("KT-MEHL", self.k.mehl, rest * 0.5),
				("KT-ZUCKER", self.k.zucker, rest * 0.2),
				("KT-BUTTER", self.k.butter, rest * 0.3),
				*rework,
			],
			ausgaenge=[(item, charge, gesamt)],
			submit=submit,
		)

	def _rework_aus(self, back_item, back_charge, rw_item, charge_id, datum, zeit, menge):
		charge = demo.neue_charge(rw_item, charge_id, datum)
		demo.buchen(
			self.ctx,
			"Repack",
			datum,
			zeit,
			eingaenge=[(back_item, back_charge, menge)],
			ausgaenge=[(rw_item, charge, menge)],
		)
		return charge

	def _nuss_rework(self, datum):
		"""Nussteig -> Nusskeks lose -> Rework Nuss (für die Allergentests)."""
		suffix = frappe.generate_hash(length=6)
		nuss = demo.neue_charge("KT-HASELNUSS", f"HN-{suffix}", add_days(datum, -5), self.ctx.lieferant)
		demo.buchen(self.ctx, "Material Receipt", datum, "05:00:00", ausgaenge=[("KT-HASELNUSS", nuss, 50)])
		teig = demo.neue_charge("KT-TEIG-NUSS", f"TN-{suffix}", datum)
		demo.buchen(
			self.ctx,
			"Manufacture",
			datum,
			"05:10:00",
			eingaenge=[
				("KT-MEHL", self.k.mehl, 40),
				("KT-ZUCKER", self.k.zucker, 20),
				("KT-BUTTER", self.k.butter, 20),
				("KT-HASELNUSS", nuss, 20),
			],
			ausgaenge=[("KT-TEIG-NUSS", teig, 100)],
		)
		back = demo.neue_charge("KT-BACK-NUSS", f"BN-{suffix}", datum)
		demo.buchen(
			self.ctx,
			"Manufacture",
			datum,
			"05:20:00",
			eingaenge=[("KT-TEIG-NUSS", teig, 100)],
			ausgaenge=[("KT-BACK-NUSS", back, 85)],
		)
		return self._rework_aus("KT-BACK-NUSS", back, "KT-RW-NUSS", f"RN-{suffix}", datum, "05:30:00", 10)

	# ------------------------------------------------------------------ Tests

	def test_t06_nuss_rework_in_butterteig_ohne_regel_blockiert(self):
		rn = self._nuss_rework(self.k.tag3)
		with self.assertRaisesRegex(frappe.ValidationError, "nicht zugelassen"):
			self._teig(
				"KT-TEIG-BUTTER",
				f"X06-{self.k.kuerzel}",
				self.k.tag3,
				"15:00:00",
				rework=[("KT-RW-NUSS", rn, 5)],
			)

	def test_t06b_allergenkonflikt_trotz_falscher_regel(self):
		rn = self._nuss_rework(self.k.tag3)
		regel = frappe.get_doc(
			{
				"doctype": "Rework Regel",
				"rework_artikel": "KT-RW-NUSS",
				"ziel_artikel": "KT-TEIG-BUTTER",
				"max_anteil_prozent": 10,
			}
		).insert()
		try:
			with self.assertRaisesRegex(frappe.ValidationError, "Haselnuss"):
				self._teig(
					"KT-TEIG-BUTTER",
					f"X06B-{self.k.kuerzel}",
					self.k.tag3,
					"15:05:00",
					rework=[("KT-RW-NUSS", rn, 5)],
				)
		finally:
			regel.delete()

	def test_t06c_butter_rework_in_nussteig_erlaubt(self):
		rw = self._rework_aus(
			"KT-BACK-BUTTER",
			self.k.back3,
			"KT-RW-BUTTER",
			f"X06C-RW-{self.k.kuerzel}",
			self.k.tag3,
			"15:10:00",
			5,
		)
		_charge, se = self._teig(
			"KT-TEIG-NUSS",
			f"X06C-{self.k.kuerzel}",
			self.k.tag3,
			"15:11:00",
			rework=[("KT-RW-BUTTER", rw, 5)],
		)
		self.assertEqual(se.docstatus, 1)

	def test_t07_rework_anteil_ueber_maximum_blockiert(self):
		rw = self._rework_aus(
			"KT-BACK-BUTTER",
			self.k.back3,
			"KT-RW-BUTTER",
			f"X07-RW-{self.k.kuerzel}",
			self.k.tag3,
			"15:20:00",
			20,
		)
		with self.assertRaisesRegex(frappe.ValidationError, "höchstens 10.0 kg"):
			self._teig(
				"KT-TEIG-BUTTER",
				f"X07-{self.k.kuerzel}",
				self.k.tag3,
				"15:21:00",
				rework=[("KT-RW-BUTTER", rw, 20)],
			)

	def test_t08_abgelaufenes_rework_blockiert(self):
		alt = add_days(self.k.tag1, -15)
		suffix = frappe.generate_hash(length=6)
		roh = {
			"KT-MEHL": demo.neue_charge("KT-MEHL", f"X08M-{suffix}", add_days(alt, -2), self.ctx.lieferant),
			"KT-ZUCKER": demo.neue_charge(
				"KT-ZUCKER", f"X08Z-{suffix}", add_days(alt, -2), self.ctx.lieferant
			),
			"KT-BUTTER": demo.neue_charge(
				"KT-BUTTER", f"X08B-{suffix}", add_days(alt, -2), self.ctx.lieferant
			),
		}
		demo.buchen(
			self.ctx, "Material Receipt", alt, "06:00:00", ausgaenge=[(i, c, 100) for i, c in roh.items()]
		)
		teig = demo.neue_charge("KT-TEIG-BUTTER", f"X08T-{suffix}", alt)
		demo.buchen(
			self.ctx,
			"Manufacture",
			alt,
			"07:00:00",
			eingaenge=[
				("KT-MEHL", roh["KT-MEHL"], 50),
				("KT-ZUCKER", roh["KT-ZUCKER"], 20),
				("KT-BUTTER", roh["KT-BUTTER"], 30),
			],
			ausgaenge=[("KT-TEIG-BUTTER", teig, 100)],
		)
		back = demo.neue_charge("KT-BACK-BUTTER", f"X08K-{suffix}", alt)
		demo.buchen(
			self.ctx,
			"Manufacture",
			alt,
			"09:00:00",
			eingaenge=[("KT-TEIG-BUTTER", teig, 100)],
			ausgaenge=[("KT-BACK-BUTTER", back, 85)],
		)
		rw = self._rework_aus("KT-BACK-BUTTER", back, "KT-RW-BUTTER", f"X08R-{suffix}", alt, "10:00:00", 5)

		self.assertEqual(getdate(frappe.db.get_value("Batch", rw, "expiry_date")), getdate(add_days(alt, 7)))
		with self.assertRaisesRegex(frappe.ValidationError, "abgelaufen"):
			self._teig(
				"KT-TEIG-BUTTER", f"X08-{suffix}", self.k.tag3, "15:30:00", rework=[("KT-RW-BUTTER", rw, 5)]
			)

	def test_t09_fifo_hinweis_bei_juengerem_rework(self):
		# Älteres Rework aus Backtag 1 bleibt liegen ...
		alt = self._rework_aus(
			"KT-BACK-BUTTER",
			self.k.back1,
			"KT-RW-BUTTER",
			f"X09A-{self.k.kuerzel}",
			self.k.tag3,
			"15:40:00",
			5,
		)
		# ... jüngeres Rework aus einem frischen Teig ohne Rework-Vorgeschichte wird eingesetzt.
		frisch, _se = self._teig("KT-TEIG-BUTTER", f"X09T-{self.k.kuerzel}", self.k.tag3, "15:41:00")
		back = demo.neue_charge("KT-BACK-BUTTER", f"X09K-{self.k.kuerzel}", self.k.tag3)
		demo.buchen(
			self.ctx,
			"Manufacture",
			self.k.tag3,
			"15:42:00",
			eingaenge=[("KT-TEIG-BUTTER", frisch, 100)],
			ausgaenge=[("KT-BACK-BUTTER", back, 85)],
		)
		neu = self._rework_aus(
			"KT-BACK-BUTTER", back, "KT-RW-BUTTER", f"X09N-{self.k.kuerzel}", self.k.tag3, "15:43:00", 5
		)

		_c, se = self._teig(
			"KT-TEIG-BUTTER",
			f"X09-{self.k.kuerzel}",
			self.k.tag3,
			"15:44:00",
			rework=[("KT-RW-BUTTER", neu, 5)],
		)
		self.assertEqual(se.docstatus, 1, "FIFO ist nur ein Hinweis und blockiert nicht")
		self.assertTrue(any(alt in w for w in (se.flags.kt_fifo_warnungen or [])))

	def test_t10_mhd_ab_backtag_nicht_ab_verpackungstag(self):
		mhd = getdate(frappe.db.get_value("Batch", self.k.los1, "expiry_date"))
		self.assertEqual(mhd, getdate(add_days(self.k.tag1, 270)))
		self.assertNotEqual(mhd, getdate(add_days(self.k.tag3, 270)))

	def test_rework_alter_zaehlt_ab_aeltestem_backtag_der_kette(self):
		# R2 entsteht an Tag 2, enthält aber über R1 Ware von Tag 1.
		herstell, ursprung, verfall = frappe.db.get_value(
			"Batch", self.k.rework2, ["manufacturing_date", "kt_ursprungsdatum", "expiry_date"]
		)
		self.assertEqual(getdate(herstell), getdate(self.k.tag1))
		self.assertEqual(getdate(ursprung), getdate(self.k.tag1))
		self.assertEqual(getdate(verfall), getdate(add_days(self.k.tag1, 7)))

	def test_t13_rueckruf_mehl_vorwaerts_bis_zum_kunden(self):
		r = rueckverfolgung(self.k.mehl, "Vorwärts")
		gefunden = {z["charge"]: z for z in r["chargen"]}
		for charge in (
			self.k.teig1,
			self.k.teig2,
			self.k.teig3,
			self.k.back1,
			self.k.back2,
			self.k.back3,
			self.k.rework1,
			self.k.rework2,
			self.k.los1,
		):
			self.assertIn(charge, gefunden)
		# Teig 2: 45 kg Mehl direkt + 5 kg Rework R1, das zu 50 % aus Mehl besteht = 47,5 %
		self.assertAlmostEqual(gefunden[self.k.teig2]["anteil"], 0.475, places=4)
		self.assertIn(self.k.lieferschein, [kd.lieferschein for kd in r["kunden"]])
		self.assertIn(self.ctx.kunde, [kd.kunde for kd in r["kunden"]])

	def test_t14_reklamation_rueckwaerts_ueber_rework_generationen(self):
		r = rueckverfolgung(self.k.teig3, "Rückwärts")
		gefunden = {z["charge"]: z for z in r["chargen"]}
		for charge in (
			self.k.rework2,
			self.k.back2,
			self.k.teig2,
			self.k.rework1,
			self.k.back1,
			self.k.teig1,
			self.k.mehl,
			self.k.zucker,
			self.k.butter,
		):
			self.assertIn(charge, gefunden)
		self.assertAlmostEqual(gefunden[self.k.rework1]["anteil"], 0.0025, places=5)
		self.assertTrue(r["lieferanten"])

		los = rueckverfolgung(self.k.los1, "Rückwärts")
		self.assertIn(
			self.k.folie, [z["charge"] for z in los["chargen"]], "Packmittel gehört zur Rückverfolgung"
		)

	def test_t15_storno_entfernt_kanten_aus_rueckverfolgung(self):
		charge, se = self._teig("KT-TEIG-BUTTER", f"X15-{self.k.kuerzel}", self.k.tag3, "16:30:00")
		self.assertIn(charge, [z["charge"] for z in rueckverfolgung(self.k.mehl, "Vorwärts")["chargen"]])
		se.cancel()
		self.assertNotIn(charge, [z["charge"] for z in rueckverfolgung(self.k.mehl, "Vorwärts")["chargen"]])
		self.assertTrue(
			frappe.db.exists("Chargen Genealogie", {"stock_entry": se.name, "storniert": 1}),
			"Kanten bleiben als storniert erhalten",
		)
