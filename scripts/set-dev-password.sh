#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Account password for the tablet's dev user. Only a SHA-512 crypt hash is
# kept, in private/dev-password.hash. SSH password login is optional and
# disabled by default. Reads one line from stdin when it is not a terminal.
if [[ -t 0 ]]; then
    read -rsp 'Password for dev on the tablet: ' pw; echo
    read -rsp 'Again: ' again; echo
else
    IFS= read -r pw
    again=$pw
fi
[[ -n "$pw" && "$pw" == "$again" ]] || { echo 'Password is empty or does not match' >&2; exit 1; }
hash=$(printf '%s' "$pw" | docker run --rm -i tabs3-builder:trixie openssl passwd -6 -stdin)
[[ "$hash" == "\$6\$"* ]]
mkdir -p private
chmod 700 private
umask 077
printf '%s\n' "$hash" > private/dev-password.hash
echo 'Saved private/dev-password.hash'
