#!/usr/bin/env bash
# scripts/vault.sh - encrypt/decrypt private artifacts so their ciphertext can live in
# the shared repo while only the key holder can use them.
#
#   ./scripts/vault.sh encrypt data/enriched/corpus_v1.json        # -> corpus_v1.json.enc
#   ./scripts/vault.sh decrypt data/enriched/corpus_v1.json.enc    # -> corpus_v1.json
#
# The key lives OUTSIDE the repo in $VAULT_KEY_FILE (default ~/.agile-sourcing-vault.key)
# and is created on first encrypt. Never commit the key. AES-256-CBC with PBKDF2 via the
# openssl that ships with Git for Windows / any Linux.
set -euo pipefail

KEY_FILE="${VAULT_KEY_FILE:-$HOME/.agile-sourcing-vault.key}"
# Windows openssl needs a Windows-style path, not Git Bash's /c/...
KEY_ARG="$(cygpath -w "$KEY_FILE" 2>/dev/null || echo "$KEY_FILE")"
cmd="${1:-}"; src="${2:-}"
[ -n "$cmd" ] && [ -n "$src" ] || { echo "usage: $0 encrypt|decrypt <file>"; exit 1; }

if [ ! -f "$KEY_FILE" ]; then
    if [ "$cmd" = "encrypt" ]; then
        umask 177
        openssl rand -hex 32 > "$KEY_FILE"
        echo "new key written to $KEY_FILE - back it up somewhere private; without it the .enc files are unrecoverable"
    else
        echo "no key at $KEY_FILE (set VAULT_KEY_FILE or restore your backup)"; exit 1
    fi
fi

case "$cmd" in
    encrypt)
        openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
            -pass "file:$KEY_ARG" -in "$src" -out "$src.enc"
        echo "encrypted -> $src.enc ($(wc -c < "$src.enc") bytes)";;
    decrypt)
        out="${src%.enc}"
        openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
            -pass "file:$KEY_ARG" -in "$src" -out "$out"
        echo "decrypted -> $out";;
    *)
        echo "usage: $0 encrypt|decrypt <file>"; exit 1;;
esac
