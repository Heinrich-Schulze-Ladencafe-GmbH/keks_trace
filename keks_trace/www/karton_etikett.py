"""Kartonlabel der Packstation: Artikel, Inhalt, Los, MHD, EAN des Kartons; N Stück für den laufenden Auftrag."""

import frappe
from frappe.utils import cint

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + frappe.request.full_path
		raise frappe.Redirect
	from keks_trace import linienbuchung

	station = frappe.form_dict.get("station")
	frappe.has_permission("Produktionsauftrag", "read", throw=True)
	d = linienbuchung.packstation(station)
	if not d.get("auftrag"):
		frappe.throw("An dieser Station läuft kein Produktionsauftrag.")
	beutel = next((e for e in d["einheiten"] if e["einheit"] == "Beutel"), None)
	gramm = round(beutel["faktor"] * 1000) if beutel else None
	context.d = d
	context.inhalt = (
		f"{d['beutel_je_karton']} x {gramm} g" if d.get("beutel_je_karton") and gramm else d["name"]
	)
	context.anzahl = max(1, min(cint(frappe.form_dict.get("anzahl") or 1), 500))
	context.ean = d.get("ean_karton")
	context.drucken = frappe.form_dict.get("druck") == "1"
	context.title = "Kartonlabel " + d["name"]
