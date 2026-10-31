"""Lasttest: Datenflut für den Demo-Server und Messung der Antwortzeiten.

    bench --site keks.localhost execute keks_trace.lasttest.flut --kwargs "{'tage': 730}"
    bench --site keks.localhost execute keks_trace.lasttest.buchungen --kwargs "{'anzahl': 300}"
    bench --site keks.localhost execute keks_trace.lasttest.messen
    bench --site keks.localhost execute keks_trace.lasttest.aufraeumen

flut: erzeugt Chargen und Genealogie-Kanten für N Produktionstage direkt in der Datenbank (schnell),
so wie sie ein Betrieb in dieser Größe erzeugt: Rohstoff-Lieferungen, Grundteige (bis ein Jahr alt
eingesetzt), Veredelung mit Rework über mehrere Generationen, Backen, lose Ware (Wochen bis Monate
gelagert), Verpacken in Lose. faktor=2 verdoppelt alle Mengen je Tag.

buchungen: echte ERPNext-Buchungen über das Terminal (Wareneingang + Herstellen), um zu sehen, wie
lange eine Buchung am Terminal dauert, wenn das Lagerbuch voll ist.

messen: misst Rückverfolgung vorwärts und rückwärts, Terminal-Scan und Herstellen und gibt eine
Tabelle aus. Alle Lasttest-Chargen beginnen mit "LT-"; aufraeumen löscht sie wieder.
"""

import random
import time

import frappe
from frappe.utils import add_days, getdate, now_datetime, nowdate

PRAEFIX = "LT-"

# Je Produktionstag (faktor=1), grob nach einer Keksproduktion mit ~1.000 kg/Tag
JE_TAG = {
	"Grundteig": 4,
	"Teig veredelt": 6,
	"Backware": 6,
	"Rework": 2,
	"Ware lose": 6,
	"Fertigware": 10,
}
ROHSTOFF_ALLE_TAGE = 5  # neue Lieferantenchargen je Rohstoff
REWORK_HOECHSTALTER = 14  # Tage
LOSE_WARE_LAGERDAUER = 180  # Tage
GRUNDTEIG_LAGERDAUER = 365  # Tage


def _artikel(stufe):
	return frappe.get_all("Item", {"kt_chargen_stufe": stufe, "disabled": 0}, pluck="name") or []


def _hash():
	return frappe.generate_hash(length=10)


