"""Akte: Lebenslauf einer Palette oder eines Behälters aus Bewegungen, Belegungen und Etikettendrucken."""

import frappe
from frappe import _
from frappe.utils import flt

from keks_trace import palette as paletten
from keks_trace.akte.basis import ZUSAMMEN_MINUTEN, _druck_ereignisse, _los, _person, _sortiert, _zeit


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
		],
		order_by="zeitpunkt asc, creation asc",
	)


def _zusammenfassen(zeilen: list[dict]) -> list[dict]:
	"""Gleiche Bewegungen hintereinander (Art, Richtung, Los, Einheit, Station, Person, Gegenpalette) zu einer."""
	gruppen = []
	for z in zeilen:
		g = gruppen[-1] if gruppen else None
		gleich = g and all(
			g[k] == z[k]
			for k in ("art", "richtung", "charge", "einheit", "station", "nutzer", "gegen_palette", "beleg")
		)
		if gleich and (z.zeitpunkt - g["bis"]).total_seconds() <= ZUSAMMEN_MINUTEN * 60:
			g["anzahl"] += flt(z.anzahl)
			g["bis"] = z.zeitpunkt
		else:
			gruppen.append({**z, "anzahl": flt(z.anzahl), "von": z.zeitpunkt, "bis": z.zeitpunkt})
	return gruppen


def _bewegung_text(g: dict) -> str:
	vorzeichen = "+" if g["richtung"] == "Zugang" else "-"
	text = f"{g['art']}: {vorzeichen}{paletten._n(g['anzahl'], g['einheit'])} Los {_los(g['charge'])}"
	if g.get("gegen_palette"):
		text += (" von" if g["richtung"] == "Zugang" else " auf") + f" Palette …{g['gegen_palette'][-6:]}"
	if g.get("beleg") and g["art"] in ("Lieferung", "Storno Lieferung"):
		text += f" ({g['beleg']})"
	return text


def palette(nve: str) -> dict:
	nr = paletten.finde(nve)
	if not nr:
		frappe.throw(_("Palette nicht gefunden."), frappe.DoesNotExistError)
	frappe.has_permission("Palette", "read", nr, throw=True)
	p = frappe.get_doc("Palette", nr)
	ereignisse = [
		{
			"zeit": p.creation,
			"art": "Angelegt",
			"text": _("Palette angelegt ({0})").format(p.typ),
			"station": p.station,
			"person": _person(p.owner),
		}
	]
	for g in _zusammenfassen(_bewegungen(nr)):
		ereignisse.append(
			{
				"zeit": g["von"],
				"bis": g["bis"],
				"art": g["art"],
				"text": _bewegung_text(g),
				"station": g["station"],
				"person": _person(g["nutzer"]),
			}
		)
	ereignisse += _druck_ereignisse(palette=nr)
	ereignisse += _zuordnungen(nr)
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
			*_karton_zeilen(i),
			[_("Etikett"), _etikett_text(i["etikett_aktuell"], p.etikett_gedruckt)],
		],
		"ereignisse": _sortiert(ereignisse),
		# Lose auf der Palette: „Woraus besteht das?“ je Los
		"lose": [
			{"charge": x["charge"], "los": x.get("los") or x["charge"], "name": x.get("name")}
			for x in i["positionen_gesamt"]
		],
	}


def _zuordnungen(nr: str) -> list[dict]:
	"""Versandkarton auf/von einer Palette, aus Sicht des Kartons und der Palette."""
	out = []
	for z in frappe.get_all(
		"Versandkarton Zuordnung",
		or_filters={"karton": nr, "palette": nr},
		fields=["karton", "palette", "richtung", "zeitpunkt", "station", "nutzer", "beleg"],
	):
		auf = z.richtung == "Auf"
		if z.karton == nr:
			text = (_("Auf Palette …{0} gestellt") if auf else _("Von Palette …{0} genommen")).format(
				z.palette[-6:]
			)
		else:
			text = (
				_("Versandkarton …{0} aufgestellt") if auf else _("Versandkarton …{0} heruntergenommen")
			).format(z.karton[-6:])
		if z.beleg:
			text += f" ({z.beleg})"
		out.append(
			{
				"zeit": z.zeitpunkt,
				"art": "Versandkarton",
				"text": text,
				"station": z.station,
				"person": _person(z.nutzer),
			}
		)
	return out


def _karton_zeilen(i: dict) -> list[list]:
	zeilen = []
	if i.get("auf_palette"):
		zeilen.append([_("Steht auf Palette"), i["auf_palette"]])
	if i.get("versandkartons"):
		zeilen.append(
			[
				_("Versandkartons darauf"),
				", ".join(f"…{k['nve'][-6:]} ({k['inhalt']})" for k in i["versandkartons"]),
			]
		)
	paket = [
		f"{i['gewicht_kg']:g} kg".replace(".", ",") if i.get("gewicht_kg") else "",
		i.get("sendungsnummer") or "",
	]
	if any(paket):
		zeilen.append([_("Paket"), " · ".join(x for x in paket if x)])
	return zeilen


def _etikett_text(aktuell, gedruckt) -> str:
	if aktuell is None:
		return _("noch nie gedruckt")
	return _("zuletzt {0}").format(_zeit(gedruckt)) + ("" if aktuell else _(" - Inhalt seither geändert"))


def behaelter(code: str) -> dict:
	if not frappe.db.exists("Produkttraeger", code):
		frappe.throw(_("Behälter {0} nicht gefunden.").format(code), frappe.DoesNotExistError)
	frappe.has_permission("Produkttraeger", "read", code, throw=True)
	t = frappe.get_doc("Produkttraeger", code)
	ereignisse = [
		{
			"zeit": t.creation,
			"art": "Angelegt",
			"text": _("{0} angelegt").format(t.typ),
			"station": None,
			"person": _person(t.owner),
		}
	]
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
			ereignisse.append(
				{
					"zeit": b.bis,
					"art": "Geleert",
					"text": _("Geleert: Charge {0}").format(_los(b.charge)),
					"station": None,
					"person": None,
				}
			)
	if t.gereinigt_am:
		ereignisse.append(
			{
				"zeit": t.gereinigt_am,
				"art": "Gereinigt",
				"text": _("Zuletzt als gereinigt gemeldet"),
				"station": None,
				"person": None,
			}
		)
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
		"lose": [
			{
				"charge": t.charge,
				"los": _los(t.charge),
				"name": frappe.get_cached_value("Item", t.artikel, "item_name") if t.artikel else None,
			}
		]
		if t.charge
		else [],
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
