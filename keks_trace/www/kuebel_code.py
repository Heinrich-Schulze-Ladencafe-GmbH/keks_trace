"""Kübel-Codes zum Einlasern: Nummer groß lesbar + Data Matrix, je Kübel als SVG zum Speichern."""

import frappe

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + frappe.request.full_path
		raise frappe.Redirect
	frappe.has_permission("Produkttraeger", "read", throw=True)
	codes = [c.strip() for c in (frappe.form_dict.get("codes") or "").split(",") if c.strip()]
	if not codes:
		codes = frappe.get_all(
			"Produkttraeger", filters={"typ": "Teigbehälter"}, pluck="code", order_by="code"
		)
	context.codes = codes
	context.title = "Kübel-Codes"
