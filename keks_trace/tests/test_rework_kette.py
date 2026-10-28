"""Abnahmetests: echter Ablauf mit Grundteig, Veredelung, Füllungen, loser Ware, Rework und Behältern.

Ausführen:
	bench --site <site> set-config allow_tests true
	bench --site <site> run-tests --module keks_trace.tests.test_rework_kette

Die Tests legen eigene Chargen und Behälter an und rollen am Ende alles zurück.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate

from keks_trace import demo
from keks_trace.trace import rueckverfolgung


def _hash():
	return frappe.generate_hash(length=6).upper()


class TestReworkKette(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = demo.stammdaten()
		cls.k = demo.drei_tage_kette(cls.ctx, kuerzel="T" + _hash())

	# ------------------------------------------------------------------ Hilfen

	def _grundteig(self, datum, zeit, rework=(), gesamt=100, traeger=None, roh=None, submit=True):
		"""Grundteig aus Mehl/Zucker/Butter (60/20/20) plus Rework."""
		roh = roh or {"KT-MEHL": self.k.mehl, "KT-ZUCKER": self.k.zucker, "KT-BUTTER": self.k.butter}
		rest = gesamt - sum(r[2] for r in rework)
		charge = demo.neue_charge("KT-GT-MUERBE", f"XGT-{_hash()}", datum)
		aus = ("KT-GT-MUERBE", charge, gesamt, traeger) if traeger else ("KT-GT-MUERBE", charge, gesamt)
		se = demo.buchen(
			self.ctx,
			"Manufacture",
			datum,
			zeit,
			eingaenge=[
				("KT-MEHL", roh["KT-MEHL"], rest * 0.6),
				("KT-ZUCKER", roh["KT-ZUCKER"], rest * 0.2),
				("KT-BUTTER", roh["KT-BUTTER"], rest * 0.2),
				*rework,
			],
			ausgaenge=[aus],
			submit=submit,
		)
		return charge, se

	def _nussteig(self, datum, zeit, grundteig, menge_gt, rework=(), gt_traeger=None):
		nuss = 10
		charge = demo.neue_charge("KT-TV-NUSS", f"XTV-{_hash()}", datum)
		gt = (
			("KT-GT-MUERBE", grundteig, menge_gt, gt_traeger)
			if gt_traeger
			else ("KT-GT-MUERBE", grundteig, menge_gt)
		)
		gesamt = menge_gt + nuss + sum(r[2] for r in rework)
		se = demo.buchen(
			self.ctx,
			"Manufacture",
			datum,
			zeit,
			eingaenge=[gt, ("KT-HASELNUSS", self.k.nuss, nuss), *rework],
			ausgaenge=[("KT-TV-NUSS", charge, gesamt)],
		)
		return charge, se

	def _rework(self, quelle, rw_item, datum, zeit, menge):
		"""quelle: (Artikel, Charge) oder (Artikel, Charge, Behälter)."""
		charge = demo.neue_charge(rw_item, f"XRW-{_hash()}", datum)
		demo.buchen(
			self.ctx,
			"Repack",
			datum,
			zeit,
			eingaenge=[(quelle[0], quelle[1], menge, *quelle[2:])],
			ausgaenge=[(rw_item, charge, menge)],
		)
		return charge

	def _alte_kette(self):
		"""Grundteig und Teigrest-Rework, 15 Tage vor Tag 1 (für Ablauftests)."""
		alt = getdate(add_days(self.k.tag1, -15))
		h = _hash()
		roh = {
			"KT-MEHL": demo.neue_charge("KT-MEHL", f"XAM-{h}", add_days(alt, -2), self.ctx.lieferant),
			"KT-ZUCKER": demo.neue_charge("KT-ZUCKER", f"XAZ-{h}", add_days(alt, -2), self.ctx.lieferant),
			"KT-BUTTER": demo.neue_charge("KT-BUTTER", f"XAB-{h}", add_days(alt, -2), self.ctx.lieferant),
		}
		demo.buchen(
			self.ctx, "Material Receipt", alt, "06:00:00", ausgaenge=[(i, c, 100) for i, c in roh.items()]
		)
		gt, _se = self._grundteig(alt, "07:00:00", roh=roh)
		rw = self._rework(("KT-GT-MUERBE", gt), "KT-RW-MUERBE", alt, "08:00:00", 5)
		return alt, gt, rw

	# ------------------------------------------------------------------ Rework und Allergene

	def test_t06_nuss_rework_in_grundteig_ohne_regel_blockiert(self):
		rn = self._rework(("KT-BW-NUSS", self.k.bw2), "KT-RW-NUSS", self.k.tag3, "12:00:00", 2)
		with self.assertRaisesRegex(frappe.ValidationError, "nicht zugelassen"):
			self._grundteig(self.k.tag3, "12:01:00", rework=[("KT-RW-NUSS", rn, 2)])

	def test_t06b_allergenkonflikt_trotz_falscher_regel(self):
		rn = self._rework(("KT-BW-NUSS", self.k.bw2), "KT-RW-NUSS", self.k.tag3, "12:05:00", 2)
		regel = frappe.get_doc(
			{
				"doctype": "Rework Regel",
				"rework_artikel": "KT-RW-NUSS",
				"ziel_artikel": "KT-GT-MUERBE",
				"max_anteil_prozent": 10,
			}
		).insert()
		try:
			with self.assertRaisesRegex(frappe.ValidationError, "Haselnuss"):
				self._grundteig(self.k.tag3, "12:06:00", rework=[("KT-RW-NUSS", rn, 2)])
		finally:
			regel.delete()

	def test_t06c_schokolierter_bruch_bringt_soja_in_nussteig(self):
		# Bruch aus der Kiste mit loser schokolierter Ware
		rs = self._rework(
			("KT-WL-NUSS-SCHOKO", self.k.wl1, self.k.kl1), "KT-RW-SCHOKO", self.k.tag3, "12:10:00", 2
		)
		regel = frappe.get_doc(
			{
				"doctype": "Rework Regel",
				"rework_artikel": "KT-RW-SCHOKO",
				"ziel_artikel": "KT-TV-NUSS",
				"max_anteil_prozent": 10,
			}
		).insert()
		try:
			with self.assertRaisesRegex(frappe.ValidationError, "Soja"):
				self._nussteig(self.k.tag3, "12:11:00", self.k.gt3, 40, rework=[("KT-RW-SCHOKO", rs, 2)])
		finally:
			regel.delete()

	def test_t06d_teigrest_rework_in_veredelten_teig_erlaubt(self):
		rm = self._rework(("KT-GT-MUERBE", self.k.gt3), "KT-RW-MUERBE", self.k.tag3, "12:20:00", 5)
		_c, se = self._nussteig(self.k.tag3, "12:21:00", self.k.gt3, 40, rework=[("KT-RW-MUERBE", rm, 4)])
		self.assertEqual(se.docstatus, 1)

	def test_t07_rework_anteil_ueber_maximum_blockiert(self):
		rm = self._rework(("KT-GT-MUERBE", self.k.gt3), "KT-RW-MUERBE", self.k.tag3, "12:30:00", 20)
		with self.assertRaisesRegex(frappe.ValidationError, "höchstens 10.0 kg"):
			self._grundteig(self.k.tag3, "12:31:00", rework=[("KT-RW-MUERBE", rm, 20)])

	def test_t08_abgelaufenes_rework_blockiert(self):
		alt, _gt, rw = self._alte_kette()
		self.assertEqual(getdate(frappe.db.get_value("Batch", rw, "expiry_date")), getdate(add_days(alt, 7)))
		with self.assertRaisesRegex(frappe.ValidationError, "Rework-Charge .* ist abgelaufen"):
			self._grundteig(self.k.tag3, "12:40:00", rework=[("KT-RW-MUERBE", rw, 5)])

	def test_t08b_grundteig_ueber_standzeit_blockiert(self):
		_alt, gt, _rw = self._alte_kette()
		with self.assertRaisesRegex(frappe.ValidationError, "Grundteig .* ist abgelaufen"):
			self._nussteig(self.k.tag3, "12:45:00", gt, 50)

	def test_t09_fifo_hinweis_bei_juengerem_rework(self):
		alt = self._rework(("KT-GT-MUERBE", self.k.gt3), "KT-RW-MUERBE", self.k.tag3, "12:50:00", 5)
		frisch, _se = self._grundteig(self.k.tag3, "12:51:00")
		neu = self._rework(("KT-GT-MUERBE", frisch), "KT-RW-MUERBE", self.k.tag3, "12:52:00", 5)
		self.assertLess(
			getdate(frappe.db.get_value("Batch", alt, "manufacturing_date")),
			getdate(frappe.db.get_value("Batch", neu, "manufacturing_date")),
		)
		_c, se = self._grundteig(self.k.tag3, "12:53:00", rework=[("KT-RW-MUERBE", neu, 5)])
		self.assertEqual(se.docstatus, 1, "FIFO ist nur ein Hinweis und blockiert nicht")
		self.assertTrue(any(alt in w for w in (se.flags.kt_fifo_warnungen or [])))

	def test_rework_alter_zaehlt_ab_aeltestem_tag_der_kette(self):
		# R2 (Teigrest von GT2, Tag 2) steckt in GT3 (Tag 3): GT3 trägt Ursprung Tag 2.
		self.assertEqual(getdate(frappe.db.get_value("Batch", self.k.gt3, "kt_ursprungsdatum")), self.k.tag2)
		herstell, verfall = frappe.db.get_value("Batch", self.k.r2, ["manufacturing_date", "expiry_date"])
		self.assertEqual(getdate(herstell), self.k.tag2)
		self.assertEqual(getdate(verfall), getdate(add_days(self.k.tag2, 7)))
		# Rework R1 (Bruch von Backware Tag 1)
		self.assertEqual(getdate(frappe.db.get_value("Batch", self.k.r1, "manufacturing_date")), self.k.tag1)

	# ------------------------------------------------------------------ MHD

	def test_t10_mhd_ab_backtag_nicht_ab_verpackungstag(self):
		mhd, backtag = frappe.db.get_value("Batch", self.k.l1, ["expiry_date", "kt_backtag"])
		self.assertEqual(getdate(backtag), self.k.tag1)
		self.assertEqual(getdate(mhd), getdate(add_days(self.k.tag1, 270)))

	def test_t10b_mhd_durch_selbst_gemachte_fuellung_begrenzt(self):
		nougat_mhd = getdate(frappe.db.get_value("Batch", self.k.nougat, "expiry_date"))
		self.assertEqual(nougat_mhd, getdate(add_days(self.k.tag1, 30)))
		self.assertEqual(getdate(frappe.db.get_value("Batch", self.k.wl3, "kt_komponenten_mhd")), nougat_mhd)
		mhd = getdate(frappe.db.get_value("Batch", self.k.l2, "expiry_date"))
		self.assertEqual(mhd, nougat_mhd)
		self.assertLess(mhd, getdate(add_days(self.k.tag2, 270)))

	# ------------------------------------------------------------------ Rückverfolgung

	def test_t11_grundteig_auf_zwei_veredelungen_an_zwei_tagen(self):
		r = rueckverfolgung(self.k.gt1, "Vorwärts")
		gefunden = {z["charge"]: z for z in r["chargen"]}
		self.assertIn(self.k.v1, gefunden)
		self.assertIn(self.k.v2, gefunden)
		self.assertEqual(getdate(gefunden[self.k.v1]["herstelldatum"]), self.k.tag1)
		self.assertEqual(getdate(gefunden[self.k.v2]["herstelldatum"]), self.k.tag2)

	def test_t13_rueckruf_mehl_vorwaerts_bis_zum_kunden(self):
		r = rueckverfolgung(self.k.mehl, "Vorwärts")
		gefunden = {z["charge"]: z for z in r["chargen"]}
		k = self.k
		for charge in (
			k.gt1,
			k.gt2,
			k.gt3,
			k.v1,
			k.v2,
			k.v3,
			k.bw1,
			k.bw2,
			k.bw3,
			k.wl1,
			k.wl2,
			k.wl3,
			k.r1,
			k.r2,
			k.l1,
			k.l2,
		):
			self.assertIn(charge, gefunden)
		self.assertNotIn(k.nougat, gefunden, "Nougat enthält kein Mehl")
		# V2: 50 kg GT1 (60 % Mehl) + 2 kg R1 (50 % Mehl) in 61 kg
		self.assertAlmostEqual(gefunden[k.v2]["anteil"], (50 * 0.6 + 2 * 0.5) / 61, places=5)
		gelieferte = {kd.charge for kd in r["kunden"]}
		self.assertEqual(gelieferte, {k.l1, k.l2})

	def test_t14_reklamation_rueckwaerts_bis_zu_fuellung_und_lieferant(self):
		k = self.k
		r = rueckverfolgung(k.l2, "Rückwärts")
		gefunden = {z["charge"] for z in r["chargen"]}
		for charge in (k.wl3, k.nougat, k.bw3, k.v3, k.gt2, k.mehl, k.kakao, k.nuss, k.folie):
			self.assertIn(charge, gefunden)
		self.assertNotIn(k.schoko, gefunden)

		r = rueckverfolgung(k.v2, "Rückwärts")
		gefunden = {z["charge"] for z in r["chargen"]}
		for charge in (k.r1, k.bw1, k.v1, k.gt1):
			self.assertIn(charge, gefunden, "Rückwärts über Rework bis zum Grundteig vom Vortag")

	def test_t15_storno_entfernt_kanten_und_leert_behaelter(self):
		tb = demo.neuer_traeger(f"XTB-{_hash()}", "Teigbehälter")
		charge, se = self._grundteig(self.k.tag3, "13:00:00", traeger=tb)
		self.assertEqual(frappe.db.get_value("Produkttraeger", tb, "status"), "Belegt")
		self.assertIn(charge, [z["charge"] for z in rueckverfolgung(self.k.mehl, "Vorwärts")["chargen"]])
		se.cancel()
		self.assertNotIn(charge, [z["charge"] for z in rueckverfolgung(self.k.mehl, "Vorwärts")["chargen"]])
		self.assertTrue(frappe.db.exists("Chargen Genealogie", {"stock_entry": se.name, "storniert": 1}))
		self.assertEqual(frappe.db.get_value("Produkttraeger", tb, "status"), "Frei")

	# ------------------------------------------------------------------ Behälter

	def test_t16_belegter_behaelter_kann_nicht_neu_befuellt_werden(self):
		tb = demo.neuer_traeger(f"XTB-{_hash()}", "Teigbehälter")
		self._grundteig(self.k.tag3, "13:10:00", traeger=tb)
		with self.assertRaisesRegex(frappe.ValidationError, "enthält noch Charge"):
			self._grundteig(self.k.tag3, "13:11:00", traeger=tb)

	def test_t16b_falscher_behaelter_gescannt(self):
		tb = demo.neuer_traeger(f"XTB-{_hash()}", "Teigbehälter")
		self._grundteig(self.k.tag3, "13:20:00", traeger=tb)
		anderer, _se = self._grundteig(self.k.tag3, "13:21:00")
		with self.assertRaisesRegex(frappe.ValidationError, "gescannt wurde Charge"):
			self._nussteig(self.k.tag3, "13:22:00", anderer, 50, gt_traeger=tb)

	def test_t16c_mehr_entnommen_als_im_behaelter(self):
		tb = demo.neuer_traeger(f"XTB-{_hash()}", "Teigbehälter")
		gt, _se = self._grundteig(self.k.tag3, "13:30:00", traeger=tb, gesamt=40)
		with self.assertRaisesRegex(frappe.ValidationError, "enthält nur"):
			self._nussteig(self.k.tag3, "13:31:00", gt, 60, gt_traeger=tb)

	def test_t16d_teilentnahme_und_leeren(self):
		k = self.k
		self.assertEqual(
			frappe.db.get_value("Produkttraeger", k.tb1, "status"), "Frei", "GT1 über zwei Tage aufgebraucht"
		)
		kiste = frappe.db.get_value("Produkttraeger", k.kl1, ["status", "charge", "menge"], as_dict=True)
		self.assertEqual(
			(kiste.status, kiste.charge), ("Belegt", k.wl1), "Rest loser Ware bleibt in der Kiste"
		)
		self.assertGreater(kiste.menge, 0)
		bel = frappe.get_all("Traeger Belegung", filters={"traeger": k.tb1}, fields=["charge", "offen"])
		self.assertEqual([(b.charge, b.offen) for b in bel], [(k.gt1, 0)])

	def test_t16e_behaelter_in_reinigung_nicht_befuellbar(self):
		tb = demo.neuer_traeger(f"XTB-{_hash()}", "Teigbehälter")
		t = frappe.get_doc("Produkttraeger", tb)
		t.status = "Reinigung"
		t.save()
		with self.assertRaisesRegex(frappe.ValidationError, "nicht befüllt werden"):
			self._grundteig(self.k.tag3, "13:40:00", traeger=tb)
