from frappe.model.document import Document


class Allergengruppe(Document):
	def validate(self):
		if self.allergene:
			teile = [a.strip() for a in self.allergene.replace(";", ",").split(",") if a.strip()]
			self.allergene = ", ".join(teile)
