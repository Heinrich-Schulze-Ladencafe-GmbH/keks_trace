import frappe
from frappe import _
from frappe.model.document import Document


class Silo(Document):
	def validate(self):
		if not frappe.get_cached_value("Item", self.artikel, "has_batch_no"):
			frappe.throw(_("Artikel {0} muss chargenpflichtig sein.").format(self.artikel))
		frappe.cache.delete_value("kt_silo_lager")

	def on_trash(self):
		frappe.cache.delete_value("kt_silo_lager")
