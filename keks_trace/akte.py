"""Akte: der Lebenslauf einer Palette oder eines Behälters, lesbar für das Terminal.

Quelle sind nur vorhandene Protokolle, nichts wird neu berechnet oder gespeichert:
- Palette: Paletten Bewegung (wer, wann, wo, welches Los) und Etikettendruck
- Behälter/Gebinde: Traeger Belegung (welche Charge von wann bis wann) und Etikettendruck

Dazu „Wo ist dieses Los?“ (fundstellen): alle Paletten und Behälter, auf bzw. in denen ein Los gerade liegt, je mit
kurzem Lebenslauf. Damit findet man eine Palette ohne Etikett wieder: Inhalt, Ort, Zeit und Person grenzen ein.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, format_datetime, get_fullname

from keks_trace import druckprotokoll
from keks_trace import palette as paletten

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


def _person(nutzer: str | None) -> str | None:
	return get_fullname(nutzer) if nutzer else None


def _los(charge: str) -> str:
	los = frappe.get_cached_value("Batch", charge, "kt_los") if charge else None
	return los or charge


def _bewegungen(palette: str) -> list[dict]:
	return frappe.get_all(
		"Paletten Bewegung",
		filters={"palette": palette},
		fields=[
			"richtung",
			"art",
			"charge",
			"artikel",
			"anzahl",
			"einheit",
			"gegen_palette",
			"beleg",
			"station",
			"zeitpunkt",
			"nutzer",
		],  # fmt: skip
		order_by="zeitpunkt asc, creation asc",
	)


def _zusammenfassen(zeilen: list[dict]) -> list[dict]:
	"""Gleiche Bewegungen hintereinander (Art, Richtung, Los, Einheit, Station, Person, Gegenpalette) zu einer."""
	gruppen = []
	for z in zeilen:
		g = gruppen[-1] if gruppen else None
		gleich = g and all(g[k] == z[k] for k in ("art", "richtung", "charge", "einheit", "station", "nutzer",
		                                          "gegen_palette", "beleg"))  # fmt: skip
		if gleich and (z.zeitpunkt - g["bis"]).total_seconds() <= ZUSAMMEN_MINUTEN * 60:
			g["anzahl"] += flt(z.anzahl)
			g["bis"] = z.zeitpunkt
		else:
			gruppen.append({**z, "anzahl": flt(z.anzahl), "von": z.zeitpunkt, "bis": z.zeitpunkt})
	return gruppen


def _bewegung_text(g: dict) -> str:
	vorzeichen = "+" if g["richtung"] == "Zugang" else "−"
	text = f"{g['art']}: {vorzeichen}{paletten._n(g['anzahl'], g['einheit'])} Los {_los(g['charge'])}"
	if g.get("gegen_palette"):
		text += (" von" if g["richtung"] == "Zugang" else " auf") + f" Palette …{g['gegen_palette'][-6:]}"
	if g.get("beleg") and g["art"] in ("Lieferung", "Storno Lieferung"):
		text += f" ({g['beleg']})"
	return text


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
		e["zeit_text"] = _zeit(e["zeit"]) + (
			f"–{_uhr(e['bis'])}" if e.get("bis") and e["bis"] != e["zeit"] else ""
		)
		e["zeit"] = str(e["zeit"])
		e.pop("bis", None)
	return ereignisse


def palette(nve: str) -> dict:
	nr = paletten.finde(nve)
	if not nr:
		frappe.throw(_("Palette nicht gefunden."), frappe.DoesNotExistError)
	frappe.has_permission("Palette", "read", nr, throw=True)
	p = frappe.get_doc("Palette", nr)
	ereignisse = [{"zeit": p.creation, "art": "Angelegt", "text": _("Palette angelegt ({0})").format(p.typ),
	               "station": p.station, "person": _person(p.owner)}]  # fmt: skip
	for g in _zusammenfassen(_bewegungen(nr)):
		ereignisse.append({"zeit": g["von"], "bis": g["bis"], "art": g["art"], "text": _bewegung_text(g),
		                   "station": g["station"], "person": _person(g["nutzer"])})  # fmt: skip
	ereignisse += _druck_ereignisse(palette=nr)
	i = paletten.info(nr)
	return {
		"typ": "palette",
		"nve": nr,
		"titel": _("Palette {0}").format(nr),
		"zeilen": [
			[_("Art / Status"), f"{p.typ} · {p.status}"],
			[_("Inhalt"), i["kartons"] or _("leer")],
			*([[_("Kunde"), p.kunde]] if p.kunde else []),
			*([[_("Lieferschein"), p.lieferschein]] if p.lieferschein else []),
			[_("Etikett"), _etikett_text(i["etikett_aktuell"], p.etikett_gedruckt)],
		],
		"ereignisse": _sortiert(ereignisse),
	}


def _etikett_text(aktuell, gedruckt) -> str:
	if aktuell is None:
		return _("noch nie gedruckt")
	return _("zuletzt {0}").format(_zeit(gedruckt)) + ("" if aktuell else _(" – Inhalt seither geändert"))


def behaelter(code: str) -> dict:
	if not frappe.db.exists("Produkttraeger", code):
		frappe.throw(_("Behälter {0} nicht gefunden.").format(code), frappe.DoesNotExistError)
	frappe.has_permission("Produkttraeger", "read", code, throw=True)
	t = frappe.get_doc("Produkttraeger", code)
	ereignisse = [{"zeit": t.creation, "art": "Angelegt", "text": _("{0} angelegt").format(t.typ),
	               "station": None, "person": _person(t.owner)}]  # fmt: skip
	for b in frappe.get_all(
		"Traeger Belegung",
		filters={"traeger": code},
		fields=["charge", "artikel", "menge_eingang", "menge_aktuell", "von", "bis", "offen"],
		order_by="von asc, creation asc",
	):
		name = frappe.get_cached_value("Item", b.artikel, "item_name") if b.artikel else ""
		text = _("Befüllt: {0} kg {1}, Charge {2}").format(
			f"{flt(b.menge_eingang, 3):g}".replace(".", ","), name, _los(b.charge)
		)
		ereignisse.append({"zeit": b.von, "art": "Befüllt", "text": text, "station": None, "person": None})
		if b.bis:
			ereignisse.append({"zeit": b.bis, "art": "Geleert", "text": _("Geleert: Charge {0}").format(_los(b.charge)),
			                   "station": None, "person": None})  # fmt: skip
	if t.gereinigt_am:
		ereignisse.append({"zeit": t.gereinigt_am, "art": "Gereinigt", "text": _("Zuletzt als gereinigt gemeldet"),
		                   "station": None, "person": None})  # fmt: skip
	ereignisse += _druck_ereignisse(traeger=code)
	inhalt = (
		(f"{flt(t.menge, 3):g} kg".replace(".", ",") + f" · Charge {_los(t.charge)}")
		if t.charge
		else _("leer")
	)
	return {
		"typ": "behaelter",
		"code": code,
		"titel": _("{0} {1}").format(t.typ, code),
		"zeilen": [[_("Status"), t.status], [_("Inhalt"), inhalt]],
		"ereignisse": _sortiert([e for e in ereignisse if e["zeit"]]),
	}


def akte(code: str) -> dict:
	"""Akte zu einem gescannten oder abgetippten Code: Palette oder Behälter/Gebinde."""
	code = (code or "").strip()
	if paletten.finde(code):
		return palette(code)
	if frappe.db.exists("Produkttraeger", code):
		return behaelter(code)
	frappe.throw(_("Zu {0} gibt es keine Akte (nur Paletten und Behälter).").format(frappe.bold(code)))


# ---------------------------------------------------------------------------
# Wo ist dieses Los?
# ---------------------------------------------------------------------------


def _kurz(nve: str) -> dict:
	"""Lebenslauf in einer Zeile: wann und von wem gepackt, letzte Bewegung, letzter Etikettendruck."""
	zeilen = _bewegungen(nve)
	zu = [z for z in zeilen if z.richtung == "Zugang"]
	letzte = zeilen[-1] if zeilen else None
	personen = sorted({_person(z.nutzer) for z in zu if z.nutzer})
	stationen = sorted({z.station for z in zu if z.station})
	druck = druckprotokoll.drucke(palette=nve, anzahl=1)
	return {
		"gepackt": (f"{_zeit(zu[0].zeitpunkt)}–{_uhr(zu[-1].zeitpunkt)}" if zu else None),
		"stationen": ", ".join(stationen),
		"personen": ", ".join(personen),
		"letzte": (
			f"{letzte.art} {_zeit(letzte.zeitpunkt)}" + (f" · {letzte.station}" if letzte.station else "")
		)
		if letzte
		else None,
		"letzter_druck": (f"{_zeit(druck[0].zeitpunkt)} ({druck[0].grund})" if druck else None),
	}


def fundstellen(charge: str) -> dict:
	"""Alle Stellen, an denen das Los gerade liegt: aktive Paletten, Behälter, lose Ware."""
	if not charge:
		return {"paletten": [], "behaelter": [], "lose": None}
	je_palette = defaultdict(list)
	for z in paletten.paletten_fuer([charge]):
		if z.anzahl_jetzt > EPS and z.status in paletten.AKTIV:
			je_palette[z.palette].append(z)
	liste = []
	for nve, zeilen in list(je_palette.items())[:MAX_FUNDSTELLEN]:
		i = paletten.info(nve)
		liste.append(
			{
				"nve": nve,
				"status": i["status"],
				"art": i["art"],
				"kunde": i["kunde"],
				"dieses_los": ", ".join(paletten._n(z.anzahl_jetzt, z.einheit) for z in zeilen),
				"inhalt": i["kartons"],
				"etikett_aktuell": i["etikett_aktuell"],
				**_kurz(nve),
			}
		)
	behaelter = frappe.get_all(
		"Produkttraeger",
		filters={"charge": charge},
		fields=["name as code", "typ", "status", "menge"],
		limit=MAX_FUNDSTELLEN,
	)
	artikel = frappe.db.get_value("Batch", charge, "item")
	lose = paletten.lose(charge)
	return {
		"los": _los(charge),
		"paletten": liste,
		"mehr_paletten": max(0, len(je_palette) - MAX_FUNDSTELLEN),
		"behaelter": behaelter,
		"lose": paletten.zerlegen(artikel, lose) if lose > EPS and artikel else None,
	}
