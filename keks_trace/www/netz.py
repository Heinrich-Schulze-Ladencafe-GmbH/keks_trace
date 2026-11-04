"""Netzbild der Rückverfolgung (Büro, QS, Audit am großen Bildschirm oder Surface). Nur lesen.
Daten über keks_trace.netz.netz und keks_trace.netz.details (Rechte: Charge lesen)."""

import frappe

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + frappe.request.full_path
		raise frappe.Redirect
	frappe.has_permission("Batch", "read", throw=True)
	context.title = "Rückverfolgung"
	context.code = frappe.form_dict.get("code") or ""
