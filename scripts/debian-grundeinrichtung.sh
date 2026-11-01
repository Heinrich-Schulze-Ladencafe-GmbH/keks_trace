#!/usr/bin/env bash
# Grundeinrichtung für ein frisches Debian (13 „trixie“, geht auch mit 12): die ersten Handgriffe.
#
#   su -                                  # als root anmelden (mit Minus, sonst fehlen usermod & Co.)
#   bash debian-grundeinrichtung.sh
#
# Fragt nacheinander, Enter übernimmt den Vorschlag in [Klammern] oder überspringt:
#   1. sudo installieren und einen Benutzer in die Gruppe sudo aufnehmen (legt ihn bei Bedarf an)
#   2. Rechnername (mit /etc/hosts)
#   3. Zeitzone
#   4. feste IP statt DHCP (ifupdown, NetworkManager oder systemd-networkd; wirkt nach Neustart)
#   5. in einer VM (Proxmox/KVM): qemu-guest-agent, damit Proxmox IP und Zustand sieht
# Geänderte Dateien werden vorher als *.vor-grundeinrichtung gesichert. Mehrfach ausführbar.
#
# Besser als eine feste IP am Rechner ist oft eine DHCP-Reservierung im Router: dann bleibt die Adresse
# zentral verwaltet und man kann sich nicht aussperren.

set -Eeuo pipefail

schritt() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
hinweis() { printf '\033[0;33m    %s\033[0m\n' "$*"; }
ok()      { printf '\033[0;32m    %s\033[0m\n' "$*"; }
fehler()  { printf '\n\033[1;31mFEHLER: %s\033[0m\n' "$*" >&2; exit 1; }

# frage "Text" "Vorschlag" → Antwort (leer = Vorschlag)
frage() { local a; read -r -p "    $1${2:+ [$2]}: " a </dev/tty; printf '%s' "${a:-$2}"; }
ja() { local a; read -r -p "    $1 [j/N]: " a </dev/tty; [[ "$a" =~ ^[jJyY] ]]; }

sichern() { [ -f "$1" ] && [ ! -f "$1.vor-grundeinrichtung" ] && cp -a "$1" "$1.vor-grundeinrichtung"; return 0; }

# ---------------------------------------------------------------------------
# IPv4-Hilfen (nur Bash)
# ---------------------------------------------------------------------------
ip_gueltig() {
	local o="(0|[1-9][0-9]{0,2})"   # ohne führende Null (sonst rechnet die Shell oktal)
	[[ "$1" =~ ^$o\.$o\.$o\.$o$ ]] || return 1
	local i; for i in 1 2 3 4; do [ "${BASH_REMATCH[$i]}" -le 255 ] || return 1; done
}
ip_zahl() { local IFS=.; read -r a b c d <<<"$1"; echo $(( (a << 24) + (b << 16) + (c << 8) + d )); }
maske() { echo $(( (0xFFFFFFFF << (32 - $1)) & 0xFFFFFFFF )); }
gleiches_netz() {  # gleiches_netz IP GATEWAY PRAEFIX
	local m; m=$(maske "$3")
	[ $(( $(ip_zahl "$1") & m )) -eq $(( $(ip_zahl "$2") & m )) ]
}
netz_oder_broadcast() {  # Adresse ist Netz- oder Broadcast-Adresse?
	local m z; m=$(maske "$2"); z=$(ip_zahl "$1")
	[ "$2" -lt 31 ] && { [ $(( z & ~m & 0xFFFFFFFF )) -eq 0 ] || [ $(( z | (~m & 0xFFFFFFFF) )) -eq "$z" ]; }
}

# ---------------------------------------------------------------------------
# Netz-Konfiguration schreiben (je Verwaltung)
# ---------------------------------------------------------------------------

# ifupdown: Abschnitt „iface DEV inet …“ durch einen statischen ersetzen (Datei auf stdout)
ifupdown_statisch() {  # ifupdown_statisch DATEI DEV IP/PRAEFIX GATEWAY DNS
	awk -v dev="$2" -v adr="$3" -v gw="$4" -v dns="$5" '
		function block() {
			print "iface " dev " inet static"
			print "\taddress " adr
			print "\tgateway " gw
			print "\tdns-nameservers " dns
		}
		$1 == "iface" && $2 == dev && $3 == "inet" { block(); ersetzt = 1; im = 1; next }
		im && ($0 ~ /^[ \t]+[a-z]/) { next }            # Optionen des alten Abschnitts weglassen
		{ im = 0; print }
		END { if (!ersetzt) { print ""; print "auto " dev; block() } }
	' "$1"
}

