"""QS-Tagesliste: alles, was die QS an einem Tag ansehen muss, an einer Stelle.

- FEFO: jüngere Charge genommen, ältere im Lager (Grund an der Buchung)
- Einwaage: Zutat außerhalb der Toleranz (Grund an der Buchung)
- Prüfung: Prüfwert außerhalb der Grenze (Prüfprotokoll), auch verweigerte Annahmen
- Sperre: Charge gesperrt (Sperrprotokoll); die Routinesperre „Freigabe vor Verwendung“ ist keine Abweichung
  und zählt nur als offene Freigabe (offene_freigaben)

Die Durchsicht wird je Tag bestätigt (DocType „QS Durchsicht“, nicht änderbar). Damit ist nachweisbar,
dass ein Grund auch gelesen wurde.
"""

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate, now_datetime

from keks_trace.sperre import FREIGABE_GRUND, FREIGABE_VORGANG, QS_ROLLEN

ARTEN = ("FEFO", "Einwaage", "Prüfung", "Sperre")


def eintraege(von, bis=None) -> list[dict]:
	"""Einträge von..bis (je einschließlich), nach Zeit sortiert."""
	von = getdate(von)
	bis = getdate(bis or von)
	ab, vor = get_datetime(von), get_datetime(add_days(bis, 1))
	zeilen = []
	for feld, art in (("kt_fefo_abweichung", "FEFO"), ("kt_rezept_abweichung", "Einwaage")):
		for se in frappe.db.sql(
			f"""select name, posting_date, posting_time, kt_station, {feld} as text
			from `tabStock Entry`
			where docstatus = 1 and ifnull({feld}, '') != '' and posting_date between %(von)s and %(bis)s""",
			{"von": von, "bis": bis},
			as_dict=True,
		):
			ausgang = (
				frappe.db.get_value(
					"Stock Entry Detail",
					{"parent": se.name, "is_finished_item": 1},
					["item_code", "batch_no"],
					as_dict=True,
				)
				or frappe._dict()
			)
			zeilen.append(
				{
					"zeit": get_datetime(f"{se.posting_date} {se.posting_time}"),
					"art": art,
					"station": se.kt_station,
					"charge": ausgang.batch_no,
					"artikel": ausgang.item_code,
					"text": se.text,
					"beleg_typ": "Stock Entry",
					"beleg": se.name,
				}
			)
	for p in frappe.get_all(
		"Pruefung",
		filters={"ergebnis": "Abweichung", "zeitpunkt": ["between", [ab, vor]]},
		fields=["name", "zeitpunkt", "pruefplan", "station", "charge", "wert", "einheit", "grenzwert", "folge", "bemerkung", "gesperrte_chargen"],
	):  # fmt: skip
		if get_datetime(p.zeitpunkt) >= vor:
			continue
		teile = [p.pruefplan]
		if p.wert is not None and p.einheit:
			teile.append(
				_("gemessen {0} {1}, erlaubt {2}").format(
					frappe.format(p.wert), p.einheit, p.grenzwert or "-"
				)
			)
		teile += [x for x in (p.folge, p.bemerkung) if x]
		if p.gesperrte_chargen:
			teile.append(_("gesperrt: {0}").format(p.gesperrte_chargen))
		zeilen.append(
			{
				"zeit": get_datetime(p.zeitpunkt),
				"art": "Prüfung",
				"station": p.station,
				"charge": p.charge,
				"artikel": frappe.db.get_value("Batch", p.charge, "item") if p.charge else None,
				"text": " · ".join(str(t) for t in teile),
				"beleg_typ": "Pruefung",
				"beleg": p.name,
			}
		)
	for s in frappe.get_all(
		"Chargen Sperre",
		filters={"aktion": "Sperren", "zeitpunkt": ["between", [ab, vor]]},
		fields=["name", "zeitpunkt", "charge", "artikel", "grund", "vorgang", "nutzer"],
	):
		if get_datetime(s.zeitpunkt) >= vor or _routine(s):
			continue
		zeilen.append(
			{
				"zeit": get_datetime(s.zeitpunkt),
				"art": "Sperre",
				"station": None,
				"charge": s.charge,
				"artikel": s.artikel,
				"text": " · ".join(x for x in (s.vorgang, s.grund, s.nutzer) if x),
				"beleg_typ": "Chargen Sperre",
				"beleg": s.name,
			}
		)
	zeilen.sort(key=lambda z: (z["zeit"], z["art"]))
	return zeilen


def _routine(s) -> bool:
	"""Routinesperre beim Anlegen (Freigabe vor Verwendung); ältere Einträge ohne Vorgang am Text erkannt."""
	return s.vorgang == FREIGABE_VORGANG or (not s.vorgang and s.grund in (FREIGABE_GRUND, _(FREIGABE_GRUND)))


def offene_freigaben() -> int:
	"""Chargen, die noch auf die Freigabe der QS warten (Aufgabe, keine Abweichung)."""
	return frappe.db.count(
		"Batch", {"kt_status": "Gesperrt", "kt_sperrgrund": ["in", [FREIGABE_GRUND, _(FREIGABE_GRUND)]]}
	)


def durchsicht(datum) -> dict | None:
	name = frappe.db.get_value("QS Durchsicht", {"datum": getdate(datum)})
	if not name:
		return None
	return frappe.db.get_value(
		"QS Durchsicht",
		name,
		["name", "datum", "durchgesehen_von", "zeitpunkt", "eintraege", "bemerkung"],
		as_dict=True,
	)


@frappe.whitelist()
def durchsehen(datum, bemerkung: str | None = None) -> dict:
	"""Tagesliste eines Tages als durchgesehen bestätigen. Nur QS; je Tag einmal; nicht für die Zukunft."""
	if not QS_ROLLEN & set(frappe.get_roles()):
		frappe.throw(_("Nur die QS bestätigt die Durchsicht."), frappe.PermissionError)
	datum = getdate(datum)
	if datum > getdate(now_datetime()):
		frappe.throw(_("Ein Tag in der Zukunft kann nicht durchgesehen werden."))
	if durchsicht(datum):
		frappe.throw(_("Der {0} ist schon als durchgesehen bestätigt.").format(frappe.format(datum, "Date")))
	doc = frappe.get_doc(
		{
			"doctype": "QS Durchsicht",
			"datum": datum,
			"eintraege": len(eintraege(datum)),
			"durchgesehen_von": frappe.session.user,
			"zeitpunkt": now_datetime(),
			"bemerkung": (bemerkung or "").strip() or None,
		}
	).insert(ignore_permissions=True)
	return {"name": doc.name, "eintraege": doc.eintraege}
