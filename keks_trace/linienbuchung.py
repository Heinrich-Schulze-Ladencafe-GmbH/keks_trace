"""Buchen an der Backstraße: Kübel einkippen, nachfüllen, Palette fertig.

Ablauf (siehe Konzept „Produktionsplanung und Datenmodell“):
- Jede Station an der Linie arbeitet für einen gewählten Produktionsauftrag (Terminal Station →
  aktueller Auftrag). Former und Verpackung können so 45 Minuten versetzt an verschiedenen
  Aufträgen sein.
- Zuführen (Former, Nachfüllstationen): Kübel, Gebinde, Charge oder Tank scannen → Umlagerung in den
  Lagerort der Linie, mit dem Produktionsauftrag als Vermerk. Der Kübel wird dabei geleert.
- Palette fertig (Paletten-Terminal): Anzahl Kartons → Fertigung. Verbraucht wird aus dem Lagerort
  der Linie, was laut Linienrezept auf diese Menge entfällt, nur Ware DIESES Auftrags, älteste
  zuerst. Ergebnis ist das Tages-Los auf der Palette.
- Auftrag beenden: Rest auf der Linie wird als „Linienrest“ ausgebucht.

Linienrezept: die Stückliste der Fertigware, durch die Stufen aufgelöst, die auf der Linie ohne
eigene Buchung entstehen (Backware, Ware lose). Was übrig bleibt, wird an der Linie zugeführt:
veredelter Teig aus Kübeln, Füllung, Glasur, Schokolade, Streusel, Packmittel.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate, now_datetime, nowdate

from keks_trace import kennzeichnung, pruefung
from keks_trace import los as los_modul
from keks_trace import palette as paletten
from keks_trace.utils import artikel_stufe

EPS = 1e-6
AUF_DER_LINIE = ("Backware", "Ware lose")  # entstehen auf der Linie ohne eigene Buchung
LINIENREST = "Linienrest"


class LinienFehler(frappe.ValidationError):
	pass


def _fehler(text):
	frappe.throw(text, LinienFehler, title=_("Linie"))


# ---------------------------------------------------------------------------
# Rezept und Bestand auf der Linie
# ---------------------------------------------------------------------------


def linienrezept(artikel: str, tiefe: int = 0) -> dict[str, float]:
	"""{Zutat: Menge je 1 Lagereinheit Fertigware}, durch Backware und lose Ware aufgelöst."""
	ergebnis = defaultdict(float)
	bom = frappe.db.get_value("BOM", {"item": artikel, "is_default": 1, "is_active": 1, "docstatus": 1})
	if not bom or tiefe > 6:
		return ergebnis
	menge = flt(frappe.db.get_value("BOM", bom, "quantity")) or 1
	for z in frappe.get_all("BOM Item", {"parent": bom}, ["item_code", "stock_qty"]):
		je = flt(z.stock_qty) / menge
		if artikel_stufe(z.item_code) in AUF_DER_LINIE:
			for k, v in linienrezept(z.item_code, tiefe + 1).items():
				ergebnis[k] += je * v
		else:
			ergebnis[z.item_code] += je
	return dict(ergebnis)


def bestand(auftrag: str) -> list[dict]:
	"""Was für diesen Auftrag auf der Linie liegt: je Charge, älteste Zuführung zuerst."""
	lager = frappe.db.get_value(
		"Linie", frappe.db.get_value("Produktionsauftrag", auftrag, "linie"), "lagerort"
	)
	zeilen = frappe.db.sql(
		"""
		select sbe.batch_no as charge, b.item as artikel, sum(sbe.qty) as menge,
			min(case when sbe.qty > 0 then sbb.posting_datetime end) as zugefuehrt
		from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
		join `tabStock Entry` se on sbb.voucher_type = 'Stock Entry' and se.name = sbb.voucher_no
		join `tabBatch` b on b.name = sbe.batch_no
		where sbe.warehouse = %(lager)s and se.kt_produktionsauftrag = %(pa)s
			and sbb.docstatus = 1 and sbb.is_cancelled = 0
		group by sbe.batch_no, b.item
		having sum(sbe.qty) > 0.000001
		order by zugefuehrt, sbe.batch_no
		""",
		{"lager": lager, "pa": auftrag},
		as_dict=True,
	)
	return [{**z, "menge": flt(z.menge, 6)} for z in zeilen]


# ---------------------------------------------------------------------------
# Aufträge an der Station
# ---------------------------------------------------------------------------


def _station(name):
	return frappe.get_cached_doc("Terminal Station", name)


def _linie(s):
	if not s.linie:
		_fehler(_("Station {0} ist keiner Linie zugeordnet.").format(s.name))
	return frappe.get_cached_doc("Linie", s.linie)


def _menge_text(artikel, kg):
	return paletten.zerlegen(artikel, kg) if kg else "0"


def auftraege(station: str) -> list[dict]:
	"""Freigegebene und laufende Aufträge der Linie, in Planungsreihenfolge (die Freigabe ist das Tor)."""
	s = _station(station)
	_linie(s)
	liste = frappe.get_all(
		"Produktionsauftrag",
		filters={"linie": s.linie, "status": ["in", ["Freigegeben", "Läuft"]]},
		fields=[
			"name", "datum", "reihenfolge", "status", "artikel", "artikelname", "menge", "einheit", "menge_kg",
			"gebucht_kg", "kunde", "kundenauftrag", "verpackungsanlage", "engpass", "dauer_stunden",
		],
		order_by="datum, reihenfolge, creation",
	)  # fmt: skip
	aktuell = frappe.db.get_value("Terminal Station", s.name, "aktueller_auftrag")
	for a in liste:
		a["aktuell"] = a["name"] == aktuell
		a["menge_text"] = _menge_text(a["artikel"], a["menge_kg"])
		a["gebucht_text"] = _menge_text(a["artikel"], a["gebucht_kg"])
		a["datum_text"] = formatdate(a["datum"])
		a["kundenname"] = frappe.db.get_value("Customer", a["kunde"], "customer_name") if a["kunde"] else None
	return liste


def waehlen(station: str, auftrag: str) -> dict:
	s = _station(station)
	_linie(s)
	pa = frappe.get_doc("Produktionsauftrag", auftrag)
	if pa.linie != s.linie:
		_fehler(_("Auftrag {0} ist für {1}, nicht für {2}.").format(pa.name, pa.linie, s.linie))
	if pa.status not in ("Freigegeben", "Läuft"):
		_fehler(_("Auftrag {0} ist {1}. Nur freigegebene Aufträge können laufen.").format(pa.name, pa.status))
	if pa.status == "Freigegeben":
		pa.db_set({"status": "Läuft", "gestartet_am": now_datetime()})
	frappe.db.set_value("Terminal Station", s.name, "aktueller_auftrag", pa.name)
	frappe.clear_document_cache("Terminal Station", s.name)
	return info(pa.name)


def _laufender(s):
	name = frappe.db.get_value("Terminal Station", s.name, "aktueller_auftrag")
	if not name:
		_fehler(_("Bitte zuerst den Produktionsauftrag wählen."))
	pa = frappe.get_doc("Produktionsauftrag", name)
	if pa.status != "Läuft":
		_fehler(_("Auftrag {0} ist {1}. Bitte einen laufenden Auftrag wählen.").format(pa.name, pa.status))
	return pa


def info(auftrag: str) -> dict:
	pa = frappe.get_doc("Produktionsauftrag", auftrag)
	rezept = linienrezept(pa.artikel)
	auf_linie = bestand(pa.name)
	je_artikel = defaultdict(float)
	for z in auf_linie:
		je_artikel[z["artikel"]] += z["menge"]
	rest_kg = max(flt(pa.menge_kg) - flt(pa.gebucht_kg), 0)
	zutaten = []
	for artikel, je in rezept.items():
		zutaten.append(
			{
				"artikel": artikel,
				"name": frappe.get_cached_value("Item", artikel, "item_name"),
				"stufe": artikel_stufe(artikel),
				"einheit": frappe.get_cached_value("Item", artikel, "stock_uom"),
				"auf_linie": flt(je_artikel.get(artikel), 3),
				"bedarf_rest": flt(je * rest_kg, 3),
				"reicht_fuer": flt(je_artikel.get(artikel, 0) / je, 1) if je else None,
			}
		)
	beutel = paletten.faktor(pa.artikel, "Beutel") if _hat(pa.artikel, "Beutel") else None
	karton = paletten.faktor(pa.artikel, "Karton") if _hat(pa.artikel, "Karton") else None
	lose = lose_artikel(pa.artikel)
	return {
		"auftrag": pa.name,
		"status": pa.status,
		"artikel": pa.artikel,
		"name": pa.artikelname,
		"datum": formatdate(pa.datum),
		"kunde": frappe.db.get_value("Customer", pa.kunde, "customer_name") if pa.kunde else None,
		"kundenauftrag": pa.kundenauftrag,
		"menge_text": _menge_text(pa.artikel, pa.menge_kg),
		"gebucht_text": _menge_text(pa.artikel, pa.gebucht_kg),
		"offen_text": _menge_text(pa.artikel, rest_kg),
		"gebucht_kg": flt(pa.gebucht_kg, 3),
		"lagereinheit": frappe.get_cached_value("Item", pa.artikel, "stock_uom"),
		"menge_kg": flt(pa.menge_kg, 3),
		"verpackungsanlage": pa.verpackungsanlage,
		"engpass": pa.engpass,
		"beutel_je_karton": round(karton / beutel) if beutel and karton else None,
		"einheiten": paletten.einheiten(pa.artikel),
		"los": pa.los,
		"spezifikation": frappe.get_cached_value("Item", pa.artikel, "kt_spezifikation"),
		"karton_je_palette": round(paletten.faktor(pa.artikel, "Palette") / karton)
		if karton and _hat(pa.artikel, "Palette")
		else None,
		"lose_artikel": lose,
		"lose_name": frappe.get_cached_value("Item", lose, "item_name") if lose else None,
		"lose_einheit": lose_einheit(lose) if lose else None,
		"lose_je_einheit": paletten.faktor(lose, lose_einheit(lose)) if lose else None,
		"linienlager": frappe.get_cached_value("Linie", pa.linie, "linienlager"),
		"im_linienlager": im_linienlager(pa.linie),
		"zutaten": zutaten,
		"kuebel": kuebel_vorschlag(
			[z["artikel"] for z in zutaten if z["stufe"] in ("Teig veredelt", "Grundteig")]
		),
	}


def lose_artikel(artikel: str) -> str | None:
	"""Die lose Ware, aus der der Artikel verpackt wird (Honig Lebkuchen 200 g → Honig Moppen lose)."""
	bom = frappe.db.get_value("BOM", {"item": artikel, "is_default": 1, "is_active": 1, "docstatus": 1})
	if not bom:
		return None
	for z in frappe.get_all("BOM Item", {"parent": bom}, ["item_code"], order_by="idx"):
		if artikel_stufe(z.item_code) == "Ware lose":
			return z.item_code
	return None


LOSE_ZIELE = ("lager", "linienlager")


def lose_einheit(artikel: str) -> str:
	"""Lose Ware wird in Kartons gezählt (kg je Karton fest am Artikel), sonst in der Lagereinheit (kg)."""
	return "Karton" if _hat(artikel, "Karton") else frappe.get_cached_value("Item", artikel, "stock_uom")


def lose_fertig(
	station: str,
	anzahl: float,
	einheit: str | None = None,
	ziel: str = "lager",
	palette: str | None = None,
	kiste: str | None = None,
) -> dict:
	"""Verpackungs-PC: Aus dem laufenden Auftrag wird auch lose Ware gemacht, parallel zur
	Verpackungsmaschine abgenommen (F5) oder, wenn die Verpackung nicht nachkommt, ins Linienlager (F6).

	Gezählt wird in Kartons (kg je Karton fest am Artikel). Ziel „lager“: Kartons ins Lager, optional auf
	eine Palette. Ziel „linienlager“: Kartons warten an der Linie und werden später verpackt (F7, Verpackungs-PC
	„Lose Ware verpacken“). Wannen werden nicht gebucht. Verbraucht wird wie bei den Kartons der Teig von der
	Linie und die Füllung aus dem Lager. Jede Buchung ergibt eine eigene Charge (ein Lagerort je Charge)."""
	from keks_trace import terminal

	s = _station(station)
	linie = _linie(s)
	pa = _laufender(s)
	pruefung.pruefe_station_frei(s.name)
	artikel = lose_artikel(pa.artikel)
	if not artikel:
		_fehler(_("Zu {0} gibt es keine lose Ware im Rezept.").format(pa.artikel))
	if ziel not in LOSE_ZIELE:
		_fehler(_("Unbekanntes Ziel {0}.").format(ziel))
	einheit = einheit or lose_einheit(artikel)
	anzahl = flt(anzahl)
	kg = flt(anzahl * paletten.faktor(artikel, einheit), 6)
	if kg <= EPS:
		_fehler(_("Bitte die Anzahl eingeben."))
	if ziel == "linienlager":
		if not linie.get("linienlager"):
			_fehler(_("Für die Linie {0} ist kein Linienlager eingerichtet.").format(linie.name))
		if palette:
			_fehler(_("Kartons im Linienlager kommen auf keine Palette, sie werden später verpackt."))
		lager = linie.linienlager
	else:
		lager = linie.fertiglager or terminal._ziel_lager(s, artikel)
	nve = paletten.finde(palette) if palette else None
	if palette and not nve:
		_fehler(_("{0} ist keine Palette.").format(palette))
	if nve:
		paletten._offen(nve)
	behaelter = terminal._ziel_behaelter(kiste) if kiste else None
	zeilen, hinweise, vom_teig = _verbrauch(pa, artikel, kg, linie)
	if not vom_teig:
		_fehler(
			_(
				"Für Auftrag {0} ist noch nichts auf der Linie gebucht. Erst am Kneter die Kübel scannen."
			).format(pa.name)
		)
	charge = terminal._neue_charge(artikel, getdate(nowdate()))
	jetzt = now_datetime()
	ausgabe = terminal._se_zeile(
		{"artikel": artikel, "charge": charge, "menge": kg, "behaelter": behaelter}, t_warehouse=lager
	)
	ausgabe["is_finished_item"] = 1
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Manufacture",
			"purpose": "Manufacture",
			"company": linie.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"kt_produktionsauftrag": pa.name,
			"items": [terminal._se_zeile(z, s_warehouse=z["lager"]) for z in zeilen] + [ausgabe],
		}
	)
	se.insert()
	se.submit()
	if nve:
		paletten.beladen(nve, charge, anzahl, einheit, s.name, "Verpackung", "Stock Entry", se.name)
	b = frappe.db.get_value("Batch", charge, ["expiry_date", "kt_status"], as_dict=True)
	return {
		"charge": charge,
		"name": frappe.get_cached_value("Item", artikel, "item_name"),
		"anzahl": anzahl,
		"einheit": einheit,
		"menge": kg,
		"ziel": ziel,
		"lager": lager,
		"palette": nve,
		"kiste": behaelter,
		"mhd": formatdate(b.expiry_date) if b.expiry_date else None,
		"gesperrt": b.kt_status == "Gesperrt",
		"buchung": se.name,
		"verbraucht": [
			{
				"name": frappe.get_cached_value("Item", z["artikel"], "item_name"),
				"charge": z.get("charge") or z.get("silo"),
				"menge": flt(z["menge"], 3),
			}
			for z in zeilen
		],
		"hinweise": hinweise + list(se.flags.kt_fifo_warnungen or []),
	}


def im_linienlager(linie: str) -> list[dict]:
	"""Was im Linienlager auf die Verpackung wartet (Kartons lose Ware), älteste zuerst."""
	lager = frappe.get_cached_value("Linie", linie, "linienlager")
	if not lager:
		return []
	zeilen = frappe.db.sql(
		"""
		select sbe.batch_no as charge, b.item as artikel, b.item_name as name, sum(sbe.qty) as menge,
			date(min(sbb.posting_datetime)) as seit
		from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
		join `tabBatch` b on b.name = sbe.batch_no
		where sbe.warehouse = %(lager)s and sbb.docstatus = 1 and sbb.is_cancelled = 0
		group by sbe.batch_no, b.item, b.item_name
		having sum(sbe.qty) > 0.000001
		order by seit, sbe.batch_no
		""",
		{"lager": lager},
		as_dict=True,
	)
	return [
		{
			**z,
			"menge": flt(z.menge, 3),
			"menge_text": paletten.zerlegen(z.artikel, z.menge),
			"seit": formatdate(z.seit),
			"alt": getdate(z.seit) < getdate(nowdate()),
		}
		for z in zeilen
	]


def _hat(artikel, uom):
	return bool(frappe.db.exists("UOM Conversion Detail", {"parent": artikel, "uom": uom}))


def kuebel_vorschlag(artikel: list[str], anzahl: int = 5) -> list[dict]:
	"""Belegte Kübel mit diesen Artikeln, ältester Teig zuerst (kein fester Lagerplatz nötig)."""
	if not artikel:
		return []
	zeilen = frappe.db.sql(
		"""
		select t.code, t.artikel, t.menge, t.charge, b.manufacturing_date as datum, b.expiry_date as verfall
		from `tabProdukttraeger` t join `tabBatch` b on b.name = t.charge
		where t.status = 'Belegt' and t.artikel in %(a)s and ifnull(b.kt_status, '') != 'Gesperrt'
			and (b.expiry_date is null or b.expiry_date >= %(heute)s)
		order by coalesce(b.kt_ursprungsdatum, b.manufacturing_date), b.creation, t.code
		limit %(n)s
		""",
		{"a": tuple(artikel), "heute": nowdate(), "n": anzahl},
		as_dict=True,
	)
	return [
		{
			"code": z.code,
			"name": frappe.get_cached_value("Item", z.artikel, "item_name"),
			"menge": flt(z.menge, 1),
			"datum": formatdate(z.datum) if z.datum else None,
			"charge": z.charge,
		}
		for z in zeilen
	]


# ---------------------------------------------------------------------------
# Zuführen: Kübel einkippen, Gebinde nachfüllen
# ---------------------------------------------------------------------------


def zufuehren(station: str, code: str, menge: float | None = None) -> dict:
	from keks_trace import terminal
	from keks_trace.silo import bestand as silo_bestand

	s = _station(station)
	if not s.f_linie:
		_fehler(_("An der Station {0} wird nicht an die Linie gegeben.").format(s.name))
	linie = _linie(s)
	pa = _laufender(s)
	rezept = linienrezept(pa.artikel)
	r = terminal.aufloesen(code)
	if r["typ"] == "palette":
		_fehler(_("{0} ist eine Palette.").format(r["code"]))
	artikel = r.get("artikel")
	if not artikel:
		_fehler(_("{0} ist leer.").format(r["code"]))
	rework_ziel = None
	if artikel not in rezept and artikel_stufe(artikel) == "Rework":
		rework_ziel = _rework_ziel(artikel, rezept, pa)
	elif artikel not in rezept:
		_fehler(
			_("{0} gehört nicht zu {1}. Bitte den richtigen Kübel bzw. das richtige Gebinde nehmen.").format(
				frappe.bold(frappe.get_cached_value("Item", artikel, "item_name")), pa.artikelname
			)
		)
	menge = flt(menge)
	if r["typ"] == "silo":
		if menge <= EPS:
			_fehler(_("Bitte die Menge aus {0} eingeben.").format(r["silo"]))
		teile, offen = [], menge
		for c in silo_bestand(r["lager"], now_datetime()):
			if offen <= EPS:
				break
			nimm = min(offen, c["menge"])
			teile.append((c["charge"], nimm, None))
			offen -= nimm
		if offen > EPS:
			_fehler(_("Im {0} sind rechnerisch nur {1}.").format(r["silo"], flt(menge - offen, 3)))
	else:
		inhalt = flt(r.get("inhalt"))
		if menge <= EPS:
			if r["typ"] == "behaelter" and inhalt > EPS:
				menge = inhalt  # Kübel wird ganz eingekippt
			else:
				_fehler(_("Bitte die Menge eingeben."))
		if menge > inhalt * 1.005 + EPS:
			_fehler(_("{0} enthält nur {1}.").format(r["code"], flt(inhalt, 3)))
		teile = [(r["charge"], menge, r.get("behaelter"))]

	if rework_ziel:
		_pruefe_rework_anteil(pa, artikel, rework_ziel, sum(m for _c, m, _b in teile))
	hinweise = []
	for charge, _m, _b in teile:
		terminal._pruefe_charge(charge, artikel)
		kennzeichnung.pruefe_zutat(pa.artikel, charge, artikel, r.get("silo"))
	if r["typ"] == "behaelter" and r.get("behaelter"):
		aelter = [k for k in kuebel_vorschlag([artikel], 3) if k["code"] != r["behaelter"]]
		eigene = frappe.db.get_value("Batch", r["charge"], ["kt_ursprungsdatum", "manufacturing_date"])
		eigen_datum = getdate(eigene[0] or eigene[1]) if eigene and (eigene[0] or eigene[1]) else None
		if aelter and eigen_datum and aelter[0]["datum"]:
			alt = frappe.db.get_value(
				"Batch", aelter[0]["charge"], ["kt_ursprungsdatum", "manufacturing_date"]
			)
			alt_datum = getdate(alt[0] or alt[1]) if alt[0] or alt[1] else None
			if alt_datum and alt_datum < eigen_datum:
				hinweise.append(
					_("Älter wäre {0} (vom {1}). Beim nächsten Mal bitte den ältesten Kübel nehmen.").format(
						aelter[0]["code"], aelter[0]["datum"]
					)
				)

	uom = frappe.get_cached_value("Item", artikel, "stock_uom")
	jetzt = now_datetime()
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Transfer",
			"purpose": "Material Transfer",
			"company": linie.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"kt_produktionsauftrag": pa.name,
			"items": [
				{
					"item_code": artikel,
					"qty": m,
					"transfer_qty": m,
					"uom": uom,
					"stock_uom": uom,
					"conversion_factor": 1,
					"s_warehouse": r["lager"],
					"t_warehouse": linie.lagerort,
					"use_serial_batch_fields": 1,
					"batch_no": c,
					"kt_traeger": b,
				}
				for c, m, b in teile
			],
		}
	)
	se.insert()
	se.submit()
	return {
		"name": frappe.get_cached_value("Item", artikel, "item_name"),
		"menge": flt(sum(m for _c, m, _b in teile), 3),
		"einheit": uom,
		"chargen": [c for c, _m, _b in teile],
		"behaelter": r.get("behaelter"),
		"auftrag": pa.name,
		"buchung": se.name,
		"hinweise": hinweise,
		"info": info(pa.name),
	}


# ---------------------------------------------------------------------------
# Rework (Flussschema F18/F19): die Backstube bucht Rework von der Linie, der Kneter gibt es zurück
# ---------------------------------------------------------------------------


def rework_ersatz() -> dict[str, set]:
	"""{Rework-Artikel: Teige, die es laut aktiver Rework-Regel ersetzen darf}."""
	ersatz = defaultdict(set)
	for r in frappe.get_all("Rework Regel", {"aktiv": 1}, ["rework_artikel", "ziel_artikel"]):
		ersatz[r.rework_artikel].add(r.ziel_artikel)
	return ersatz


def _rework_ziel(artikel, rezept, pa) -> str:
	"""Der Teig im Linienrezept, den dieses Rework ersetzt (Filter: Regel und Allergene)."""
	from keks_trace.rework import _pruefe_allergene

	ziele = [z for z in rework_ersatz().get(artikel, ()) if z in rezept]
	if not ziele:
		_fehler(
			_("{0} passt nicht zu {1}: keine Rework-Regel für einen Teig dieses Artikels.").format(
				frappe.bold(frappe.get_cached_value("Item", artikel, "item_name")), pa.artikelname
			)
		)
	_pruefe_allergene(artikel, ziele[0])
	return ziele[0]


def _pruefe_rework_anteil(pa, artikel, ziel, menge):
	"""Rework-Anteil am Teig, der für diesen Auftrag auf der Linie liegt, höchstens laut Regel."""
	maximum = flt(
		frappe.db.get_value(
			"Rework Regel",
			{"rework_artikel": artikel, "ziel_artikel": ziel, "aktiv": 1},
			"max_anteil_prozent",
		)
	)
	ersatz = rework_ersatz()
	teig = rework = 0.0
	for z in bestand(pa.name):
		if z["artikel"] == ziel:
			teig += z["menge"]
		elif ziel in ersatz.get(z["artikel"], ()):
			rework += z["menge"]
	gesamt = teig + rework + menge
	if gesamt <= EPS or (rework + menge) / gesamt * 100 > maximum + 1e-9:
		erlaubt = (
			max(maximum / 100 * (teig + rework) - rework, 0) / (1 - maximum / 100) if maximum < 100 else 0
		)
		_fehler(
			_(
				"Zu viel Rework: höchstens {0} % in {1}. Auf der Linie liegen {2} kg Teig und {3} kg Rework, "
				"dazu passen noch {4} kg Rework. Erst Teig zuführen."
			).format(
				flt(maximum, 1),
				frappe.get_cached_value("Item", ziel, "item_name"),
				flt(teig, 1),
				flt(rework, 1),
				flt(erlaubt, 1),
			)
		)


def rework_sorten(auftrag: str) -> list[dict]:
	"""Rework-Sorten, die von diesem Auftrag abgenommen werden dürfen: es gibt eine Regel zu einem Teig
	im Linienrezept, und die Ware hat keine Allergene, die das Rework nicht hat. Nach Entnahmepunkt."""
	from keks_trace.utils import allergene

	pa = frappe.get_doc("Produktionsauftrag", auftrag)
	rezept = linienrezept(pa.artikel)
	ware = allergene(frappe.get_cached_value("Item", pa.artikel, "kt_allergengruppe"))
	ergebnis = []
	for artikel, ziele in rework_ersatz().items():
		if not ziele & set(rezept) or frappe.get_cached_value("Item", artikel, "disabled"):
			continue
		if ware - allergene(frappe.get_cached_value("Item", artikel, "kt_allergengruppe")):
			continue
		ergebnis.append(
			{
				"artikel": artikel,
				"name": frappe.get_cached_value("Item", artikel, "item_name"),
				"punkt": frappe.get_cached_value("Item", artikel, "kt_entnahmepunkt") or "",
			}
		)
	reihenfolge = {"Nach dem Ofen": 0, "Nach dem Sprühen": 1, "Am Ende der Linie": 2}
	return sorted(ergebnis, key=lambda x: (reihenfolge.get(x["punkt"], 3), x["name"]))


def laufende_auftraege() -> list[dict]:
	"""Was gerade auf den Linien läuft (für die Backstube: von welchem Auftrag kommt das Rework?).

	Zuerst die Aufträge, an denen eine Station gerade arbeitet (Kneter, Verpackungs-PC); ältere, nie beendete
	Aufträge nur, wenn es keine solchen gibt."""
	liste = frappe.get_all(
		"Produktionsauftrag",
		{"status": "Läuft"},
		["name as auftrag", "linie", "artikel", "artikelname as name", "datum"],
		order_by="linie, gestartet_am desc",
	)
	aktiv = set(
		frappe.get_all(
			"Terminal Station", {"aktiv": 1, "aktueller_auftrag": ["is", "set"]}, pluck="aktueller_auftrag"
		)
	)
	an_station = [a for a in liste if a.auftrag in aktiv]
	return [{**a, "datum": formatdate(a.datum)} for a in (an_station or liste)]


def rework_von_linie(station: str, auftrag: str, rework_artikel: str, kg: float, behaelter: str) -> dict:
	"""Backstube: Rework-Behälter von der Linie gewogen. Der Teig dieses Auftrags auf der Linie wird zu
	Rework (neue Rework-Charge im Behälter, Herkunft = Teigchargen). So zählt Rework nicht als Linienrest."""
	from keks_trace import terminal

	s = _station(station)
	pa = frappe.get_doc("Produktionsauftrag", auftrag)
	if pa.status != "Läuft":
		_fehler(_("Auftrag {0} ist {1}. Rework nur von laufenden Aufträgen.").format(pa.name, pa.status))
	if rework_artikel not in {x["artikel"] for x in rework_sorten(pa.name)}:
		_fehler(
			_("{0} passt nicht zu {1} (Regel oder Allergene).").format(
				frappe.get_cached_value("Item", rework_artikel, "item_name"), pa.artikelname
			)
		)
	kg = flt(kg, 6)
	if kg <= EPS:
		_fehler(_("Bitte das Gewicht von der Waage eingeben."))
	if not behaelter:
		_fehler(_("Bitte den Rework-Behälter scannen oder antippen."))
	behaelter = terminal._ziel_behaelter(behaelter)
	if frappe.db.get_value("Produkttraeger", behaelter, "typ") != "Rework-Behälter":
		_fehler(_("{0} ist kein Rework-Behälter.").format(behaelter))
	linie = frappe.get_cached_doc("Linie", pa.linie)
	ersatz = rework_ersatz()
	teig = [
		z
		for z in bestand(pa.name)
		if artikel_stufe(z["artikel"]) in ("Grundteig", "Teig veredelt") or z["artikel"] in ersatz
	]
	vorhanden = sum(z["menge"] for z in teig)
	if kg > vorhanden + 1e-4:
		_fehler(
			_("Für Auftrag {0} liegen nur {1} kg Teig auf der Linie. Am Kneter gebucht?").format(
				pa.name, flt(vorhanden, 1)
			)
		)
	zeilen, offen = [], kg
	for z in teig:
		if offen <= EPS:
			break
		nimm = min(offen, z["menge"])
		zeilen.append({"artikel": z["artikel"], "charge": z["charge"], "menge": flt(nimm, 6)})
		offen -= nimm
	charge = terminal._neue_charge(rework_artikel, getdate(nowdate()))
	jetzt = now_datetime()
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Repack",
			"purpose": "Repack",
			"company": linie.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"kt_produktionsauftrag": pa.name,
			"remarks": _("Rework von der Linie, Auftrag {0}").format(pa.name),
			"items": [terminal._se_zeile(z, s_warehouse=linie.lagerort) for z in zeilen]
			+ [
				terminal._se_zeile(
					{"artikel": rework_artikel, "charge": charge, "menge": kg, "behaelter": behaelter},
					t_warehouse=terminal._ziel_lager(s, rework_artikel),
				)
			],
		}
	)
	se.insert()
	se.submit()
	b = frappe.db.get_value("Batch", charge, ["expiry_date"], as_dict=True)
	return {
		"charge": charge,
		"name": frappe.get_cached_value("Item", rework_artikel, "item_name"),
		"punkt": frappe.get_cached_value("Item", rework_artikel, "kt_entnahmepunkt") or "",
		"menge": kg,
		"behaelter": behaelter,
		"auftrag": pa.name,
		"mhd": formatdate(b.expiry_date) if b.expiry_date else None,
		"buchung": se.name,
	}


# ---------------------------------------------------------------------------
# Palette fertig
# ---------------------------------------------------------------------------


def _verbrauch(pa, artikel_aus, kg, linie):
	"""Verbrauch für kg von artikel_aus laut Linienrezept: erst was für diesen Auftrag auf der Linie liegt
	(Teig vom Kneter), der Rest (Füllung, Glasur, Schokolade, Packmittel) automatisch aus dem Lager bzw.
	Tank, älteste zuerst. Nachgefüllt wird an der Linie nicht gebucht. Gibt (zeilen, hinweise, vom_teig)."""
	from keks_trace import terminal

	vorrat = defaultdict(list)
	ersatz = rework_ersatz()
	for z in bestand(pa.name):
		vorrat[z["artikel"]].append(z)
		for ziel in ersatz.get(z["artikel"], ()):
			vorrat[ziel].append(z)  # Rework am Kneter zugeführt: wird mit dem Teig verbraucht
	for liste in vorrat.values():
		liste.sort(key=lambda z: (z["zugefuehrt"] or now_datetime(), z["charge"]))
	silos = terminal._silo_je_artikel()
	zeilen, hinweise, vom_teig = [], [], False
	for artikel, je in linienrezept(artikel_aus).items():
		bedarf = je * kg
		offen = bedarf
		for z in vorrat.get(artikel, []):
			if offen <= EPS:
				break
			nimm = min(offen, z["menge"])
			if nimm <= EPS:
				continue
			z["menge"] -= nimm  # dieselbe Charge kann für mehrere Zutaten stehen (Rework)
			zeilen.append(
				{
					"artikel": z["artikel"],
					"charge": z["charge"],
					"menge": flt(nimm, 6),
					"lager": linie.lagerort,
				}
			)
			offen -= nimm
			vom_teig = vom_teig or artikel_stufe(artikel) != "Packmittel"
		quellen = (
			[{"code": silos[artikel], "menge": offen}] if artikel in silos else terminal._quellen(artikel)
		)
		for q in quellen:
			if offen <= EPS:
				break
			nimm = min(offen, q["menge"])
			try:
				z = terminal._zeile(q["code"], nimm)
			except frappe.ValidationError:
				continue
			zeilen.append({**z, "menge": flt(nimm, 6)})
			offen -= nimm
		if offen > max(bedarf * 0.005, EPS):
			hinweise.append(
				_("{0}: laut Rezept {1} {3}, im Lager nur {2} {3}. Bestand prüfen.").format(
					frappe.get_cached_value("Item", artikel, "item_name"),
					flt(bedarf, 2),
					flt(bedarf - offen, 2),
					frappe.get_cached_value("Item", artikel, "stock_uom"),
				)
			)
	frappe.local.message_log = []
	return zeilen, hinweise, vom_teig


def palette_fertig(station: str, anzahl: float, einheit: str, palette: str | None = None) -> dict:
	from keks_trace import terminal

	s = _station(station)
	if not s.f_palette_fertig:
		_fehler(_("An der Station {0} werden keine Paletten der Linie gebucht.").format(s.name))
	linie = _linie(s)
	pa = _laufender(s)
	pruefung.pruefe_station_frei(s.name)
	if flt(anzahl) <= EPS:
		_fehler(_("Bitte die Anzahl eingeben."))
	kg = flt(flt(anzahl) * paletten.faktor(pa.artikel, einheit), 6)
	nve = paletten.finde(palette) if palette else None
	if palette and not nve:
		_fehler(_("{0} ist keine Palette.").format(palette))
	if nve:
		paletten._offen(nve)

	zeilen, hinweise, vom_teig = _verbrauch(pa, pa.artikel, kg, linie)
	if not vom_teig:
		_fehler(
			_(
				"Für Auftrag {0} ist noch nichts auf der Linie gebucht. Erst am Kneter die Kübel scannen."
			).format(pa.name)
		)

	vorgabe = los_modul.mhd_vorgabe(pa.kundenauftrag, nowdate())
	if los_modul.format_() == "JWWT":
		charge, _los, _neu = los_modul.tages_charge(pa.artikel, nowdate(), vorgabe)
	else:
		charge = (
			pa.los
			if pa.los and getdate(frappe.db.get_value("Batch", pa.los, "creation")) == getdate()
			else None
		)
		if not charge:
			charge = terminal._neue_charge(pa.artikel, getdate(nowdate()))
			if vorgabe:
				frappe.db.set_value("Batch", charge, "kt_mhd_vorgabe", vorgabe)
	jetzt = now_datetime()
	ausgabe = terminal._se_zeile(
		{"artikel": pa.artikel, "charge": charge, "menge": kg}, t_warehouse=linie.fertiglager
	)
	ausgabe["is_finished_item"] = 1
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Manufacture",
			"purpose": "Manufacture",
			"company": linie.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"kt_produktionsauftrag": pa.name,
			"kt_kundenauftrag": pa.kundenauftrag,
			"items": [terminal._se_zeile(z, s_warehouse=z["lager"]) for z in zeilen] + [ausgabe],
		}
	)
	se.insert()
	se.submit()
	if nve:
		if pa.kundenauftrag:
			frappe.db.set_value("Palette", nve, {"kundenauftrag": pa.kundenauftrag, "kunde": pa.kunde})
		paletten.beladen(nve, charge, anzahl, einheit, s.name, "Verpackung", "Stock Entry", se.name)
	gebucht = flt(pa.gebucht_kg) + kg
	pa.db_set({"gebucht_kg": gebucht, "los": charge})
	if gebucht >= flt(pa.menge_kg) - EPS:
		hinweise.append(_("Auftragsmenge erreicht. Auftrag am Ende beenden."))
	b = frappe.db.get_value(
		"Batch", charge, ["expiry_date", "kt_los", "kt_kennzeichen", "kt_status"], as_dict=True
	)
	return {
		"charge": charge,
		"los": b.kt_los or charge,
		"name": pa.artikelname,
		"anzahl": anzahl,
		"einheit": einheit,
		"menge": kg,
		"palette": nve,
		"mhd": formatdate(b.expiry_date) if b.expiry_date else None,
		"kennzeichen": b.kt_kennzeichen if b.kt_kennzeichen != kennzeichnung.KEINE else None,
		"gesperrt": b.kt_status == "Gesperrt",
		"auftrag": pa.name,
		"gebucht_text": _menge_text(pa.artikel, gebucht),
		"buchung": se.name,
		"verbraucht": [
			{
				"name": frappe.get_cached_value("Item", z["artikel"], "item_name"),
				"charge": z.get("charge") or z.get("silo"),
				"menge": flt(z["menge"], 3),
			}
			for z in zeilen
		],
		"hinweise": hinweise + list(se.flags.kt_fifo_warnungen or []),
	}


# ---------------------------------------------------------------------------
# Auftrag beenden
# ---------------------------------------------------------------------------


def beenden(station: str, auftrag: str | None = None, abbrechen: bool = False) -> dict:
	s = _station(station)
	linie = _linie(s)
	pa = frappe.get_doc("Produktionsauftrag", auftrag or _laufender(s).name)
	if pa.status not in ("Läuft", "Freigegeben"):
		_fehler(_("Auftrag {0} ist bereits {1}.").format(pa.name, pa.status))
	rest = bestand(pa.name)
	buchung = None
	if rest:
		jetzt = now_datetime()
		se = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": LINIENREST,
				"purpose": "Material Issue",
				"company": linie.company,
				"set_posting_time": 1,
				"posting_date": jetzt.date(),
				"posting_time": jetzt.time().strftime("%H:%M:%S"),
				"kt_station": s.name,
				"kt_produktionsauftrag": pa.name,
				"remarks": _("Rest auf der Linie bei Auftragsende {0}").format(pa.name),
				"items": [
					{
						"item_code": z["artikel"],
						"qty": z["menge"],
						"transfer_qty": z["menge"],
						"uom": frappe.get_cached_value("Item", z["artikel"], "stock_uom"),
						"stock_uom": frappe.get_cached_value("Item", z["artikel"], "stock_uom"),
						"conversion_factor": 1,
						"s_warehouse": linie.lagerort,
						"use_serial_batch_fields": 1,
						"batch_no": z["charge"],
					}
					for z in rest
				],
			}
		)
		se.insert()
		se.submit()
		buchung = se.name
	pa.db_set({"status": "Abgebrochen" if abbrechen else "Fertig", "beendet_am": now_datetime()})
	for st in frappe.get_all("Terminal Station", {"aktueller_auftrag": pa.name}, pluck="name"):
		frappe.db.set_value("Terminal Station", st, "aktueller_auftrag", None)
	return {
		"auftrag": pa.name,
		"status": pa.status,
		"rest": [
			{
				"name": frappe.get_cached_value("Item", z["artikel"], "item_name"),
				"charge": z["charge"],
				"menge": flt(z["menge"], 3),
			}
			for z in rest
		],
		"buchung": buchung,
	}


# ---------------------------------------------------------------------------
# Packstation (nur anzeigen)
# ---------------------------------------------------------------------------


def packstation(station: str) -> dict:
	"""Was die Packstation gerade einrichten muss: Auftrag, Anlage, Beutel je Karton, Los, MHD."""
	from keks_trace.genealogie import daten_berechnen

	s = _station(station)
	_linie(s)
	name = frappe.db.get_value("Terminal Station", s.name, "aktueller_auftrag")
	if not name:
		return {"auftrag": None}
	i = info(name)
	eingaenge = [(z["charge"], z["artikel"], z["menge"]) for z in bestand(name)]
	los = los_modul.jwwt(nowdate()) if los_modul.format_() == "JWWT" else None
	werte = daten_berechnen(i["artikel"], eingaenge, nowdate(), None, "-") if eingaenge else {}
	if not werte.get("kt_backtag"):
		werte = daten_berechnen(i["artikel"], [], nowdate(), None, "-")
	mhd = werte.get("expiry_date")
	ean = frappe.db.get_value("Item Barcode", {"parent": i["artikel"], "uom": "Karton"}, "barcode")
	return {
		**i,
		"los_vorschau": los,
		"mhd_vorschau": formatdate(mhd) if mhd else None,
		"ean_karton": ean,
	}
