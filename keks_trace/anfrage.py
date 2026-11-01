"""Doppelbuchungen verhindern (WLAN in der Halle): jede Buchung vom Terminal trägt eine Anfrage-ID.

Das Terminal schickt im Kopf „X-KT-Anfrage“ eine ID, die es so lange behält, bis eine Buchung geklappt hat.
Kommt dieselbe Anfrage (gleiche ID, gleiche Methode, gleiche Daten) noch einmal, z. B. weil die Antwort
unterwegs verloren ging und der Mitarbeiter nochmal tippt, liefert der Server das Ergebnis der ersten
Buchung zurück statt ein zweites Mal zu buchen. Läuft die erste noch, kommt eine klare Meldung.
"""

import functools
import hashlib
import json

import frappe
from frappe import _

GUELTIG = 24 * 3600  # Sekunden: so lange wird das Ergebnis einer Buchung gemerkt
SPERRE = 120  # Sekunden: so lange darf eine Buchung höchstens laufen


def _schluessel(methode: str) -> str | None:
	anfrage = frappe.get_request_header("X-KT-Anfrage") if frappe.request else None
	if not anfrage:
		return None
	daten = {k: v for k, v in (frappe.form_dict or {}).items() if k not in ("cmd", "csrf_token")}
	fingerabdruck = hashlib.sha256(
		json.dumps([methode, daten], sort_keys=True, default=str).encode()
	).hexdigest()[:24]
	return f"kt_anfrage:{frappe.session.user}:{anfrage[:64]}:{fingerabdruck}"


def einmalig(fn):
	"""Buchung höchstens einmal ausführen je Anfrage-ID und Daten (siehe oben)."""

	@functools.wraps(fn)
	def wrapper(*args, **kwargs):
		schluessel = _schluessel(fn.__name__)
		if not schluessel:
			return fn(*args, **kwargs)
		ergebnis = frappe.cache.get_value(schluessel)
		if ergebnis is not None:
			return ergebnis
		sperre = frappe.cache.make_key(schluessel + ":laeuft")
		if not frappe.cache.set(sperre, 1, nx=True, ex=SPERRE):
			frappe.throw(_("Diese Buchung läuft schon. Bitte kurz warten, nicht nochmal tippen."))
		try:
			ergebnis = fn(*args, **kwargs)
			frappe.db.commit()  # erst gebucht, dann gemerkt
			frappe.cache.set_value(schluessel, ergebnis, expires_in_sec=GUELTIG)
			return ergebnis
		finally:
			frappe.cache.delete(sperre)

	return wrapper
