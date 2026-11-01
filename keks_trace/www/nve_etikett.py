import frappe

from keks_trace import palette

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + frappe.request.full_path
		raise frappe.Redirect
	nve = palette.finde(frappe.form_dict.get("nve") or "")
	if not nve:
		frappe.throw("Palette nicht gefunden.", frappe.DoesNotExistError)
	frappe.has_permission("Palette", "read", nve, throw=True)
	context.e = palette.etikett(nve)
	context.drucken = frappe.form_dict.get("druck") == "1"
	if context.drucken:
		# Festhalten, welchen Inhalt das gedruckte Etikett zeigt (Hinweis „neu drucken“ bei Änderung)
		palette.etikett_gedruckt(nve)
		frappe.db.commit()
	context.logo = frappe.db.get_single_value("Keks Trace Einstellungen", "etikett_logo")
	context.title = "NVE " + nve
