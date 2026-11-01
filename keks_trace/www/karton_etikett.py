"""Kartonlabel der Packstation: Artikel, Inhalt, Los, MHD, EAN des Kartons; N Stück für den laufenden Auftrag."""

import frappe
from frappe.utils import cint

from keks_trace import etiketten

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + frappe.request.full_path
		raise frappe.Redirect
	d = etiketten.karton(frappe.form_dict.get("station"))
	context.d = d
	context.inhalt = d["inhalt"]
	context.anzahl = max(1, min(cint(frappe.form_dict.get("anzahl") or 1), etiketten.MAX_KARTON))
	context.ean = d.get("ean")
	context.drucken = frappe.form_dict.get("druck") == "1"
	context.title = "Kartonlabel " + d["name"]
