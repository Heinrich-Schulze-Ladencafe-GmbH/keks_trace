from frappe.model.document import Document

from keks_trace.schutz import nur_einfuegen_on_trash, nur_einfuegen_validate


class Pruefung(Document):
	"""Prüfprotokoll. Nicht änderbar, nicht löschbar."""

	def validate(self):
		nur_einfuegen_validate(self)

	def on_trash(self):
		nur_einfuegen_on_trash(self)
