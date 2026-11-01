import frappe

from keks_trace import etiketten

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + frappe.request.full_path
		raise frappe.Redirect
	context.etiketten = etiketten.gebinde(frappe.form_dict.get("codes") or "")
	context.drucken = frappe.form_dict.get("druck") == "1"
	context.title = "Gebinde-Etiketten"
