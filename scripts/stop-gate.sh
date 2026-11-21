#!/usr/bin/env bash
# Hook Stop: najwyzej 2 wymuszone rundy poprawek, potem puszcza.
# Licznik i log sa osobne dla kazdego katalogu projektu (takze dla worktree).
# Awaryjnie: touch /tmp/gate.off wylacza bramke na tej maszynie, rm /tmp/gate.off wlacza.
[ -f /tmp/gate.off ] && exit 0
dir="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
id=$(printf '%s' "$dir" | cksum | cut -d' ' -f1)
count=/tmp/stop-gate.$id.count
log=/tmp/gate.$id.log
if bash "$dir/scripts/gate.sh" > "$log" 2>&1; then
  rm -f "$count"; exit 0
fi
n=$(( $(cat "$count" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$count"
if [ "$n" -gt 2 ]; then rm -f "$count"; exit 0; fi
echo "GATE: FAIL, runda $n z 2. Pelny log: $log" >&2
tail -n 30 "$log" >&2
exit 2
