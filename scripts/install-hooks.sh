#!/usr/bin/env bash
# Install git hooks (symlink from .git/hooks to scripts/git-hooks).
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS_SRC="$REPO_ROOT/scripts/git-hooks"
HOOKS_DST="$REPO_ROOT/.git/hooks"

if [ ! -d "$HOOKS_DST" ]; then
    echo "Error: $HOOKS_DST does not exist."
    exit 1
fi

for hook in "$HOOKS_SRC"/*; do
    [ -e "$hook" ] || continue
    name=$(basename "$hook")
    target="$HOOKS_DST/$name"
    if [ -e "$target" ] || [ -L "$target" ]; then
        echo "Backing up existing $name -> $name.backup"
        mv "$target" "$target.backup"
    fi
    ln -s "$hook" "$target"
    echo "Installed: $name -> $hook"
done

echo "Done."
