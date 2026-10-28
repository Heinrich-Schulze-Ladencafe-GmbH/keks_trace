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
