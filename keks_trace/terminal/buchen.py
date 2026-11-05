"""Buchen am Terminal: Herstellen, Rework, Vorrat am Tisch anbrechen."""

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate, now_datetime, nowdate

from keks_trace import haccp, kennzeichnung
from keks_trace import los as los_modul
from keks_trace import palette as paletten
from keks_trace.anfrage import einmalig
from keks_trace.terminal.basis import (
	EPS,
	_darf,
	_fehler,
	_liste,
	_meldungen,
	_neue_charge,
	_se_zeile,
	_station,
	_vorraete,
)
from keks_trace.terminal.bestand import _pruefe_charge, _reserviert, _verkaufslager, charge_lager
from keks_trace.terminal.einwaage import _fuer_auftrag, _pruefe_rezept, rezept
from keks_trace.terminal.scan import aufloesen
from keks_trace.terminal.zutaten import _pruefe_fefo, _zeile
from keks_trace.utils import allergene, artikel_stufe, versandfaehig


@frappe.whitelist()
@einmalig
def anbrechen(station: str, code: str) -> dict:
	"""Neuen Karton / neue Rolle an den Tisch: die Charge kommt in den Vorrat und wird ab jetzt verbraucht."""
	s = _station(station)
	r = aufloesen(code)
	charge = r.get("charge")
	if r["typ"] != "charge" or not charge:
		_fehler(_("Bitte das Etikett des Kartons bzw. der Rolle scannen (Charge)."))
	artikel = frappe.db.get_value("Batch", charge, "item")
	vorrat = _vorraete().get(artikel)
	if not vorrat:
		_fehler(
			_("Für {0} ist kein Vorrat am Tisch eingerichtet.").format(
				frappe.get_cached_value("Item", artikel, "item_name")
			)
		)
	_pruefe_charge(charge, artikel)
	ziel = frappe.db.get_value("Silo", vorrat, "warehouse")
	vorrat_lager = set(frappe.get_all("Silo", pluck="warehouse")) | _verkaufslager()
	quellen = {w: m for w, m in charge_lager(charge).items() if w not in vorrat_lager}
	if not quellen:
		_fehler(_("Von Charge {0} ist nichts mehr im Lager.").format(charge))
	jetzt = now_datetime()
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Transfer",
			"purpose": "Material Transfer",
			"company": s.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"items": [
				_se_zeile({"artikel": artikel, "charge": charge, "menge": m}, w, ziel)
				for w, m in quellen.items()
			],
		}
	)
	se.insert()
	se.submit()
	return {
		"vorrat": vorrat,
		"charge": charge,
		"menge": flt(sum(quellen.values()), 3),
		"name": frappe.get_cached_value("Item", artikel, "item_name"),
		"buchung": se.name,
	}


def _ziel_lager(s, artikel):
	silo = frappe.db.get_value(
		"Silo", {"artikel": artikel, "aktiv": 1}, "warehouse", order_by="creation desc"
	)
	if silo:
		return silo
	lager = s.fertiglager if versandfaehig(artikel) else s.produktionslager
	if not lager:
		_fehler(_("An der Station {0} ist kein Ziellager eingerichtet.").format(s.name))
	return lager


def _ziel_behaelter(code):
	if not code:
		return None
	r = aufloesen(code)
	if r["typ"] != "behaelter":
		_fehler(_("{0} ist kein Behälter.").format(code))
	if r["status"] == "Reinigung":
		_fehler(
			_("Behälter {0} ist zur Reinigung. Erst reinigen und im Info-Scan als gereinigt melden.").format(
				code
			)
		)
	if r["status"] == "Gesperrt":
		_fehler(_("Behälter {0} ist gesperrt.").format(code))
	if r["behaelter_typ"] == "Gebinde":
		_fehler(_("{0} ist ein Gebinde vom Wareneingang, kein Zielbehälter.").format(code))
	if r.get("charge"):
		_fehler(_("Behälter {0} ist noch mit {1} belegt.").format(code, r["charge"]))
	return code