networkd_statisch() {  # networkd_statisch DEV IP/PRAEFIX GATEWAY DNS
	printf '[Match]\nName=%s\n\n[Network]\nAddress=%s\nGateway=%s\n' "$1" "$2" "$3"
	local d; for d in $4; do printf 'DNS=%s\n' "$d"; done
}

# Zum Testen nur die Funktionen laden: GRUNDEINRICHTUNG_NUR_FUNKTIONEN=1 source debian-grundeinrichtung.sh
[ -n "${GRUNDEINRICHTUNG_NUR_FUNKTIONEN:-}" ] && return 0

[ "$(id -u)" -eq 0 ] || fehler "Bitte als root starten: su -   und dann   bash $0"
command -v usermod >/dev/null || fehler 'usermod fehlt im Pfad. Mit "su -" (mit Minus) anmelden, nicht nur "su".'
export DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------------------------
# 1. sudo
# ---------------------------------------------------------------------------
schritt "1. Benutzer mit sudo"
command -v sudo >/dev/null || { apt-get update -q && apt-get install -y -q sudo >/dev/null; ok "sudo installiert"; }
VORSCHLAG="${SUDO_USER:-$(getent passwd | awk -F: '$3 >= 1000 && $3 < 65534 {print $1; exit}')}"
NUTZER="$(frage "Welcher Benutzer soll sudo bekommen? (leer: keiner)" "$VORSCHLAG")"
if [ -n "$NUTZER" ]; then
	if ! id "$NUTZER" >/dev/null 2>&1; then
		if ja "Benutzer $NUTZER gibt es nicht. Anlegen?"; then
			adduser --gecos "" "$NUTZER" </dev/tty
		else
			NUTZER=""
		fi
	fi
	if [ -n "$NUTZER" ]; then
		if id -nG "$NUTZER" | grep -qw sudo; then
			ok "$NUTZER ist schon in der Gruppe sudo"
		else
			usermod -aG sudo "$NUTZER"
			ok "$NUTZER ist jetzt in der Gruppe sudo (gilt nach neuer Anmeldung)"
		fi
	fi
fi

# ---------------------------------------------------------------------------
# 2. Rechnername
# ---------------------------------------------------------------------------
schritt "2. Rechnername"
ALT="$(hostname)"
NEU="$(frage "Rechnername (Buchstaben, Ziffern, Bindestrich)" "$ALT")"
if [ "$NEU" != "$ALT" ]; then
	[[ "$NEU" =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$ ]] || fehler "Ungültiger Rechnername: $NEU"
	hostnamectl set-hostname "$NEU"
	sichern /etc/hosts
	if grep -qE '^127\.0\.1\.1[[:space:]]' /etc/hosts; then
		sed -i -E "s/^127\.0\.1\.1[[:space:]].*/127.0.1.1\t${NEU}/" /etc/hosts
	else
		printf '127.0.1.1\t%s\n' "$NEU" >> /etc/hosts
	fi
	ok "Rechnername ist jetzt $NEU"
else
	ok "bleibt $ALT"
fi

# ---------------------------------------------------------------------------
# 3. Zeitzone
# ---------------------------------------------------------------------------
schritt "3. Zeitzone"
TZ_ALT="$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo unbekannt)"
TZ_NEU="$(frage "Zeitzone" "Europe/Berlin")"
if [ "$TZ_NEU" != "$TZ_ALT" ]; then
	[ -f "/usr/share/zoneinfo/$TZ_NEU" ] || fehler "Unbekannte Zeitzone: $TZ_NEU"
	timedatectl set-timezone "$TZ_NEU"
	ok "Zeitzone ist jetzt $TZ_NEU"
else
	ok "bleibt $TZ_ALT"
fi

