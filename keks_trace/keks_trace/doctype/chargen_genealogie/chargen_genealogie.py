from frappe.model.document import Document

from keks_trace.schutz import nur_einfuegen_on_trash, nur_einfuegen_validate


class ChargenGenealogie(Document):
	"""Kante der Chargen-Genealogie. Wird nur beim Buchen geschrieben; Korrektur über Storno der Lagerbuchung. Nicht änderbar, nicht löschbar."""

	def validate(self):
		nur_einfuegen_validate(self)

	def on_trash(self):
		nur_einfuegen_on_trash(self)
