#!/bin/bash
# Run on the PC from the project root: copy the registry image made by
# make-registry.py to the tablet (USB SSH by default, TABS3_HOST to override)
# and restart the registry server. The image stays out of Git and packages.
set -euo pipefail
src=${1:-private/sensors}
host=${TABS3_HOST:-172.16.42.2}
ssh=(ssh -i private/id_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=5
     -o UserKnownHostsFile=private/installed-known-hosts -o HostKeyAlias=172.16.42.2 "dev@$host")
for f in registry.bin groups.conf; do
    [ -s "$src/$f" ] || { echo "$src/$f is missing; run make-registry.py first" >&2; exit 1; }
done
"${ssh[@]}" 'test "$(tr -d "\000" </proc/device-tree/model)" = "Samsung Galaxy Tab S3 LTE (SM-T825)"'
for f in registry.bin groups.conf; do
    "${ssh[@]}" "sudo -n mkdir -p /etc/sns-reg.d && sudo -n sh -c 'cat > /etc/sns-reg.d/$f.new' &&
                 sudo -n chmod 0644 /etc/sns-reg.d/$f.new && sudo -n mv /etc/sns-reg.d/$f.new /etc/sns-reg.d/$f" < "$src/$f"
done
local_sums=$(cd "$src" && sha256sum registry.bin groups.conf)
remote_sums=$("${ssh[@]}" 'cd /etc/sns-reg.d && sha256sum registry.bin groups.conf')
[ "$local_sums" = "$remote_sums" ] || { echo "copy on the tablet differs" >&2; exit 1; }
echo "$remote_sums"
"${ssh[@]}" 'if systemctl is-enabled --quiet tabs3-sns-reg.service; then sudo -n systemctl restart tabs3-sns-reg.service; fi'
echo "Registry installed; the sensor DSP reads it at its next start (reboot)."