# ---------------------------------------------------------------------------
# 4. Feste IP
# ---------------------------------------------------------------------------
schritt "4. Feste IP-Adresse"
NEUSTART=0
DEV="$(ip -4 route show default | awk '{for (i = 1; i < NF; i++) if ($i == "dev") {print $(i + 1); exit}}')"
GW_ALT="$(ip -4 route show default | awk '{for (i = 1; i < NF; i++) if ($i == "via") {print $(i + 1); exit}}')"
[ -n "$DEV" ] || fehler "Keine Standard-Route gefunden: ist der Rechner im Netz?"
ADR_ALT="$(ip -4 -o addr show dev "$DEV" | awk '{print $4; exit}')"   # z. B. 192.168.1.37/24
IP_ALT="${ADR_ALT%/*}"; PFX_ALT="${ADR_ALT#*/}"
DYNAMISCH=0; ip -4 -o addr show dev "$DEV" | grep -qw dynamic && DYNAMISCH=1
DNS_ALT="$(resolvectl dns "$DEV" 2>/dev/null | sed 's/.*://' | xargs || true)"
[ -n "$DNS_ALT" ] || DNS_ALT="$(awk '$1 == "nameserver" && $2 !~ /^127\./ {print $2}' /etc/resolv.conf | xargs || true)"
[ -n "$DNS_ALT" ] || DNS_ALT="$GW_ALT"

echo "    Netzwerkkarte: $DEV"
echo "    Adresse jetzt: $ADR_ALT ($([ "$DYNAMISCH" -eq 1 ] && echo "per DHCP" || echo "fest eingestellt"))"
echo "    Gateway: ${GW_ALT:-?}    DNS: ${DNS_ALT:-?}"

