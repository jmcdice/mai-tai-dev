#!/usr/bin/env bash
#
# verify-boot-cron-env.sh - Prove the @reboot/cron path can actually start the
# mai-tai bots, WITHOUT waiting for a real reboot.
#
# It installs a one-shot cron job (fires the next minute) that runs under the
# REAL cron daemon's environment -- identical to what @reboot gets -- sources
# ~/.bash_profile exactly like boot-mai-tai.sh does, and records whether
# claude / node / tmux / uvx / timeout and the Vertex auth vars all resolve.
# Then it prints a PASS/FAIL verdict and restores your crontab.
#
# Safe: backs up your crontab and restores it via an EXIT trap no matter what.
# Non-disruptive: does NOT touch the running bots.
#
# Run as yourself:   ./scripts/verify-boot-cron-env.sh
# Or via sudo:       sudo ./scripts/verify-boot-cron-env.sh
#   (either way it probes the 'joey' user's crontab, since that's what @reboot uses)
#
set -uo pipefail

TARGET_USER="joey"                    # the user the @reboot job runs as
OUT="/tmp/mai-tai-cron-probe.$$.out"
PROBE="/tmp/mai-tai-cron-probe.$$.sh"

# Address the right crontab whether we're root (sudo) or the user.
if [ "$(id -u)" -eq 0 ]; then
  CRONTAB=(crontab -u "$TARGET_USER")
else
  if [ "$(id -un)" != "$TARGET_USER" ]; then
    echo "WARN: running as $(id -un), not $TARGET_USER. Re-run as $TARGET_USER or with sudo." >&2
  fi
  CRONTAB=(crontab)
fi

echo "Probing the real cron environment for user '$TARGET_USER'..."

# The probe: runs under cron, mimics boot-mai-tai.sh's env setup, records results.
cat > "$PROBE" <<PROBE_EOF
#!/usr/bin/env bash
{
  echo "PROBE_RAN=1"
  echo "whoami=\$(id -un)  HOME=\$HOME"
  echo "--- raw cron PATH ---"; echo "PATH=\$PATH"
  # exactly what boot-mai-tai.sh / mai-tai-supervisor.sh do:
  set +u
  [ -f "\$HOME/.bash_profile" ] && . "\$HOME/.bash_profile" >/dev/null 2>&1
  set -u
  echo "--- after sourcing ~/.bash_profile ---"
  for t in claude node tmux uvx timeout git; do
    echo "\$t=\$(command -v \$t 2>/dev/null || echo MISSING)"
  done
  echo "CLAUDE_CODE_USE_VERTEX=\${CLAUDE_CODE_USE_VERTEX:-unset}"
  echo "ANTHROPIC_VERTEX_PROJECT_ID=\${ANTHROPIC_VERTEX_PROJECT_ID:-unset}"
  echo "CLOUD_ML_REGION=\${CLOUD_ML_REGION:-unset}"
  # ADC file that Vertex auth needs (env alone isn't enough):
  adc="\$HOME/.config/gcloud/application_default_credentials.json"
  echo "gcloud_ADC=\$( [ -f "\$adc" ] && echo present || echo MISSING )"
  echo "backend_health=\$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://192.168.86.39:8000/health 2>/dev/null)"
} > "$OUT" 2>&1
PROBE_EOF
chmod +x "$PROBE"
chown "$TARGET_USER" "$PROBE" 2>/dev/null || true

# Backup crontab and guarantee restore on exit.
BK="/tmp/mai-tai-crontab-backup.$$"
"${CRONTAB[@]}" -l > "$BK" 2>/dev/null || : > "$BK"
cleanup() {
  "${CRONTAB[@]}" "$BK" 2>/dev/null || "${CRONTAB[@]}" - < "$BK" 2>/dev/null
  rm -f "$PROBE" "$BK"
  echo "(crontab restored)"
}
trap cleanup EXIT

# Install temp probe line (fires every minute; we remove it after first run).
{ cat "$BK"; echo "* * * * * /usr/bin/bash $PROBE"; } | "${CRONTAB[@]}" - || {
  echo "FAILED to install probe crontab. If you saw 'Permission denied', run with sudo." >&2
  exit 1
}

echo "Installed one-shot probe. Waiting up to ~90s for cron to fire..."
for _ in $(seq 1 18); do [ -s "$OUT" ] && break; sleep 5; done

echo
if [ ! -s "$OUT" ]; then
  echo "RESULT: probe did not run within 90s. Is the cron daemon running? (systemctl status cron)"
  exit 1
fi

echo "===== real cron-env probe output ====="
cat "$OUT"
echo "======================================"
echo
# Verdict
missing="$(grep -E "=MISSING" "$OUT" | cut -d= -f1 | tr '\n' ' ')"
vertex_ok=1
grep -q "CLAUDE_CODE_USE_VERTEX=1" "$OUT" || vertex_ok=0
grep -q "gcloud_ADC=present" "$OUT" || true   # informational
if [ -z "$missing" ] && [ "$vertex_ok" -eq 1 ]; then
  echo "VERDICT: ✅ PASS - cron env resolves all tools + Vertex vars. @reboot should start the bots."
else
  echo "VERDICT: ⚠  ATTENTION"
  [ -n "$missing" ] && echo "  Missing under cron: $missing  -> add these to ~/.bash_profile's PATH."
  [ "$vertex_ok" -eq 0 ] && echo "  CLAUDE_CODE_USE_VERTEX not set under cron -> check ~/.bash_profile."
  echo "  (Fix the profile so these resolve; the boot script sources it, so that's the lever.)"
fi
rm -f "$OUT"
