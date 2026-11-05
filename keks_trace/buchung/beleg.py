"""Buchung: neue Charge, Zeilen der Lagerbuchung, Ziellager und Zielbehälter."""

import frappe
from frappe import _
from frappe.utils import now_datetime

from keks_trace.buchung.basis import _fehler
from keks_trace.buchung.scan import aufloesen
from keks_trace.utils import artikel_stufe, versandfaehig


def _neue_charge(artikel, herstelldatum=None, charge_id=None, lieferant=None, verfall=None):
	if not charge_id:
		# Fertigware bekommt eine kurze Los-Nummer (passt auf Beutel und ins GS1-Etikett)
		kurz = artikel_stufe(artikel) == "Fertigware"
		praefix = ("L" if kurz else f"{artikel}-") + f"{now_datetime().strftime('%y%m%d')}-"
		n = frappe.db.count("Batch", {"name": ["like", praefix + "%"]}) + 1
		while frappe.db.exists("Batch", f"{praefix}{n:02d}"):
			n += 1
		charge_id = f"{praefix}{n:02d}"
	werte = {
		"doctype": "Batch",
		"item": artikel,
		"batch_id": charge_id,
		"manufacturing_date": herstelldatum,
		"supplier": lieferant,
	}
	if verfall:
		werte["expiry_date"] = verfall
	if artikel_stufe(artikel) == "Fertigware":
		werte["kt_los"] = charge_id
	return frappe.get_doc(werte).insert().name


def _se_zeile(z, s_warehouse=None, t_warehouse=None):
	uom = frappe.get_cached_value("Item", z["artikel"], "stock_uom")
	return {
		"item_code": z["artikel"],
		"qty": z["menge"],
		"transfer_qty": z["menge"],
		"uom": uom,
		"stock_uom": uom,
		"conversion_factor": 1,
		"s_warehouse": s_warehouse,
		"t_warehouse": t_warehouse,
		"use_serial_batch_fields": 1,
		"batch_no": z.get("charge"),
		"kt_traeger": z.get("behaelter"),
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