if [ "$DYNAMISCH" -eq 1 ] || ja "Die Adresse ist schon fest. Trotzdem ändern?"; then
	IP_NEU="$(frage "Feste IP (leer: DHCP behalten)" "")"
	if [ -n "$IP_NEU" ]; then
		PFX="$PFX_ALT"
		[[ "$IP_NEU" == */* ]] && { PFX="${IP_NEU#*/}"; IP_NEU="${IP_NEU%/*}"; }
		ip_gueltig "$IP_NEU" || fehler "Keine gültige IPv4-Adresse: $IP_NEU"
		[[ "$PFX" =~ ^[0-9]+$ ]] && [ "$PFX" -ge 8 ] && [ "$PFX" -le 30 ] || fehler "Präfix muss 8 bis 30 sein (z. B. 24 für 255.255.255.0)."
		GW="$(frage "Gateway" "$GW_ALT")"
		ip_gueltig "$GW" || fehler "Kein gültiges Gateway: $GW"
		DNS="$(frage "DNS-Server (mehrere mit Leerzeichen)" "$DNS_ALT")"
		for d in $DNS; do ip_gueltig "$d" || fehler "Kein gültiger DNS-Server: $d"; done
		gleiches_netz "$IP_NEU" "$GW" "$PFX" || fehler "$IP_NEU/$PFX und Gateway $GW liegen nicht im selben Netz."
		netz_oder_broadcast "$IP_NEU" "$PFX" && fehler "$IP_NEU ist die Netz- oder Broadcast-Adresse."
		[ "$IP_NEU" = "$GW" ] && fehler "Die Adresse darf nicht die des Gateways sein."
		if [ "$IP_NEU" != "$IP_ALT" ] && ping -c 1 -W 1 "$IP_NEU" >/dev/null 2>&1; then
			fehler "$IP_NEU antwortet schon im Netz: die Adresse ist vergeben."
		fi
		hinweis "Tipp: die Adresse im Router aus dem DHCP-Bereich nehmen bzw. dort reservieren."

		# Welche Netzwerk-Verwaltung ist zuständig?
		VERWALTUNG=""
		if systemctl is-active --quiet NetworkManager 2>/dev/null && nmcli -t -f DEVICE,STATE dev 2>/dev/null | grep -q "^${DEV}:connected"; then
			VERWALTUNG=networkmanager
		elif grep -qsE "^[[:space:]]*iface[[:space:]]+${DEV}[[:space:]]+inet" /etc/network/interfaces; then
			VERWALTUNG=ifupdown
		elif systemctl is-active --quiet systemd-networkd 2>/dev/null; then
			VERWALTUNG=networkd
		fi
		[ -n "$VERWALTUNG" ] || fehler "Netzwerk-Verwaltung nicht erkannt (weder NetworkManager, ifupdown noch systemd-networkd). Bitte von Hand einstellen."

		echo
		echo "    Neu:  $DEV  $IP_NEU/$PFX  Gateway $GW  DNS $DNS   (über $VERWALTUNG)"
		if ja "So speichern?"; then
			case "$VERWALTUNG" in
				networkmanager)
					CON="$(nmcli -t -f NAME,DEVICE con show --active | awk -F: -v d="$DEV" '$2 == d {print $1; exit}')"
					nmcli con mod "$CON" ipv4.method manual ipv4.addresses "$IP_NEU/$PFX" ipv4.gateway "$GW" \
						ipv4.dns "${DNS// /,}" ipv4.ignore-auto-dns yes
					;;
				ifupdown)
					sichern /etc/network/interfaces
					ifupdown_statisch /etc/network/interfaces "$DEV" "$IP_NEU/$PFX" "$GW" "$DNS" > /etc/network/interfaces.neu
					mv /etc/network/interfaces.neu /etc/network/interfaces
					# Ohne resolvconf liest niemand dns-nameservers: dann resolv.conf direkt schreiben
					if [ ! -L /etc/resolv.conf ] && ! command -v resolvconf >/dev/null; then
						sichern /etc/resolv.conf
						for d in $DNS; do echo "nameserver $d"; done > /etc/resolv.conf
					fi
					;;
				networkd)
					networkd_statisch "$DEV" "$IP_NEU/$PFX" "$GW" "$DNS" > "/etc/systemd/network/10-${DEV}-fest.network"
					;;
			esac
			# cloud-init (VM-Vorlagen) würde die Netz-Einstellung beim Start wieder überschreiben
			if [ -d /etc/cloud/cloud.cfg.d ]; then
				echo "network: {config: disabled}" > /etc/cloud/cloud.cfg.d/99-feste-ip.cfg
				hinweis "cloud-init: Netz-Einstellung abgeschaltet, damit die feste IP bleibt."
			fi
			ok "Gespeichert. Wirksam nach dem Neustart; danach erreichbar unter $IP_NEU."
			NEUSTART=1
		fi
	else
		ok "DHCP bleibt"
	fi
fi

# ---------------------------------------------------------------------------
# 5. Gast-Agent für Proxmox (nur in einer KVM-VM)
# ---------------------------------------------------------------------------
schritt "5. Proxmox-Gast-Agent"
VIRT="$(systemd-detect-virt 2>/dev/null || true)"
if [ "$VIRT" = "kvm" ] || [ "$VIRT" = "qemu" ]; then
	if dpkg -s qemu-guest-agent >/dev/null 2>&1; then
		ok "qemu-guest-agent ist schon installiert"
	else
		apt-get install -y -q qemu-guest-agent >/dev/null
		ok "qemu-guest-agent installiert"
	fi
	# Läuft nur, wenn in Proxmox unter Optionen der QEMU Guest Agent an ist (dann gibt es das Gerät dafür)
	if [ -e /dev/virtio-ports/org.qemu.guest_agent.0 ]; then
		systemctl start qemu-guest-agent 2>/dev/null && ok "läuft: Proxmox zeigt jetzt die IP der VM an"
	else
		hinweis "In Proxmox bei der VM unter Optionen den QEMU Guest Agent einschalten; wirkt erst, wenn die VM in Proxmox gestoppt und neu gestartet wird."
	fi
else
	ok "keine KVM-VM (${VIRT:-unbekannt}), nicht nötig"
fi

# ---------------------------------------------------------------------------
# Fertig
# ---------------------------------------------------------------------------
schritt "Fertig"
[ -n "${NUTZER:-}" ] && echo "    Mit $NUTZER neu anmelden, dann geht sudo (Test: sudo whoami → root)."
if [ "$NEUSTART" -eq 1 ]; then
	hinweis "Eine SSH-Verbindung reißt beim Neustart ab: danach mit der neuen Adresse $IP_NEU verbinden."
	hinweis "Falls der Rechner nicht wiederkommt: über die Konsole der VM anmelden, die Sicherung *.vor-grundeinrichtung zurückkopieren."
	if ja "Jetzt neu starten?"; then
		systemctl reboot
	else
		echo "    Später mit: systemctl reboot"
	fi
fi
