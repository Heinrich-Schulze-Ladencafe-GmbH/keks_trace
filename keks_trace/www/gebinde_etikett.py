import frappe
import pyqrcode
from frappe.utils import formatdate

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + frappe.request.full_path
		raise frappe.Redirect
	codes = [c.strip() for c in (frappe.form_dict.get("codes") or "").split(",") if c.strip()]
	etiketten = []
	for code in codes[:200]:
		frappe.has_permission("Produkttraeger", "read", code, throw=True)
		t = frappe.get_doc("Produkttraeger", code)
		b = (
			frappe.db.get_value(
				"Batch", t.charge, ["item", "item_name", "expiry_date", "supplier"], as_dict=True
			)
			if t.charge
			else frappe._dict()
		)
		eingang = frappe.db.get_value("Traeger Belegung", {"traeger": code}, "von", order_by="creation asc")
		qr = pyqrcode.create(code, error="M")
		etiketten.append(
			{
				"code": code,
				"art": t.gebindeart or t.typ,
				"artikel": b.get("item"),
				"name": b.get("item_name"),
				"charge": t.charge,
				"mhd": formatdate(b.expiry_date) if b.get("expiry_date") else "",
				"lieferant": b.get("supplier") or "",
				"menge": t.menge,
				"einheit": frappe.get_cached_value("Item", b.item, "stock_uom") if b.get("item") else "",
				"eingang": formatdate(eingang) if eingang else "",
				"qr": _svg(qr),
			}
		)
	context.etiketten = etiketten
	context.drucken = frappe.form_dict.get("druck") == "1"
	context.title = "Gebinde-Etiketten"


def _svg(qr):
	import io

	puffer = io.BytesIO()
	qr.svg(puffer, scale=4, quiet_zone=1, xmldecl=False, svgns=True)
	return puffer.getvalue().decode()