@frappe.whitelist()
def flut(tage: int = 730, faktor: int = 1, seed: int = 4711) -> dict:
	"""Chargen und Genealogie für `tage` Produktionstage bis heute erzeugen."""
	frappe.only_for("System Manager")
	rnd = random.Random(seed)
	tage, faktor = int(tage), int(faktor)
	artikel = {
		s: _artikel(s)
		for s in ("Rohstoff", "Packmittel", "Halbfabrikat", "Grundteig", "Teig veredelt", "Rework",
		          "Backware", "Ware lose", "Fertigware")
	}  # fmt: skip
	for s in ("Rohstoff", "Grundteig", "Teig veredelt", "Backware", "Ware lose", "Fertigware"):
		if not artikel[s]:
			frappe.throw(f"Kein Artikel der Stufe {s}. Erst die Demo anlegen (keks_trace.demo.run).")
	jetzt = now_datetime()
	nutzer = frappe.session.user
	start = getdate(add_days(nowdate(), -tage))
	chargen, kanten = [], []
	vorrat = {s: [] for s in artikel}  # (charge, tag) je Stufe
	rohstoff_aktuell = {}
	n = 0

	def charge(stufe, tag, verfall_tage=None):
		nonlocal n
		n += 1
		item = rnd.choice(artikel[stufe])
		name = f"{PRAEFIX}{tag.strftime('%y%m%d')}-{n:07d}"
		verfall = add_days(tag, verfall_tage) if verfall_tage else None
		chargen.append((name, name, item, tag, verfall, stufe, tag))
		vorrat[stufe].append((name, tag))
		return name

	def kante(ein, aus, menge, tag, anteil):
		kanten.append((_hash(), ein, aus, menge, anteil, tag))

	def aus_vorrat(stufe, tag, max_alter, k=1):
		"""Zufällig aus dem Vorrat einer Stufe, nicht älter als max_alter Tage, ältere bevorzugt."""
		grenze = add_days(tag, -max_alter)
		liste = [c for c, t in vorrat[stufe][-400:] if grenze <= t <= tag]
		if not liste:
			return []
		return rnd.sample(liste[: max(k * 3, 1)], min(k, len(liste)))

	for d in range(tage + 1):
		tag = getdate(add_days(start, d))
		if tag.weekday() >= 5:
			continue
		if d % ROHSTOFF_ALLE_TAGE == 0 or not rohstoff_aktuell:
			for s in ("Rohstoff", "Packmittel", "Halbfabrikat"):
				for item in artikel[s]:
					rohstoff_aktuell[item] = charge_fuer(item, s, tag, chargen, vorrat, rnd)
		roh = [c for i, c in rohstoff_aktuell.items() if i in artikel["Rohstoff"]]
		pack = [c for i, c in rohstoff_aktuell.items() if i in artikel["Packmittel"]]
		halb = [c for i, c in rohstoff_aktuell.items() if i in artikel["Halbfabrikat"]]
		for _ in range(JE_TAG["Grundteig"] * faktor):
			g = charge("Grundteig", tag, GRUNDTEIG_LAGERDAUER)
			for c in rnd.sample(roh, min(5, len(roh))):
				kante(c, g, 40, tag, 0.2)
			for r in aus_vorrat("Rework", tag, REWORK_HOECHSTALTER) if rnd.random() < 0.3 else []:
				kante(r, g, 5, tag, 0.03)
		for _ in range(JE_TAG["Teig veredelt"] * faktor):
			v = charge("Teig veredelt", tag, 3)
			for g in aus_vorrat("Grundteig", tag, GRUNDTEIG_LAGERDAUER, rnd.choice((1, 1, 2))):
				kante(g, v, 200, tag, 0.8)
			for c in rnd.sample(roh, min(3, len(roh))):
				kante(c, v, 10, tag, 0.05)
			for r in aus_vorrat("Rework", tag, REWORK_HOECHSTALTER) if rnd.random() < 0.4 else []:
				kante(r, v, 8, tag, 0.04)
		heute_teig = [c for c, t in vorrat["Teig veredelt"][-JE_TAG["Teig veredelt"] * faktor :]]
		for i in range(JE_TAG["Backware"] * faktor):
			b = charge("Backware", tag)
			kante(heute_teig[i % len(heute_teig)], b, 180, tag, 1)
		heute_back = [c for c, t in vorrat["Backware"][-JE_TAG["Backware"] * faktor :]]
		for _ in range(JE_TAG["Rework"] * faktor):
			r = charge("Rework", tag, REWORK_HOECHSTALTER)
			kante(rnd.choice(heute_back), r, 10, tag, 0.5)
			kante(rnd.choice(heute_teig), r, 10, tag, 0.5)
		for i in range(JE_TAG["Ware lose"] * faktor):
			lw = charge("Ware lose", tag, LOSE_WARE_LAGERDAUER)
			kante(heute_back[i % len(heute_back)], lw, 150, tag, 0.9)
			if halb:
				kante(rnd.choice(halb), lw, 15, tag, 0.1)
		for _ in range(JE_TAG["Fertigware"] * faktor):
			f = charge("Fertigware", tag, 270)
			for lw in aus_vorrat("Ware lose", tag, LOSE_WARE_LAGERDAUER, rnd.choice((1, 1, 2))):
				kante(lw, f, 90, tag, 0.95)
			for p in rnd.sample(pack, min(1, len(pack))):
				kante(p, f, 1, tag, 0.01)

	t0 = time.time()
	for i in range(0, len(chargen), 2000):
		frappe.db.sql(
			"""insert into `tabBatch` (name, batch_id, item, manufacturing_date, expiry_date, kt_chargen_stufe,
				kt_ursprungsdatum, kt_status, creation, modified, owner, modified_by, docstatus, batch_qty)
			values """
			+ ",".join(["(%s,%s,%s,%s,%s,%s,%s,'Freigegeben',%s,%s,%s,%s,0,0)"] * len(chargen[i : i + 2000])),
			[v for c in chargen[i : i + 2000] for v in (*c, jetzt, jetzt, nutzer, nutzer)],
		)
	for i in range(0, len(kanten), 5000):
		frappe.db.sql(
			"""insert into `tabChargen Genealogie` (name, input_batch, output_batch, menge, anteil, posting_date,
				quelle, storniert, creation, modified, owner, modified_by, docstatus)
			values """
			+ ",".join(["(%s,%s,%s,%s,%s,%s,'Buchung',0,%s,%s,%s,%s,0)"] * len(kanten[i : i + 5000])),
			[v for k in kanten[i : i + 5000] for v in (*k, jetzt, jetzt, nutzer, nutzer)],
		)
	frappe.db.commit()
	ergebnis = {
		"tage": tage,
		"chargen": len(chargen),
		"kanten": len(kanten),
		"sekunden": round(time.time() - t0, 1),
	}
	print(ergebnis)
	return ergebnis


