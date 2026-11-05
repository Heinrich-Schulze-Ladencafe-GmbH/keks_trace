"""Akte: gemeinsame Grenzen und Helfer (Zeit, Person, Los, Etikettendrucke)."""

import frappe
from frappe import _
from frappe.utils import format_datetime, get_fullname

from keks_trace import druckprotokoll

EPS = 1e-6


MAX_EREIGNISSE = 80


MAX_FUNDSTELLEN = 40


# Aufeinanderfolgende gleiche Bewegungen (z. B. 40 Karton einzeln gebucht) werden zu einer Zeile zusammengefasst,
# solange zwischen zwei Buchungen höchstens so viele Minuten liegen.
ZUSAMMEN_MINUTEN = 30


def _zeit(dt) -> str | None:
	return format_datetime(dt, "dd.MM.yy HH:mm") if dt else None


def _uhr(dt) -> str | None:
	return format_datetime(dt, "HH:mm") if dt else None


def _bis(von, bis) -> str:
	"""„-10:48“ für eine Zeitspanne; gleiche Minute: nichts; anderer Tag: mit Datum."""
	if not von or not bis or _zeit(bis) == _zeit(von):
		return ""
	return f"-{_uhr(bis)}" if _datum(bis) == _datum(von) else f" bis {_zeit(bis)}"


def _person(nutzer: str | None) -> str | None:
	return get_fullname(nutzer) if nutzer else None


def _los(charge: str) -> str:
	los = frappe.get_cached_value("Batch", charge, "kt_los") if charge else None
	return los or charge


def _druck_ereignisse(**filt) -> list[dict]:
	return [
		{
			"zeit": d.zeitpunkt,
			"art": "Etikett",
			"text": _("Etikett gedruckt: {0}").format(d.grund)
			+ (f" · {d.drucker}" if d.drucker else "")
			+ (f" · {d.bemerkung}" if d.bemerkung else ""),
			"station": d.station,
			"person": _person(d.nutzer),
		}
		for d in druckprotokoll.drucke(**filt)
	]


def _sortiert(ereignisse: list[dict]) -> list[dict]:
	ereignisse.sort(key=lambda e: e["zeit"])
	ereignisse = ereignisse[-MAX_EREIGNISSE:]
	for e in ereignisse:
		e["zeit_text"] = _zeit(e["zeit"]) + _bis(e["zeit"], e.get("bis"))
		e["zeit"] = str(e["zeit"])
		e.pop("bis", None)
	return ereignisse


def _datum(d) -> str | None:
	return format_datetime(d, "dd.MM.yy") if d else None
