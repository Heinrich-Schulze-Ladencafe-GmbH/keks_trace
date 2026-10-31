import frappe
from frappe import _
from frappe.model.document import Document

# Vorlagen je Typ: Funktionen und herstellbare Stufen. Anpassbar an jeder Station.
VORLAGEN = {
	"Backstube": (
		{"f_herstellen", "f_rework", "f_silo"},
		["Grundteig", "Teig veredelt", "Backware", "Ware lose", "Halbfabrikat"],
	),
	"Verpackung": ({"f_herstellen", "f_paletten", "f_rework"}, ["Fertigware"]),
	"Lager": ({"f_wareneingang", "f_paletten", "f_silo", "f_umlagern"}, []),
	"Versand": ({"f_lieferung", "f_paletten"}, []),
	"Herzen Garnieren": ({"f_herstellen", "f_rework"}, ["Halbfabrikat", "Ware lose"]),
	"Herzen Verpackung": ({"f_herstellen", "f_paletten", "f_rework"}, ["Fertigware"]),
	"Lagerverkauf": ({"f_umlagern"}, []),
	"Former": ({"f_linie"}, []),
	"Kneter": ({"f_herstellen", "f_linie"}, ["Teig veredelt"]),
	"Nachfüllen": ({"f_linie"}, []),
	"Packstation": ({"f_packstation"}, []),
	"Paletten-Terminal": ({"f_palette_fertig", "f_paletten"}, ["Fertigware"]),
	"Individuell": (set(), []),
}
FUNKTIONEN = (
	"f_herstellen",
	"f_rework",
	"f_silo",
	"f_wareneingang",
	"f_paletten",
	"f_lieferung",
	"f_umlagern",
	"f_linie",
	"f_packstation",
	"f_palette_fertig",
)


def vorbelegen(doc):
	funktionen, stufen = VORLAGEN.get(doc.typ, (set(), []))
	for f in FUNKTIONEN:
		doc.set(f, 1 if f in funktionen else 0)
	if not (doc.stufen or "").strip():
		doc.stufen = "\n".join(stufen)


class TerminalStation(Document):
	def validate(self):
		if self.is_new() and not any(self.get(f) for f in FUNKTIONEN):
			vorbelegen(self)
		from keks_trace.install import CHARGEN_STUFEN

		falsch = [s for s in self.stufen_liste() if s not in CHARGEN_STUFEN]
		if falsch:
			frappe.throw(
				_("Unbekannte Chargenstufe: {0}. Erlaubt: {1}").format(
					", ".join(falsch), ", ".join(CHARGEN_STUFEN)
				)
			)
		if (self.f_linie or self.f_packstation or self.f_palette_fertig) and not self.linie:
			frappe.throw(
				_("Bitte die Linie angeben (für Former, Nachfüllen, Packstation, Paletten-Terminal).")
			)
		if self.f_umlagern and not self.umlager_ziel and self.typ == "Lagerverkauf":
			frappe.throw(_("Bitte „Umlagern nach“ angeben (z. B. Lagerort Lagerverkauf)."))

	def stufen_liste(self) -> list[str]:
		return [s.strip() for s in (self.stufen or "").splitlines() if s.strip()]

	def funktionen(self) -> list[str]:
		return [f[2:] for f in FUNKTIONEN if self.get(f)]