@frappe.whitelist()
def vorschau(
	station: str, ziel: str, zeilen, kundenauftrag: str | None = None, mhd: str | None = None
) -> dict:
	"""Los und MHD, bevor gebucht wird (zum Einstellen des Beuteldruckers)."""
	from keks_trace.genealogie import daten_berechnen

	_station(station)
	if artikel_stufe(ziel) != "Fertigware":
		return {}
	eingaenge = []
	for z in _liste(zeilen):
		r = aufloesen(z["code"])
		if r.get("charge") and r["typ"] != "silo":
			eingaenge.append((r["charge"], r["artikel"], flt(z.get("menge"))))
	charge, los = None, None
	vorgabe = los_modul.mhd_vorgabe(kundenauftrag, nowdate(), mhd)
	if los_modul.format_() == "JWWT":
		los = los_modul.jwwt(nowdate())
		name = f"{ziel}-{getdate(nowdate()).isocalendar()[0]}-{los}"
		if vorgabe:
			name += "-M" + getdate(vorgabe).strftime("%y%m%d")
		charge = name if frappe.db.exists("Batch", name) else None
	werte = daten_berechnen(ziel, eingaenge, nowdate(), charge, "-")
	voll = werte.get("expiry_date")
	vorher = frappe.db.get_value("Batch", charge, "expiry_date") if charge else None
	mhd = min(voll, vorgabe) if voll and vorgabe else voll
	ziel_k = kennzeichnung.artikel_kennzeichen(ziel)
	return {
		"kennzeichen": [k for k in kennzeichnung.ALLE if k in ziel_k],
		"oeko_nr": frappe.db.get_single_value("Keks Trace Einstellungen", "oeko_kontrollnummer")
		if kennzeichnung.BIO in ziel_k
		else None,
		"los": los,
		"los_vorhanden": bool(charge),
		"mhd": formatdate(mhd) if mhd else None,
		"mhd_sinkt": bool(vorher and mhd and getdate(mhd) < getdate(vorher)),
		"mhd_bisher": formatdate(vorher) if vorher else None,
		"mhd_voll": formatdate(voll) if voll else None,
		"mhd_gekuerzt": bool(vorgabe and voll and vorgabe < getdate(voll)),
		"mhd_iso": str(mhd) if mhd else None,
	}


