"""Öffentliche Schnittstelle für Scanner-Seiten, Terminals und Berichte."""

import frappe

from keks_trace import trace, traeger


@frappe.whitelist()
def rueckverfolgung(charge: str, richtung: str = "Vorwärts") -> dict:
	"""Rückverfolgung einer Charge. richtung: 'Vorwärts' oder 'Rückwärts'."""
	frappe.has_permission("Batch", "read", charge, throw=True)
	return trace.rueckverfolgung(charge, richtung)


@frappe.whitelist()
def traeger_info(code: str) -> dict:
	"""Inhalt eines Behälters (Charge, Menge, Verfall) nach dem Scannen seines QR-Codes."""
	frappe.has_permission("Produkttraeger", "read", code, throw=True)
	return traeger.info(code)


@frappe.whitelist()
def mengenbilanz(charge: str) -> dict:
	"""Mengenbilanz einer Charge: Zugang, Abgang, Bestand, Abgleich mit der Genealogie."""
	from keks_trace.bilanz import mengenbilanz as _bilanz

	frappe.has_permission("Batch", "read", charge, throw=True)
	return _bilanz(charge)


@frappe.whitelist()
def silo_info(silo: str) -> dict:
	"""Chargen im Silo (rechnerischer Bestand) und Chargen, die noch vermischt enthalten sein können."""
	from keks_trace.silo import info

	frappe.has_permission("Silo", "read", silo, throw=True)
	return info(silo)
