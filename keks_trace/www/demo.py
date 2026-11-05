"""Drehbuch der Demo mit dem Stand von heute (demo/tag.py). Lesen für alle mit Leserecht auf Chargen;
vorbereiten nur System Manager auf einem Demosystem."""

import frappe

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + frappe.request.full_path
		raise frappe.Redirect
	frappe.has_permission("Batch", "read", throw=True)
	context.title = "Demo"
	context.darf = int("System Manager" in frappe.get_roles())
