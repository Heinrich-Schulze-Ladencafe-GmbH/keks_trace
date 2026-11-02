"""Audit-Ansicht für Handy und Tablet: Palette, Los oder Behälter scannen und zeigen, was es ist, wo es war und
woraus es besteht. Nur lesen, keine Station nötig. Daten über terminal.info / akte / herkunft (Rechte wie dort)."""

import frappe

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + frappe.request.full_path
		raise frappe.Redirect
	frappe.has_permission("Batch", "read", throw=True)
	context.title = "Akte"
	context.code = frappe.form_dict.get("code") or ""
