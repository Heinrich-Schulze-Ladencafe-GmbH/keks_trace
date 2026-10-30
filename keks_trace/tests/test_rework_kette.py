"""Abnahmetests: echter Ablauf mit Grundteig, Veredelung, Füllungen, loser Ware, Rework und Behältern.

Ausführen:
	bench --site <site> set-config allow_tests true
	bench --site <site> run-tests --module keks_trace.tests.test_rework_kette

Die Tests legen eigene Chargen und Behälter an und rollen am Ende alles zurück.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate

from keks_trace import demo, sperre
from keks_trace.bilanz import mengenbilanz
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

	def _rohstoffe(self, datum, menge=100):
		"""Eigene Rohstoffchargen (Mehl, Zucker, Butter) eingehen lassen; Butter wird von der QS freigegeben."""
		h = _hash()
		roh = {
			"KT-MEHL": demo.neue_charge("KT-MEHL", f"XRM-{h}", add_days(datum, -2), self.ctx.lieferant),
			"KT-ZUCKER": demo.neue_charge("KT-ZUCKER", f"XRZ-{h}", add_days(datum, -2), self.ctx.lieferant),
			"KT-BUTTER": demo.neue_charge("KT-BUTTER", f"XRB-{h}", add_days(datum, -2), self.ctx.lieferant),
		}
		demo.buchen(
			self.ctx, "Material Receipt", datum, "06:00:00", ausgaenge=[(i, c, menge) for i, c in roh.items()]
		)
		sperre.freigeben(roh["KT-BUTTER"], "Wareneingangsprüfung in Ordnung")
		return roh

	def _alte_kette(self):
		"""Grundteig und Teigrest-Rework, 15 Tage vor Tag 1 (für Ablauftests)."""
		alt = getdate(add_days(self.k.tag1, -15))
		roh = self._rohstoffe(alt)
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

	# ------------------------------------------------------------------ Sperren und Freigabe (IFS 5.11)

	def test_t12_nicht_freigegebene_lose_ware_blockiert(self):
		k = self.k
		self.assertEqual(frappe.db.get_value("Batch", k.wl2, "kt_status"), "Gesperrt")
		los = demo.neue_charge("KT-FW-NUSS-SCHOKO", f"XL-{_hash()}", k.tag3)
		packen = dict(
			eingaenge=[("KT-WL-NUSS-SCHOKO", k.wl2, 20, k.kl2), ("KT-FOLIE", k.folie, 0.5)],
			ausgaenge=[("KT-FW-NUSS-SCHOKO", los, 20)],
		)
		with self.assertRaisesRegex(frappe.ValidationError, "ist gesperrt"):
			demo.buchen(self.ctx, "Manufacture", k.tag3, "14:00:00", **packen)
		sperre.freigeben(k.wl2, "Sensorik in Ordnung")
		se = demo.buchen(self.ctx, "Manufacture", k.tag3, "14:01:00", **packen)
		self.assertEqual(se.docstatus, 1)

	def test_t17_wareneingang_gesperrt_bis_freigabe(self):
		butter = demo.neue_charge("KT-BUTTER", f"XBU-{_hash()}", self.k.tag3, self.ctx.lieferant)
		self.assertEqual(frappe.db.get_value("Batch", butter, "kt_status"), "Gesperrt")
		self.assertTrue(frappe.db.exists("Chargen Sperre", {"charge": butter, "aktion": "Sperren"}))
		demo.buchen(
			self.ctx, "Material Receipt", self.k.tag3, "06:30:00", ausgaenge=[("KT-BUTTER", butter, 50)]
		)
		roh = {"KT-MEHL": self.k.mehl, "KT-ZUCKER": self.k.zucker, "KT-BUTTER": butter}
		with self.assertRaisesRegex(frappe.ValidationError, "ist gesperrt"):
			self._grundteig(self.k.tag3, "14:10:00", roh=roh)
		sperre.freigeben(butter, "Temperatur 4 °C")
		_c, se = self._grundteig(self.k.tag3, "14:11:00", roh=roh)
		self.assertEqual(se.docstatus, 1)
		self.assertTrue(frappe.db.exists("Chargen Sperre", {"charge": butter, "aktion": "Freigeben"}))

	def test_t18_rueckrufsperre_sperrt_alle_betroffenen_chargen(self):
		tag = self.k.tag3
		roh = self._rohstoffe(tag)
		gt, _se = self._grundteig(tag, "15:00:00", roh=roh)
		tv, _se = self._nussteig(tag, "15:01:00", gt, 50)
		rw = self._rework(("KT-GT-MUERBE", gt), "KT-RW-MUERBE", tag, "15:02:00", 5)

		r = sperre.rueckruf_sperre(roh["KT-MEHL"], "Fremdkörper beim Lieferanten gemeldet")
		gesperrt = {c["charge"] for c in r["chargen"]}
		self.assertEqual(gesperrt, {roh["KT-MEHL"], gt, tv, rw})
		for c in gesperrt:
			self.assertEqual(frappe.db.get_value("Batch", c, "kt_status"), "Gesperrt")
			self.assertTrue(frappe.db.exists("Chargen Sperre", {"charge": c, "vorgang": r["vorgang"]}))
		self.assertTrue(frappe.db.exists("Chargen Sperre", {"charge": roh["KT-ZUCKER"]}) is None)
		with self.assertRaisesRegex(frappe.ValidationError, "ist gesperrt"):
			self._nussteig(tag, "15:05:00", gt, 20)

	def test_t18b_gesperrtes_los_kann_nicht_ausgeliefert_werden(self):
		k = self.k
		sperre.sperren(k.l1, "Etikett fehlerhaft")
		with self.assertRaisesRegex(frappe.ValidationError, "ist gesperrt"):
			demo.liefern(self.ctx, k.tag3, [("KT-FW-NUSS-SCHOKO", k.l1, 5)])
		sperre.freigeben(k.l1, "Etikett korrigiert")
		self.assertEqual(demo.liefern(self.ctx, k.tag3, [("KT-FW-NUSS-SCHOKO", k.l1, 5)]).docstatus, 1)

	def test_t19_nur_qs_darf_sperren_und_mhd_aendern(self):
		email = "kt-lager-test@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "Lager",
					"send_welcome_email": 0,
					"roles": [{"role": "Stock User"}],
				}
			).insert(ignore_permissions=True)
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				sperre.freigeben(self.k.wl2, "darf ich nicht")
			b = frappe.get_doc("Batch", self.k.gt3)
			b.expiry_date = add_days(b.expiry_date, 30)
			b.flags.ignore_permissions = True
			with self.assertRaisesRegex(frappe.PermissionError, "Nur die QS"):
				b.save()
		finally:
			frappe.set_user("Administrator")

	# ------------------------------------------------------------------ Unveränderbarkeit (IFS 2.1.2.1)

	def test_t20_protokolle_nicht_aenderbar_und_nicht_loeschbar(self):
		kante = frappe.get_doc("Chargen Genealogie", {"output_batch": self.k.v2, "input_batch": self.k.r1})
		kante.menge = 0
		with self.assertRaisesRegex(frappe.ValidationError, "kann nicht geändert werden"):
			kante.save(ignore_permissions=True)
		with self.assertRaisesRegex(frappe.ValidationError, "kann nicht gelöscht werden"):
			frappe.delete_doc("Chargen Genealogie", kante.name, ignore_permissions=True)
		eintrag = frappe.get_last_doc("Chargen Sperre", filters={"charge": self.k.wl1})
		with self.assertRaisesRegex(frappe.ValidationError, "kann nicht gelöscht werden"):
			frappe.delete_doc("Chargen Sperre", eintrag.name, ignore_permissions=True)
		belegung = frappe.get_last_doc("Traeger Belegung", filters={"traeger": self.k.tb1})
		with self.assertRaisesRegex(frappe.ValidationError, "kann nicht gelöscht werden"):
			frappe.delete_doc("Traeger Belegung", belegung.name, ignore_permissions=True)

	def test_t21_gebuchte_und_stornierte_belege_nicht_loeschbar(self):
		_c, se = self._grundteig(self.k.tag3, "16:00:00")
		with self.assertRaises(frappe.ValidationError):  # gebucht: sperrt schon Frappe selbst
			frappe.delete_doc("Stock Entry", se.name, ignore_permissions=True)
		se.cancel()  # storniert: Frappe würde das Löschen erlauben, keks_trace verbietet es
		with self.assertRaisesRegex(frappe.ValidationError, "nicht gelöscht"):
			frappe.delete_doc("Stock Entry", se.name, ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("Batch", self.k.gt1, ignore_permissions=True)
		self.assertTrue(frappe.db.exists("Batch", self.k.gt1))

	def test_t22_sperrstatus_nicht_von_hand_aenderbar(self):
		b = frappe.get_doc("Batch", self.k.wl2)
		b.kt_status = "Freigegeben" if b.kt_status == "Gesperrt" else "Gesperrt"
		with self.assertRaisesRegex(frappe.ValidationError, "vom System gesetzt"):
			b.save(ignore_permissions=True)

	# ------------------------------------------------------------------ Vollständigkeit

	def test_t23_fehlende_rezeptzutat(self):
		def ohne_zucker(zeit):
			charge = demo.neue_charge("KT-GT-MUERBE", f"XVZ-{_hash()}", self.k.tag3)
			return demo.buchen(
				self.ctx,
				"Manufacture",
				self.k.tag3,
				zeit,
				eingaenge=[("KT-MEHL", self.k.mehl, 70), ("KT-BUTTER", self.k.butter, 30)],
				ausgaenge=[("KT-GT-MUERBE", charge, 100)],
			)

		frappe.db.set_single_value("Keks Trace Einstellungen", "vollstaendigkeit", "Warnen")
		se = ohne_zucker("16:10:00")
		self.assertEqual(se.docstatus, 1)
		self.assertEqual(se.flags.kt_fehlende_zutaten, ["KT-ZUCKER"])
		frappe.db.set_single_value("Keks Trace Einstellungen", "vollstaendigkeit", "Blockieren")
		try:
			with self.assertRaisesRegex(frappe.ValidationError, "KT-ZUCKER"):
				ohne_zucker("16:11:00")
		finally:
			frappe.db.set_single_value("Keks Trace Einstellungen", "vollstaendigkeit", "Warnen")

	# ------------------------------------------------------------------ Mengenbilanz und Test (IFS 4.18.2)

	def test_t24_mengenbilanz_rohstoff(self):
		tag = self.k.tag3
		roh = self._rohstoffe(tag)
		self._grundteig(tag, "17:00:00", roh=roh)
		demo.buchen(self.ctx, "Material Issue", tag, "17:01:00", eingaenge=[("KT-MEHL", roh["KT-MEHL"], 3)])
		b = mengenbilanz(roh["KT-MEHL"])
		self.assertEqual(b["zugang"], 100)
		self.assertEqual(b["summen"]["Verbraucht in Produktion"], -60)
		self.assertEqual(b["summen"]["Ausgebucht / entsorgt"], -3)
		self.assertEqual(b["bestand"], 37)
		self.assertEqual(b["differenz_lager"], 0)
		self.assertEqual(b["differenz_genealogie"], 0)
		self.assertTrue(b["ok"])

		b = mengenbilanz(self.k.bw1)
		self.assertEqual(b["summen"]["Zu Rework umgefüllt"], -2)
		self.assertAlmostEqual(b["ausbeute_prozent"], 83.3, places=1)
		self.assertTrue(b["ok"])

	def test_t25_mengenbilanz_erkennt_luecke(self):
		tag = self.k.tag3
		roh = self._rohstoffe(tag)
		gt, se = self._grundteig(tag, "17:10:00", roh=roh)
		# Manipulation simulieren: Verbrauch steht im Lager, aber die Kante fehlt
		frappe.db.set_value(
			"Chargen Genealogie", {"stock_entry": se.name, "input_batch": roh["KT-ZUCKER"]}, "storniert", 1
		)
		b = mengenbilanz(roh["KT-ZUCKER"])
		self.assertFalse(b["ok"])
		self.assertEqual(b["differenz_genealogie"], 20)
		test = frappe.get_doc({"doctype": "Rueckverfolgungstest", "charge": gt, "anlass": "Audit"}).insert()
		self.assertEqual(
			test.ergebnis, "Bestanden", "Rückwärts fehlt der Zucker; die Bilanz des Grundteigs selbst stimmt"
		)
		test = frappe.get_doc(
			{"doctype": "Rueckverfolgungstest", "charge": roh["KT-ZUCKER"], "anlass": "Audit"}
		).insert()
		self.assertEqual(test.ergebnis, "Abweichung")
		self.assertIn("laut Genealogie", test.bericht)

	def test_t26_rueckverfolgungstest_als_nachweis(self):
		test = frappe.get_doc(
			{"doctype": "Rueckverfolgungstest", "charge": self.k.mehl, "anlass": "Jährlicher Test"}
		).insert()
		self.assertEqual(test.ergebnis, "Bestanden")
		self.assertGreater(test.anzahl_vorwaerts, 10)
		self.assertGreaterEqual(test.anzahl_kunden, 1)
		self.assertGreater(test.dauer_sekunden, 0)
		self.assertIn(self.k.l1, test.bericht)
		test.submit()
		test.reload()
		test.bericht = "geändert"
		with self.assertRaises(frappe.UpdateAfterSubmitError):
			test.save()
