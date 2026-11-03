import frappe
from frappe import _
from frappe.model.document import Document

# Arten, die schon gebaut sind; die übrigen (Nummern vom Kunden) folgen in einem späteren Schritt
GEBAUT = ("Eigener",)


class NVENummernkreis(Document):
	def validate(self):
		basis = "".join(c for c in (self.basisnummer or "") if c.isdigit())
		if self.basisnummer and (basis != self.basisnummer.strip() or not 7 <= len(basis) <= 10):
			frappe.throw(_("Die GS1-Basisnummer muss aus 7 bis 10 Ziffern bestehen."))
		if self.reserveziffer and not (len(self.reserveziffer) == 1 and self.reserveziffer.isdigit()):
			frappe.throw(_("Die Reserveziffer ist eine Ziffer 0 bis 9."))
		if self.standard and frappe.db.exists("NVE Nummernkreis", {"standard": 1, "name": ["!=", self.name]}):
			frappe.throw(_("Es gibt schon einen Standard-Nummernkreis. Dort zuerst den Haken entfernen."))
