"""Linie: Palette fertig, Auftrag beenden, Packstation."""

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate, now_datetime, nowdate

from keks_trace import buchung, haccp, kennzeichnung
from keks_trace import los as los_modul
from keks_trace import palette as paletten
from keks_trace.linienbuchung.auftrag import info
from keks_trace.linienbuchung.basis import EPS, LINIENREST, _fehler, _laufender, _linie, _menge_text, _station
from keks_trace.linienbuchung.rezept import _verbrauch, bestand


def palette_fertig(station: str, anzahl: float, einheit: str, palette: str | None = None) -> dict:
	s = _station(station)
	if not s.f_palette_fertig:
		_fehler(_("An der Station {0} werden keine Paletten der Linie gebucht.").format(s.name))
	linie = _linie(s)
	pa = _laufender(s)
	haccp.pruefe_station_frei(s.name)
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
			charge = buchung._neue_charge(pa.artikel, getdate(nowdate()))
			if vorgabe:
				frappe.db.set_value("Batch", charge, "kt_mhd_vorgabe", vorgabe)
	jetzt = now_datetime()
	ausgabe = buchung._se_zeile(
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
			"items": [buchung._se_zeile(z, s_warehouse=z["lager"]) for z in zeilen] + [ausgabe],
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
