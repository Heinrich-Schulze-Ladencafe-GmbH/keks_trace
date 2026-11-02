"""Druckprotokoll, Akte, „Wo ist dieses Los?“ und „Woraus besteht das?“.

Ausführen:
	bench --site <site> run-tests --module keks_trace.tests.test_akte
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from keks_trace import akte, demo, druckprotokoll, etiketten, palette, sperre, terminal
from keks_trace.tests.test_etiketten import Empfaenger
from keks_trace.utils import regel_nur_hinweis


def _hash():
	return frappe.generate_hash(length=6).upper() + "7"


def _drucke(**filt):
	return frappe.get_all(
		"Etikettendruck",
		filters=filt,
		fields=["grund", "drucker", "bemerkung", "station"],
		order_by="creation asc",
	)


class TestAkte(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.enterClassContext(regel_nur_hinweis("fefo_rohstoffe"))
		cls.ctx = demo.stammdaten()
		cls.h = _hash()
		cls.silo = demo.silos_anlegen(cls.ctx, "AK" + cls.h)
		frappe.cache.delete_value("kt_silo_lager")
		mhd = add_days(nowdate(), 200)
		for artikel, menge in (("KT-MEHL", 500), ("KT-ZUCKER", 300)):
			terminal.wareneingang("Lager", artikel, f"L{cls.h}-{artikel}", menge, mhd, silo=cls.silo[artikel])
		cls.butter = terminal.wareneingang(
			"Lager",
			"KT-BUTTER",
			f"BU{cls.h}",
			100,
			add_days(nowdate(), 30),
			pruefwerte={"Temperatur Kühlware Wareneingang": {"wert": 4}},
		)["charge"]
		sperre.freigeben(cls.butter, "Test Akte")
		demo.metalldetektor_ok("Verpackung")

	def setUp(self):
		self.empfaenger = Empfaenger()
		self.addCleanup(self.empfaenger.schliessen)
		self.drucker = frappe.get_doc(
			{
				"doctype": "Etikettendrucker",
				"drucker_name": f"AK {_hash()}",
				"adresse": "127.0.0.1",
				"port": self.empfaenger.port,
				"dpi": "203",
				"etikett_breite": 105,
				"etikett_hoehe": 148,
			}
		).insert()
		for station in ("Lager", "Verpackung", "Backstube"):
			frappe.db.set_value(
				"Terminal Station",
				station,
				{"drucker_palette": self.drucker.name, "drucker_gebinde": self.drucker.name},
			)
			frappe.clear_document_cache("Terminal Station", station)

	def _verpacken(self, kartons, nve):
		wl = demo.neue_charge("KT-WL-KAKAO-NOUGAT", f"WLA{_hash()}", nowdate())
		demo.buchen(
			self.ctx, "Material Receipt", nowdate(), "05:00:00", ausgaenge=[("KT-WL-KAKAO-NOUGAT", wl, 60)]
		)
		sperre.freigeben(wl, "Test")
		fol = demo.neue_charge("KT-FOLIE", f"FOLA{_hash()}")
		demo.buchen(self.ctx, "Material Receipt", nowdate(), "05:00:00", ausgaenge=[("KT-FOLIE", fol, 5)])
		return terminal.herstellen(
			"Verpackung",
			"KT-FW-KAKAO-NOUGAT",
			[{"code": wl, "menge": 48}, {"code": fol, "menge": 1}],
			anzahl=kartons,
			einheit="Karton",
			ziel_behaelter=nve,
		)

	# ------------------------------------------------------------------ Druckprotokoll
	def test_palette_erstdruck_nachdruck_mit_grund(self):
		nve = terminal.palette_neu("Lager")["nve"]
		r = terminal.etikett_drucken("Lager", "palette", nve=nve, grund="ablauf")
		self.assertEqual(
			r["grund"], "Erstdruck"
		)  # noch nie gedruckt: Erstdruck, egal was das Terminal schickt
		self.empfaenger.warten()

		# gleicher Inhalt, per Knopf ohne Grund: nichts drucken, nach dem Grund fragen
		r = terminal.etikett_drucken("Lager", "palette", nve=nve)
		self.assertTrue(r["grund_noetig"])
		self.assertEqual([g["wert"] for g in r["gruende"]], ["beschaedigt", "fehlt"])
		self.assertEqual(len(self.empfaenger.daten), 1)

		r = terminal.etikett_drucken("Lager", "palette", nve=nve, grund="beschaedigt")
		self.assertEqual(r["grund"], "Beschädigt / unleserlich")
		self.empfaenger.warten(2)
		self.assertEqual(
			[(d.grund, d.drucker, d.station) for d in _drucke(palette=nve)],
			[
				("Erstdruck", self.drucker.name, "Lager"),
				("Beschädigt / unleserlich", self.drucker.name, "Lager"),
			],
		)
		with self.assertRaisesRegex(frappe.ValidationError, "Unbekannter Grund"):
			terminal.etikett_drucken("Lager", "palette", nve=nve, grund="einfach so")

	def test_inhalt_geaendert_und_im_ablauf(self):
		nve = terminal.palette_neu("Verpackung")["nve"]
		etiketten.drucken("Verpackung", "palette", nve=nve, grund="ablauf")
		self._verpacken(4, nve)
		self.assertEqual(etiketten.drucken("Verpackung", "palette", nve=nve)["grund"], "Inhalt geändert")
		self.assertEqual(
			etiketten.drucken("Verpackung", "palette", nve=nve, grund="ablauf")["grund"], "Im Ablauf"
		)
		self.assertEqual(_drucke(palette=nve)[-1].grund, "Im Ablauf")

	def test_gebinde_und_browserdruck(self):
		code = demo.neuer_traeger(f"TR-{_hash()}", "Teigbehälter")
		self.assertEqual(
			etiketten.drucken("Backstube", "gebinde", codes=code, grund="ablauf")["grund"], "Erstdruck"
		)
		self.assertTrue(etiketten.drucken("Backstube", "gebinde", codes=code)["grund_noetig"])
		# ohne Netzwerkdrucker: vor dem Öffnen der Druckseite vormerken, gleiche Regel
		self.assertTrue(terminal.etikett_vormerken("Backstube", "gebinde", codes=code)["grund_noetig"])
		terminal.etikett_vormerken("Backstube", "gebinde", codes=code, grund="fehlt")
		self.assertEqual([d.drucker for d in _drucke(traeger=code)], [self.drucker.name, "Browser"])

	def test_testdruck_im_protokoll(self):
		etiketten.testdruck(self.drucker.name)
		d = frappe.get_all(
			"Etikettendruck", filters={"art": "Test", "drucker": self.drucker.name}, pluck="grund"
		)
		self.assertEqual(d, ["Testdruck"])

	def test_protokoll_nicht_aenderbar(self):
		nve = terminal.palette_neu("Lager")["nve"]
		etiketten.drucken("Lager", "palette", nve=nve)
		doc = frappe.get_last_doc("Etikettendruck", filters={"palette": nve})
		doc.grund = "Testdruck"
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		with self.assertRaises(frappe.ValidationError):
			doc.delete()

	def test_nve_mit_leerzeichen(self):
		nve = terminal.palette_neu("Lager")["nve"]
		self.assertEqual(palette.finde(f"(00) {nve[:1]} {nve[1:8]} {nve[8:17]} {nve[17]}"), nve)

	# ------------------------------------------------------------------ Akte und Los-Suche
	def test_akte_und_wo_ist_das_los(self):
		a, b = terminal.palette_neu("Verpackung")["nve"], terminal.palette_neu("Verpackung")["nve"]
		e = self._verpacken(6, a)
		terminal.palette_umpacken("Verpackung", a, b, e["charge"], 2, "Karton")
		etiketten.drucken("Verpackung", "palette", nve=a)

		k = akte.palette(a)
		arten = [x["art"] for x in k["ereignisse"]]
		self.assertEqual(arten[0], "Angelegt")
		self.assertIn("Verpackung", arten)
		self.assertIn("Umpacken", arten)
		self.assertEqual(arten[-1], "Etikett")
		self.assertEqual(k["lose"][0]["charge"], e["charge"])

		f = terminal.info(e["charge"])["fundstellen"]
		self.assertEqual({p["nve"] for p in f["paletten"]}, {a, b})
		pa = next(p for p in f["paletten"] if p["nve"] == a)
		self.assertEqual(pa["dieses_los"], "4 Karton")
		self.assertTrue(pa["gepackt"])
		self.assertIn("Erstdruck", pa["letzter_druck"])

		# Etikett von a fehlt: b wurde gescannt und hat sein Etikett
		etiketten.drucken("Verpackung", "palette", nve=a, grund="fehlt", geprueft=b)
		self.assertEqual(_drucke(palette=a)[-1].bemerkung, f"Mit Etikett gescannt: {b}")
		etiketten.drucken("Verpackung", "palette", nve=a, grund="fehlt", geprueft="")
		self.assertEqual(_drucke(palette=a)[-1].bemerkung, f"Nicht geprüft: {b}")
		with self.assertRaisesRegex(frappe.ValidationError, "hat laut Scan ein Etikett"):
			etiketten.drucken("Verpackung", "palette", nve=a, grund="fehlt", geprueft=a)

	def test_akte_behaelter(self):
		code = demo.neuer_traeger(f"TA-{_hash()}", "Teigbehälter")
		gt = terminal.herstellen(
			"Backstube",
			"KT-GT-MUERBE",
			[
				{"code": self.silo["KT-MEHL"], "menge": 60},
				{"code": self.silo["KT-ZUCKER"], "menge": 20},
				{"code": self.butter, "menge": 20},
			],
			ziel_behaelter=code,
		)
		k = terminal.akte(code)
		self.assertEqual(k["typ"], "behaelter")
		self.assertIn("Befüllt", [x["art"] for x in k["ereignisse"]])
		self.assertEqual(k["lose"][0]["charge"], gt["charge"])
		with self.assertRaisesRegex(frappe.ValidationError, "keine Akte"):
			terminal.akte("GIBTSNICHT-" + self.h)

	# ------------------------------------------------------------------ Woraus besteht das?
	def test_herkunft_bis_zum_silo_und_lieferanten(self):
		gt = terminal.herstellen(
			"Backstube",
			"KT-GT-MUERBE",
			[
				{"code": self.silo["KT-MEHL"], "menge": 60},
				{"code": self.silo["KT-ZUCKER"], "menge": 20},
				{"code": self.butter, "menge": 20},
			],
		)
		h = terminal.herkunft(gt["charge"])
		self.assertEqual(h["baum"]["charge"], gt["charge"])
		self.assertEqual(h["baum"]["herstellung"]["station"], "Backstube")
		roh = {r["charge"]: r for r in h["rohstoffe"]}
		zucker = roh[f"L{self.h}-KT-ZUCKER"]
		self.assertEqual(zucker["wareneingang"]["silo"], self.silo["KT-ZUCKER"])  # direkt ins Silo
		self.assertEqual(zucker["wareneingang"]["station"], "Lager")
		self.assertTrue(zucker["wareneingang"]["zeit"])
		self.assertFalse(zucker["moeglich"])
		self.assertEqual(roh[self.butter]["freigabe"]["aktion"], "Freigeben")
		self.assertFalse(h["abgeschnitten"])

	def test_herkunft_ohne_charge(self):
		nve = terminal.palette_neu("Lager")["nve"]
		with self.assertRaisesRegex(frappe.ValidationError, "keine Charge"):
			terminal.herkunft(nve)

	def test_kandidaten_sind_die_anderen_paletten_mit_dem_los(self):
		# Das Los gilt je Tag und Artikel: auch andere Paletten des Tages tragen es (genau deshalb die Prüfung)
		a, b = terminal.palette_neu("Verpackung")["nve"], terminal.palette_neu("Verpackung")["nve"]
		self._verpacken(2, a)
		self._verpacken(2, b)
		kandidaten = druckprotokoll.andere_paletten(a)
		self.assertIn(b, kandidaten)
		self.assertNotIn(a, kandidaten)
