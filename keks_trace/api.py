"""Öffentliche Schnittstelle für Scanner-Seiten, Terminals und Berichte."""

import frappe

from keks_trace import trace


@frappe.whitelist()
def rueckverfolgung(charge: str, richtung: str = "Vorwärts") -> dict:
	"""Rückverfolgung einer Charge. richtung: 'Vorwärts' oder 'Rückwärts'."""
	frappe.has_permission("Batch", "read", charge, throw=True)
	return trace.rueckverfolgung(charge, richtung)