def charge_fuer(item, stufe, tag, chargen, vorrat, rnd):
	name = f"{PRAEFIX}{tag.strftime('%y%m%d')}-{item}-{rnd.randrange(10**6):06d}"
	chargen.append((name, name, item, tag, add_days(tag, 300), stufe, tag))
	vorrat.setdefault(stufe, []).append((name, tag))
	return name


@frappe.whitelist()
def buchungen(anzahl: int = 300) -> dict:
	"""Echte Buchungen über das Terminal: Wareneingang Rohstoff, dann Grundteig herstellen (füllt das Lagerbuch)."""
	frappe.only_for("System Manager")
	from keks_trace import terminal

	rezept = _grundteig_rezept()
	if not rezept:
		frappe.throw("Kein Grundteig-Rezept mit Sackware gefunden. Erst die Demo anlegen.")
	dauer = []
	for i in range(int(anzahl)):
		zeilen = []
		for z in rezept["zutaten"]:
			c = terminal.wareneingang(
				"Lager",
				z["artikel"],
				f"{PRAEFIX}WE{_hash()[:6]}",
				z["menge"] * 1.01,
				add_days(nowdate(), 300),
			)["charge"]
			frappe.db.set_value("Batch", c, "kt_status", "Freigegeben")
			zeilen.append({"code": c, "menge": z["menge"]})
		t0 = time.time()
		terminal.herstellen("Backstube", rezept["artikel"], zeilen)
		dauer.append(time.time() - t0)
		if i % 50 == 49:
			frappe.db.commit()
			print(f"{i + 1} Buchungen, zuletzt {dauer[-1] * 1000:.0f} ms")
	frappe.db.commit()
	ergebnis = {
		"buchungen": len(dauer),
		"herstellen_ms_mittel": round(sum(dauer) / len(dauer) * 1000),
		"herstellen_ms_max": round(max(dauer) * 1000),
	}
	print(ergebnis)
	return ergebnis


def _grundteig_rezept():
	from keks_trace import terminal

	for r in terminal.rezepte("Backstube"):
		if r.get("stufe") != "Grundteig" or frappe.get_cached_value("Item", r.artikel, "kt_bio"):
			continue
		rz = terminal.rezept(r.artikel, station="Backstube")
		zutaten = [z for z in rz["zutaten"] if not z.get("silo") and z["stufe"] in ("Rohstoff", "Packmittel")]
		if zutaten and len(zutaten) == len(rz["zutaten"]):
			return {"artikel": r.artikel, "zutaten": zutaten}
	# Sonst irgendein Rezept, Silo-Zutaten weglassen (Vollständigkeit warnt nur)
	for r in terminal.rezepte("Backstube"):
		if frappe.get_cached_value("Item", r.artikel, "kt_bio"):
			continue
		rz = terminal.rezept(r.artikel, station="Backstube")
		zutaten = [z for z in rz["zutaten"] if not z.get("silo") and z["stufe"] == "Rohstoff"]
		if zutaten:
			return {"artikel": r.artikel, "zutaten": zutaten}
	return None


