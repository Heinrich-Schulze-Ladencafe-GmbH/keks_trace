import frappe
from frappe import _
from frappe.model.document import Document


class Produkttraeger(Document):
	def validate(self):
		if self.is_new():
			from keks_trace.zpl import DM_ZEICHEN

			# Der Code steht als Data Matrix auf dem Etikett und wird gescannt: keine Leer- und Sonderzeichen
			if not DM_ZEICHEN.match(self.code or ""):
				frappe.throw(_("Code bitte nur aus Buchstaben, Ziffern und - . / (höchstens 60 Zeichen)."))
		vorher = self.get_doc_before_save()
		if not vorher or self.flags.kt_vom_system:
			return
		# Belegt/Frei setzt nur das System beim Buchen; ein Mensch darf sperren oder zur Reinigung geben.
		if self.status != vorher.status and "Belegt" in (self.status, vorher.status):
			frappe.throw(
				_("Der Status 'Belegt' wird beim Buchen gesetzt und kann nicht von Hand geändert werden.")
			)
		if self.status != vorher.status and self.status in ("Reinigung", "Gesperrt") and vorher.charge:
			frappe.throw(_("Behälter {0} enthält noch Charge {1}.").format(self.code, vorher.charge))