@frappe.whitelist()
@einmalig
def herstellen(
	station: str,
	ziel: str,
	zeilen,
	ausbringung: float | None = None,
	ziel_behaelter: str | None = None,
	anzahl: float | None = None,
	einheit: str | None = None,
	kundenauftrag: str | None = None,
	pruefwerte=None,
	mhd: str | None = None,
	fefo_grund: str | None = None,
	sollmenge: float | None = None,
	rezept_grund: str | None = None,
) -> dict:
	"""Fertigung buchen: Zutaten (gescannt) -> neue Charge des Ziels, optional in einen Behälter.

	Fertigware: Ausbringung als Anzahl + Einheit (Karton/Beutel); ziel_behaelter darf eine Palette sein.
	fefo_grund: Pflicht, wenn ein Rohstoff/Packmittel mit späterem MHD genommen wird, obwohl ein früheres
	im Lager liegt (FEFO); wird mit der Buchung gespeichert.
	sollmenge / rezept_grund: Sollmenge vom Teigmacher; weicht eine Zutat über die Toleranz ab, ist ein Grund
	Pflicht (Einstellung), siehe _pruefe_rezept.
	"""
	s = _station(station)
	r = rezept(ziel, station=s.name)
	_darf(s, "herstellen")
	haccp.pruefe_station_frei(s.name)
	if r["stufe"] not in s.stufen_liste():
		_fehler(_("{0} wird nicht an der Station {1} hergestellt.").format(r["name"], s.name))
	linie = frappe.get_cached_value("Item", ziel, "kt_linie")
	if s.linie and linie != s.linie and s.typ != "Verpackungs-PC":
		_fehler(_("{0} gehört nicht zur Linie {1}.").format(r["name"], s.linie))
	erlaubt = {z["artikel"] for z in r["zutaten"]}
	eingaenge = [_zeile(z["code"], z["menge"], ziel, erlaubt) for z in _liste(zeilen)]
	if not eingaenge:
		_fehler(_("Keine Zutaten gescannt."))
	fefo = _pruefe_fefo(eingaenge, fefo_grund)
	rezept_abw = _pruefe_rezept(ziel, sollmenge, eingaenge, rezept_grund)
	pruef_ergebnisse = haccp.bei_buchung(haccp.HERSTELLEN, ziel, pruefwerte, s.name)
	haccp.verweigern_herstellen(pruef_ergebnisse, s.name, _("Herstellen {0}").format(r["name"]))

	summe = sum(
		z["menge"]
		for z in eingaenge
		if z.get("einheit", r["einheit"]) == r["einheit"] and artikel_stufe(z["artikel"]) != "Packmittel"
	)
	if flt(anzahl) > EPS and einheit:
		ausbringung = flt(flt(anzahl) * paletten.faktor(ziel, einheit), 6)
	else:
		anzahl, einheit = None, None
	ausbringung = flt(ausbringung) or flt(summe * r["ausbeute"], 3)
	if kundenauftrag and not _fuer_auftrag(kundenauftrag, ziel):
		_fehler(_("{0} ist im Kundenauftrag {1} nicht bestellt.").format(ziel, kundenauftrag))
	for z in eingaenge:  # für einen anderen Auftrag hergestellte Ware bleibt bei ihm
		reserviert = _reserviert(z.get("charge"))
		if reserviert and reserviert != kundenauftrag:
			_fehler(
				_("{0} ({1}) ist für Kundenauftrag {2} gemacht und dort reserviert.").format(
					z["name"], z["charge"], reserviert
				)
			)
	palette = paletten.finde(ziel_behaelter) if ziel_behaelter else None
	if palette and not versandfaehig(ziel):
		_fehler(_("Auf eine Palette kommen nur Fertigware und lose Ware im Karton."))
	behaelter = None if palette else _ziel_behaelter(ziel_behaelter)
	if palette:
		paletten._offen(palette)

	# Kneter an der Linie: der veredelte Teig geht direkt in den Former, also auf die Linie zum laufenden Auftrag
	linien_auftrag, ziel_lager = None, None
	if s.f_linie:
		from keks_trace import linienbuchung

		linien_auftrag = linienbuchung._laufender(s)
		if ziel not in linienbuchung.linienrezept(linien_auftrag.artikel):
			_fehler(_("{0} gehört nicht zu {1}.").format(r["name"], linien_auftrag.artikelname))
		ziel_lager = frappe.get_cached_value("Linie", s.linie, "lagerort")
		behaelter = None

	vorgabe = los_modul.mhd_vorgabe(kundenauftrag, nowdate(), mhd) if r["stufe"] == "Fertigware" else None
	if r["stufe"] == "Fertigware" and los_modul.format_() == "JWWT":
		charge, _los, _neu = los_modul.tages_charge(ziel, nowdate(), vorgabe)
	else:
		charge = _neue_charge(ziel, getdate(nowdate()))
		if vorgabe:
			frappe.db.set_value("Batch", charge, "kt_mhd_vorgabe", vorgabe)
	if kundenauftrag and r["stufe"] != "Fertigware":
		# Vorstufe für einen Auftrag (z. B. garniertes Herz): reserviert, bis der Auftrag erledigt ist
		frappe.db.set_value("Batch", charge, "kt_kundenauftrag", kundenauftrag)
	jetzt = now_datetime()
	ausgabe = _se_zeile(
		{"artikel": ziel, "charge": charge, "menge": ausbringung, "behaelter": behaelter},
		t_warehouse=ziel_lager or _ziel_lager(s, ziel),
	)
	ausgabe["is_finished_item"] = 1
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Manufacture",
			"purpose": "Manufacture",
			"company": s.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"kt_kundenauftrag": kundenauftrag,
			"kt_produktionsauftrag": linien_auftrag.name if linien_auftrag else None,
			"kt_fefo_abweichung": fefo,
			"kt_rezept_abweichung": rezept_abw,
			"items": [_se_zeile(z, s_warehouse=z["lager"]) for z in eingaenge] + [ausgabe],
		}
	)
	se.insert()
	se.submit()
	if palette and kundenauftrag:
		frappe.db.set_value(
			"Palette",
			palette,
			{
				"kundenauftrag": kundenauftrag,
				"kunde": frappe.db.get_value("Sales Order", kundenauftrag, "customer"),
			},
		)
	if palette:
		paletten.beladen(
			palette, charge, anzahl or ausbringung, einheit or frappe.get_cached_value("Item", ziel, "stock_uom"),
			s.name, "Verpackung", "Stock Entry", se.name,
		)  # fmt: skip

	hinweise = haccp.nach_buchung(pruef_ergebnisse, s.name, charge, se.name)
	hinweise += list(se.flags.kt_fifo_warnungen or [])
	verfall = frappe.db.get_value("Batch", charge, "expiry_date")
	if mhd and verfall and getdate(verfall) < getdate(mhd):
		hinweise.append(
			_("MHD {0} geht nicht, laut Rohstoffen nur bis {1}.").format(formatdate(mhd), formatdate(verfall))
		)
	if se.flags.kt_fehlende_zutaten:
		hinweise.append(_("Laut Rezept nicht gescannt: {0}").format(", ".join(se.flags.kt_fehlende_zutaten)))
	b = frappe.db.get_value(
		"Batch", charge, ["expiry_date", "kt_status", "kt_los", "kt_kennzeichen"], as_dict=True
	)
	return {
		"charge": charge,
		"los": b.kt_los,
		"kennzeichen": b.kt_kennzeichen if b.kt_kennzeichen != kennzeichnung.KEINE else None,
		"artikel": ziel,
		"name": r["name"],
		"menge": ausbringung,
		"anzahl": anzahl,
		"einheit": einheit,
		"behaelter": behaelter,
		"palette": palette,
		"kundenauftrag": kundenauftrag,
		"mhd": formatdate(b.expiry_date) if b.expiry_date else None,
		"gesperrt": b.kt_status == "Gesperrt",
		"buchung": se.name,
		"hinweise": [h for h in dict.fromkeys(hinweise + _meldungen())],
	}


