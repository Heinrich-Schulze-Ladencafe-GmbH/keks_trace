import frappe
from frappe.sessions import get_csrf_token

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/terminal"
		raise frappe.Redirect
	context.title = "Keks Trace Terminal"
	context.nutzer = frappe.session.user
	context.kt_csrf = get_csrf_token()
