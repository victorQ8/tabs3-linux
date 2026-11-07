#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Console login password for the tablet's dev account. Only a SHA-512 crypt
# hash is kept, in private/dev-password.hash; SSH stays key-only. Reads one
# line from standard input when it is not a terminal.
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