@frappe.whitelist()
@einmalig
def rework_erfassen(
	station: str, quelle: str, menge: float, rework_artikel: str, ziel_behaelter: str | None = None
) -> dict:
	"""Teigreste oder Bruch in einen Rework-Behälter umfüllen (neue Rework-Charge)."""
	s = _station(station)
	_darf(s, "rework")
	if artikel_stufe(rework_artikel) != "Rework":
		_fehler(_("{0} ist kein Rework-Artikel.").format(rework_artikel))
	q = _zeile(quelle, menge)
	if q["typ"] == "silo":
		_fehler(_("Aus einem Silo kann kein Rework erfasst werden."))

	zuviel = allergene(frappe.get_cached_value("Item", q["artikel"], "kt_allergengruppe")) - allergene(
		frappe.get_cached_value("Item", rework_artikel, "kt_allergengruppe")
	)
	if zuviel:
		_fehler(
			_(
				"{0} enthält Allergene, die {1} nicht hat: {2}. Bitte den passenden Rework-Behälter wählen."
			).format(q["name"], rework_artikel, ", ".join(sorted(a.capitalize() for a in zuviel)))
		)
	behaelter = _ziel_behaelter(ziel_behaelter)
	charge = _neue_charge(rework_artikel, getdate(nowdate()))
	jetzt = now_datetime()
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Repack",
			"purpose": "Repack",
			"company": s.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"items": [
				_se_zeile(q, s_warehouse=q["lager"]),
				_se_zeile(
					{
						"artikel": rework_artikel,
						"charge": charge,
						"menge": q["menge"],
						"behaelter": behaelter,
					},
					t_warehouse=_ziel_lager(s, rework_artikel),
				),
			],
		}
	)
	se.insert()
	se.submit()
	b = frappe.db.get_value("Batch", charge, ["expiry_date"], as_dict=True)
	return {
		"charge": charge,
		"name": frappe.get_cached_value("Item", rework_artikel, "item_name"),
		"menge": q["menge"],
		"behaelter": behaelter,
		"mhd": formatdate(b.expiry_date) if b.expiry_date else None,
		"buchung": se.name,
		"hinweise": _meldungen(),
	}
