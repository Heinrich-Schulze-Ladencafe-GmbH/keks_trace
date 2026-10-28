import frappe
from frappe import _
from frappe.model.document import Document


class Produkttraeger(Document):
	def validate(self):
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
