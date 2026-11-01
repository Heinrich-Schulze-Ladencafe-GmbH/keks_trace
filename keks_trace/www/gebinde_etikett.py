import frappe
import pyqrcode

from keks_trace import etiketten

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + frappe.request.full_path
		raise frappe.Redirect
	liste = etiketten.gebinde(frappe.form_dict.get("codes") or "")
	for e in liste:
		e["qr"] = _svg(pyqrcode.create(e["code"], error="M"))
	context.etiketten = liste
	context.drucken = frappe.form_dict.get("druck") == "1"
	context.title = "Gebinde-Etiketten"


def _svg(qr):
	import io

	puffer = io.BytesIO()
	qr.svg(puffer, scale=4, quiet_zone=1, xmldecl=False, svgns=True)
	return puffer.getvalue().decode()
