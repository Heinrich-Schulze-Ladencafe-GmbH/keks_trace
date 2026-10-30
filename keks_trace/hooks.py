app_name = "keks_trace"
app_title = "Keks Trace"

# Symbol auf der ERPNext-Startseite (Desktop) mit Link zur Startseite „Keks Trace“
add_to_apps_screen = [
	{
		"name": "keks_trace",
		"logo": "/assets/keks_trace/images/keks-trace-logo.svg",
		"title": "Keks Trace",
		"route": "/desk/keks-trace",
	}
]
app_publisher = "Heinrich Schulze Ladencafe GmbH"
app_description = "Chargenrückverfolgung mit Rework für die Keksproduktion"
app_email = ""
app_license = "proprietary"

# keks_trace baut auf ERPNext auf (Chargen, Lager, Buchungen).
required_apps = ["erpnext"]

# Zusatzfelder an Artikel und Charge werden per Code angelegt,
# damit jede Instanz identisch ist (nichts in der Oberfläche zusammenklicken).
after_install = "keks_trace.install.after_install"
after_migrate = "keks_trace.install.after_migrate"

doc_events = {
	"Stock Entry": {
		# Läuft VOR der ERPNext-Prüfung, damit Bediener klare deutsche Meldungen sehen:
		# Sperren, Verfall, Rework-Regeln, Allergene, Behälter, Vollständigkeit.
		"before_validate": "keks_trace.pruefungen.pruefe_stock_entry",
		# Genealogie-Kanten, Ursprungs-/Backtag-/MHD-Daten und Behälterinhalt.
		"on_submit": ["keks_trace.genealogie.on_submit", "keks_trace.traeger.on_submit"],
		"before_cancel": "keks_trace.palette.se_before_cancel",
		"on_cancel": ["keks_trace.genealogie.on_cancel", "keks_trace.traeger.on_cancel"],
		"on_trash": "keks_trace.schutz.beleg_on_trash",
	},
	"Delivery Note": {
		"before_validate": "keks_trace.sperre.pruefe_lieferung",
		# Paletten: Inhalt prüfen, beim Buchen abbuchen, beim Storno zurück
		"validate": "keks_trace.palette.pruefe_lieferung",
		"on_submit": "keks_trace.palette.lieferung_on_submit",
		"on_cancel": "keks_trace.palette.lieferung_on_cancel",
		"on_trash": "keks_trace.schutz.beleg_on_trash",
	},
	"Purchase Receipt": {"on_trash": "keks_trace.schutz.beleg_on_trash"},
	"Stock Reconciliation": {"on_trash": "keks_trace.schutz.beleg_on_trash"},
	"Item": {"validate": "keks_trace.los.item_validate"},
	"Batch": {
		"before_insert": "keks_trace.sperre.batch_before_insert",
		"after_insert": "keks_trace.sperre.batch_after_insert",
		"validate": "keks_trace.schutz.batch_validate",
		"on_trash": "keks_trace.schutz.batch_on_trash",
	},
}
