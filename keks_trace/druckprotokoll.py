"""Druckprotokoll: jeder Etikettendruck mit Grund (DocType Etikettendruck, nur einfügen).

Wozu: Ein nachgedrucktes Etikett ist ein Risiko - klebt es auf der falschen Palette, gibt es eine NVE zweimal.
Deshalb steht jeder Druck mit Grund, Station, Drucker und Person im Protokoll, und ein Nachdruck ohne Anlass
(gleicher Inhalt, kein Ablauf) braucht einen Grund: „beschädigt“ oder „fehlt“.

Den Grund bestimmt das System, wo es ihn kennt:
- noch nie gedruckt → Erstdruck
- Palette: Inhalt seit dem letzten Druck geändert → Inhalt geändert
- sonst der Grund vom Terminal: „ablauf“ (Druck gehört zur Buchung, z. B. versandbereit), „beschaedigt“, „fehlt“
Kartonetiketten werden laufend nachgedruckt (Rolle für die nächste Palette) und brauchen keinen Grund.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

GRUENDE = {
	"erstdruck": "Erstdruck",
	"inhalt": "Inhalt geändert",
	"ablauf": "Im Ablauf",
	"beschaedigt": "Beschädigt / unleserlich",
	"fehlt": "Etikett fehlt",
	"test": "Testdruck",
}
# Gründe, die das Terminal bei einem Nachdruck zur Auswahl anbietet
NACHDRUCK = ("beschaedigt", "fehlt")
VOM_TERMINAL = ("ablauf", *NACHDRUCK)
ARTNAME = {"palette": "Palette", "karton": "Karton", "gebinde": "Gebinde", "test": "Test"}


def schon_gedruckt(palette: str | None = None, traeger: str | None = None) -> bool:
	filt = {"palette": palette} if palette else {"traeger": traeger}
	return bool(frappe.db.exists("Etikettendruck", filt))


def grund_bestimmen(art: str, grund: str | None, palette: str | None = None, traeger=()) -> str | None:
	"""Schlüssel aus GRUENDE oder None = das Terminal muss nach dem Grund fragen."""
	if grund and grund not in VOM_TERMINAL:
		frappe.throw(_("Unbekannter Grund für den Druck: {0}").format(grund))
	if art == "karton":
		return grund or "ablauf"
	if art == "palette":
		from keks_trace import palette as paletten

		aktuell = paletten.etikett_aktuell(palette)
		if aktuell is None and not schon_gedruckt(palette=palette):
			return "erstdruck"
		if aktuell is False:
			return "inhalt"
	elif art == "gebinde" and not any(schon_gedruckt(traeger=t) for t in traeger):
		return "erstdruck"
	return grund


def andere_paletten(palette: str) -> list[str]:
	"""Aktive Paletten, die ein Los mit dieser Palette teilen - Kandidaten für eine Verwechslung."""
	from keks_trace import palette as paletten

	lose = [x["charge"] for x in paletten.inhalt(palette)]
	return sorted(
		{
			z.palette
			for z in paletten.paletten_fuer(lose)
			if z.palette != palette and z.anzahl_jetzt > 1e-6 and z.status in paletten.AKTIV
		}
	)


def geprueft_text(geprueft, palette: str | None) -> str | None:
	"""Nachdruck „Etikett fehlt“: welche anderen Paletten mit demselben Los am Terminal gescannt wurden, also ihr
	Etikett noch haben, und welche nicht. None = nicht über die Los-Suche gedruckt (keine Angabe)."""
	if geprueft is None or not palette:
		return None
	if isinstance(geprueft, str):
		geprueft = [x for x in geprueft.split(",") if x.strip()]
	from keks_trace import palette as paletten

	gesehen = set()
	for code in geprueft:
		nve = paletten.finde(code)
		if not nve:
			frappe.throw(_("Palette {0} nicht gefunden.").format(code))
		if nve == palette:
			frappe.throw(_("Die Palette, die nachgedruckt wird, hat laut Scan ein Etikett. Bitte prüfen."))
		gesehen.add(nve)
	kandidaten = andere_paletten(palette)
	if not kandidaten:
		return _("Keine anderen Paletten mit diesem Los im Lager.")
	teile = []
	if ok := [n for n in kandidaten if n in gesehen]:
		teile.append(_("Mit Etikett gescannt: {0}").format(", ".join(ok)))
	if offen := [n for n in kandidaten if n not in gesehen]:
		teile.append(_("Nicht geprüft: {0}").format(", ".join(offen)))
	return ". ".join(teile)


def buchen(
	art: str,
	grund: str,
	drucker: str | None,
	station: str | None = None,
	palette: str | None = None,
	traeger=(),
	auftrag: str | None = None,
	anzahl: int = 1,
	bemerkung: str | None = None,
) -> None:
	"""Druck festhalten: eine Zeile je Palette bzw. je Behälter/Gebinde."""
	from keks_trace import palette as paletten

	gemeinsam = {
		"doctype": "Etikettendruck",
		"zeitpunkt": now_datetime(),
		"art": ARTNAME[art],
		"grund": GRUENDE[grund],
		"drucker": drucker,
		"station": station,
		"nutzer": frappe.session.user,
		"auftrag": auftrag,
		"bemerkung": bemerkung,
	}
	if art == "gebinde":
		for t in traeger:
			frappe.get_doc({**gemeinsam, "traeger": t, "anzahl": 1}).insert(ignore_permissions=True)
		return
	zeile = {**gemeinsam, "anzahl": anzahl}
	if palette:
		zeile.update(palette=palette, inhalt=paletten.stand(palette) or None)
	frappe.get_doc(zeile).insert(ignore_permissions=True)


def drucke(palette: str | None = None, traeger: str | None = None, anzahl: int = 50) -> list[dict]:
	"""Letzte Drucke für die Akte."""
	filt = {"palette": palette} if palette else {"traeger": traeger}
	return frappe.get_all(
		"Etikettendruck",
		filters=filt,
		fields=["zeitpunkt", "grund", "drucker", "station", "nutzer", "bemerkung"],
		order_by="zeitpunkt desc, creation desc",
		limit=anzahl,
	)
