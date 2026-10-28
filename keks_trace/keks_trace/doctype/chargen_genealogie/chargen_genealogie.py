from frappe.model.document import Document


class ChargenGenealogie(Document):
	"""Wird nur vom Buchungs-Hook geschrieben. Korrekturen laufen über Storno der Lagerbuchung."""