def _zeit(fn, *args, n=3, **kw):
	beste, ergebnis = None, None
	for _ in range(n):
		t0 = time.time()
		ergebnis = fn(*args, **kw)
		d = time.time() - t0
		beste = d if beste is None else min(beste, d)
	return beste, ergebnis


@frappe.whitelist()
def messen() -> list[dict]:
	"""Antwortzeiten bei der aktuellen Datenmenge messen."""
	from keks_trace import terminal, trace

	zeilen = []
	z = {
		"Chargen": frappe.db.count("Batch"),
		"Genealogie-Kanten": frappe.db.count("Chargen Genealogie"),
		"Lagerbuchungen (Stock Ledger)": frappe.db.count("Stock Ledger Entry"),
	}
	for k, v in z.items():
		zeilen.append({"was": k, "wert": f"{v:,}".replace(",", "."), "ms": None})

	def ein(was, fn, *args, **kw):
		d, r = _zeit(fn, *args, **kw)
		menge = len(r) if isinstance(r, list) else (len(r.get("chargen", [])) if isinstance(r, dict) else "")
		zeilen.append({"was": was, "wert": menge, "ms": round(d * 1000)})

	alt_mehl = frappe.db.sql(
		f"""select name from `tabBatch` where name like '{PRAEFIX}%%' and kt_chargen_stufe = 'Rohstoff'
		order by manufacturing_date limit 1 offset 20"""
	)
	neu_fw = frappe.db.sql(
		f"""select name from `tabBatch` where name like '{PRAEFIX}%%' and kt_chargen_stufe = 'Fertigware'
		order by manufacturing_date desc limit 1"""
	)
	alt_gt = frappe.db.sql(
		f"""select name from `tabBatch` where name like '{PRAEFIX}%%' and kt_chargen_stufe = 'Grundteig'
		order by manufacturing_date limit 1 offset 10"""
	)
	if alt_mehl:
		ein("Rückruf Rohstoff vorwärts (Chargen gefunden)", trace.vorwaerts, alt_mehl[0][0])
		ein("Rückruf komplett inkl. Kunden/Paletten", trace.rueckverfolgung, alt_mehl[0][0], "Vorwärts")
	if alt_gt:
		ein("Grundteig vorwärts", trace.vorwaerts, alt_gt[0][0])
	if neu_fw:
		ein("Kundenreklamation Los rückwärts", trace.rueckwaerts, neu_fw[0][0])
	charge = frappe.db.get_value("Batch", {"name": ["like", f"{PRAEFIX}%"]}, "name") or frappe.db.get_value(
		"Batch", {}, "name"
	)
	ein("Terminal: Scan einer Charge", terminal.info, charge)
	ein("Terminal: Rezeptliste Backstube", terminal.rezepte, "Backstube")
	ein("Terminal: Aufträge Verpackung", terminal.auftraege, "Verpackung")
	b = frappe.db.get_value("Batch", {"name": ["like", f"{PRAEFIX}WE%"]}, "name")
	if b:
		from keks_trace import bilanz

		ein("Mengenbilanz einer Charge", bilanz.mengenbilanz, b)
	frappe.db.rollback()
	breite = max(len(z["was"]) for z in zeilen)
	for z in zeilen:
		print(
			f"{z['was']:<{breite}}  {z['wert']!s:>10}  {'' if z['ms'] is None else str(z['ms']) + ' ms':>9}"
		)
	return zeilen


@frappe.whitelist()
def aufraeumen() -> dict:
	"""Lasttest-Chargen und ihre Kanten löschen (nur die aus flut; echte Buchungen bleiben im Lagerbuch)."""
	frappe.only_for("System Manager")
	k = frappe.db.sql(
		f"""delete from `tabChargen Genealogie` where input_batch like '{PRAEFIX}%%' and stock_entry is null"""
	)
	frappe.db.sql(
		f"""delete b from `tabBatch` b where b.name like '{PRAEFIX}%%'
		and not exists (select 1 from `tabSerial and Batch Entry` s where s.batch_no = b.name)"""
	)
	frappe.db.commit()
	print("Lasttest-Daten gelöscht")
	return {"ok": True, "kanten": k}
