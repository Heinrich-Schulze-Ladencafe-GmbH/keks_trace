"""Linie: Zuführen, also Kübel einkippen und Gebinde nachfüllen."""

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime

from keks_trace import buchung, kennzeichnung
from keks_trace.linienbuchung.auftrag import info, kuebel_vorschlag
from keks_trace.linienbuchung.basis import EPS, _fehler, _laufender, _linie, _station
from keks_trace.linienbuchung.rework import _pruefe_rework_anteil, _rework_ziel
from keks_trace.linienbuchung.rezept import linienrezept
from keks_trace.utils import artikel_stufe


def zufuehren(station: str, code: str, menge: float | None = None, fefo_grund: str | None = None) -> dict:
	"""Kübel, Gebinde oder Tank an die Linie. fefo_grund: Pflicht, wenn ein Rohstoff/Packmittel mit späterem
	MHD zugeführt wird, obwohl ein früheres im Lager liegt (wie beim Herstellen)."""
	from keks_trace.silo import bestand as silo_bestand

	s = _station(station)
	if not s.f_linie:
		_fehler(_("An der Station {0} wird nicht an die Linie gegeben.").format(s.name))
	linie = _linie(s)
	pa = _laufender(s)
	rezept = linienrezept(pa.artikel)
	r = buchung.aufloesen(code)
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
		buchung._pruefe_charge(charge, artikel)
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
	fefo = None
	if r["typ"] != "silo":
		fefo = buchung._pruefe_fefo(
			[{"artikel": artikel, "charge": r["charge"], "typ": r["typ"], "einheit": uom,
			  "name": frappe.get_cached_value("Item", artikel, "item_name")}],
			fefo_grund,
		)  # fmt: skip
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
			"kt_fefo_abweichung": fefo,
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
