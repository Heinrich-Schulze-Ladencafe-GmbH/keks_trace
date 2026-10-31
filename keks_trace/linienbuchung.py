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
		"zutaten": zutaten,
		"kuebel": kuebel_vorschlag(
			[z["artikel"] for z in zutaten if z["stufe"] in ("Teig veredelt", "Grundteig")]
		),
	}


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
	if artikel not in rezept:
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
# Palette fertig
# ---------------------------------------------------------------------------


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

	# Verbrauch laut Linienrezept, nur Ware dieses Auftrags, älteste Zuführung zuerst
	vorrat = defaultdict(list)
	for z in bestand(pa.name):
		vorrat[z["artikel"]].append(z)
	zeilen, hinweise = [], []
	for artikel, je in linienrezept(pa.artikel).items():
		bedarf = je * kg
		offen = bedarf
		for z in vorrat.get(artikel, []):
			if offen <= EPS:
				break
			nimm = min(offen, z["menge"])
			if nimm <= EPS:
				continue
			zeilen.append((artikel, z["charge"], flt(nimm, 6)))
			offen -= nimm
		if offen > max(bedarf * 0.005, EPS) and artikel_stufe(artikel) != "Packmittel":
			hinweise.append(
				_(
					"{0}: laut Rezept {1} {3}, auf der Linie gebucht nur {2} {3}. Zuführen am Former/Nachfüllen prüfen."
				).format(
					frappe.get_cached_value("Item", artikel, "item_name"),
					flt(bedarf, 2),
					flt(bedarf - offen, 2),
					frappe.get_cached_value("Item", artikel, "stock_uom"),
				)
			)
	if not any(artikel_stufe(a) != "Packmittel" for a, _c, _m in zeilen):
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
			"items": [
				terminal._se_zeile({"artikel": a, "charge": c, "menge": m}, s_warehouse=linie.lagerort)
				for a, c, m in zeilen
			]
			+ [ausgabe],
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
			{"name": frappe.get_cached_value("Item", a, "item_name"), "charge": c, "menge": flt(m, 3)}
			for a, c, m in zeilen
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
