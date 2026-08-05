#!/usr/bin/env bash
# infra/delivery/verify-dns.sh — deliverability DNS preflight for the delivery worker (#1412).
#
# Run this AFTER you add the Cloudflare records (SPF / DKIM / DMARC) and Resend domain
# verification, BEFORE enabling sends. It is READ-ONLY (dig lookups only) — it changes
# nothing. It catches the mistakes that silently spam-folder mail: a second SPF record,
# an unresolved DKIM CNAME, a missing/`p=`-less DMARC, a broken MX.
#
# Usage:
#   bash infra/delivery/verify-dns.sh [SENDING_DOMAIN] [DKIM_HOST ...]
# Examples:
#   bash infra/delivery/verify-dns.sh closelistening.app
#   bash infra/delivery/verify-dns.sh mail.closelistening.app resend._domainkey.mail.closelistening.app
#
# SENDING_DOMAIN defaults to closelistening.app. Pass the exact DKIM host(s) Resend shows
# after domain-add (they are per-domain and cannot be guessed); each is checked as a CNAME.
# Exit code: 0 = all PASS, 1 = at least one FAIL. WARN does not fail the run.

set -uo pipefail

DOMAIN="${1:-closelistening.app}"
shift || true
DKIM_HOSTS=("$@")

PASS=0 FAIL=0 WARN=0
green() { printf '\033[32mPASS\033[0m %s\n' "$1"; PASS=$((PASS + 1)); }
red()   { printf '\033[31mFAIL\033[0m %s\n' "$1"; FAIL=$((FAIL + 1)); }
yellow(){ printf '\033[33mWARN\033[0m %s\n' "$1"; WARN=$((WARN + 1)); }

command -v dig >/dev/null 2>&1 || { echo "dig not found (install bind/dnsutils)"; exit 2; }

echo "== Deliverability DNS preflight for ${DOMAIN} =="
echo

# Resend uses SES underneath: the MAIL FROM / return-path lives on `send.<domain>` (its own
# MX + SPF), DKIM is a TXT/CNAME at `resend._domainkey.<domain>`, and DMARC is at the org
# domain. So SPF + MX are checked on the return-path subdomain, NOT the top domain.
RETURN_PATH="send.${DOMAIN}"

# --- SPF on the return-path subdomain (Resend: include:amazonses.com) --------------------
# (while-read, not mapfile — macOS ships bash 3.2 where mapfile is absent.)
SPF=()
while IFS= read -r line; do [ -n "${line}" ] && SPF+=("${line}"); done \
	< <(dig +short TXT "${RETURN_PATH}" | tr -d '"' | grep -i '^v=spf1')
if [ "${#SPF[@]}" -eq 0 ]; then
	red "SPF: no v=spf1 TXT on ${RETURN_PATH} — Resend return-path SPF missing"
elif [ "${#SPF[@]}" -gt 1 ]; then
	red "SPF: ${#SPF[@]} SPF records on ${RETURN_PATH} — RFC 7208 allows exactly ONE (merge)"
	printf '     %s\n' "${SPF[@]}"
else
	if grep -qiE 'include:(amazonses.com|_spf.resend.com)' <<<"${SPF[0]}"; then
		green "SPF: ${RETURN_PATH} — ${SPF[0]}"
	else
		yellow "SPF: ${RETURN_PATH} has SPF but no amazonses/resend include — ${SPF[0]}"
	fi
	grep -qiE '[~-]all' <<<"${SPF[0]}" || yellow "SPF: no ~all/-all qualifier (recommended)"
fi
echo

# --- MX on the return-path subdomain (bounces → feedback-smtp.<region>.amazonses.com) -----
MX_RP="$(dig +short MX "${RETURN_PATH}")"
if [ -z "${MX_RP}" ]; then
	red "MX: no MX on ${RETURN_PATH} — Resend return-path/bounce record missing"
elif grep -qiE 'amazonses.com|feedback-smtp' <<<"${MX_RP}"; then
	green "MX: ${RETURN_PATH} → $(tr '\n' ' ' <<<"${MX_RP}")"
else
	yellow "MX: ${RETURN_PATH} has an MX but not the amazonses feedback host — $(tr '\n' ' ' <<<"${MX_RP}")"
fi
echo

# --- DKIM: TXT (p=) or CNAME at resend._domainkey.<domain> (or any passed host) -----------
[ "${#DKIM_HOSTS[@]}" -eq 0 ] && DKIM_HOSTS=("resend._domainkey.${DOMAIN}")
for host in "${DKIM_HOSTS[@]}"; do
	cname="$(dig +short CNAME "${host}")"
	txt="$(dig +short TXT "${host}" | tr -d '"')"
	if [ -n "${cname}" ]; then
		green "DKIM: ${host} → ${cname}"
	elif grep -qi 'p=' <<<"${txt}"; then
		green "DKIM: ${host} TXT public key present (Resend TXT-style DKIM)"
	else
		red "DKIM: ${host} does not resolve (CNAME or p= TXT) — missing/not propagated"
	fi
done
echo

# --- DMARC: at the ORG domain (strip a leading sending-subdomain label) -------------------
ORG="${DOMAIN}"
if [ "$(tr -cd '.' <<<"${DOMAIN}" | wc -c)" -ge 2 ]; then
	ORG="${DOMAIN#*.}"  # mail.closelistening.app -> closelistening.app
fi
DMARC="$(dig +short TXT "_dmarc.${ORG}" | tr -d '"' | grep -i '^v=DMARC1')"
if [ -z "${DMARC}" ]; then
	red "DMARC: no v=DMARC1 TXT on _dmarc.${ORG}"
else
	if grep -qiE 'p=(none|quarantine|reject)' <<<"${DMARC}"; then
		green "DMARC: ${DMARC}"
		grep -qi 'p=none' <<<"${DMARC}" && yellow "DMARC: p=none is monitor-only — ramp to quarantine/reject once aligned"
	else
		red "DMARC: record present but no p= policy tag — ${DMARC}"
	fi
	grep -qi 'rua=' <<<"${DMARC}" || yellow "DMARC: no rua= aggregate-report address (recommended)"
fi
echo

echo "== ${PASS} pass, ${FAIL} fail, ${WARN} warn =="
if [ "${FAIL}" -eq 0 ]; then
	echo "DNS preflight: OK"
	exit 0
fi
echo "DNS preflight: FAIL"
exit 1
