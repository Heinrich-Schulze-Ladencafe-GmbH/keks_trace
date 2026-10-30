import frappe
from frappe import _
from frappe.model.document import Document


class Palette(Document):
	def on_trash(self):
		if frappe.db.exists("Paletten Bewegung", {"palette": self.name}):
			frappe.throw(_("Palette {0} hat Bewegungen und kann nicht gelöscht werden.").format(self.name))
