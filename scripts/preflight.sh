#!/usr/bin/env bash
# Demo preflight / QA checklist (P4). Run on the RTX node at T-30 min:  bash scripts/preflight.sh
# Every line prints ✔ or ✘; exit code = number of failures. Also warms the models.
set -uo pipefail

APP=$(cd "$(dirname "$0")/.." && pwd)
GW=${KAIROS_GATEWAY:-http://127.0.0.1:8080}
OLLAMA=${KAIROS_OLLAMA_URL:-http://127.0.0.1:11434}
COMPOSE=(docker compose -f "$APP/infra/compose/docker-compose.yml" -f "$APP/infra/compose/docker-compose.gpu.yml")
PY="$APP/.venv/bin/python"
FAIL=0

check() {  # check "<label>" <command...>
  local label=$1; shift
  if "$@" >/dev/null 2>&1; then printf '  \033[32m✔\033[0m %s\n' "$label"; else printf '  \033[31m✘\033[0m %s\n' "$label"; FAIL=$((FAIL + 1)); fi
}

echo "services"
check "kairosd.service active" systemctl is-active --quiet kairosd
if systemctl is-enabled --quiet kairos-web 2>/dev/null; then
  check "kairos-web.service active" systemctl is-active --quiet kairos-web
else
  printf '  \033[33m–\033[0m %s\n' "kairos-web.service not installed (apps/web missing or KAIROS_PUBLIC_URL unset): skipped"
fi
for s in postgres redis ollama mock-jira vendor-docs; do
  check "compose: $s running" bash -c "[ -n \"\$(${COMPOSE[*]} ps --status running -q $s)\" ]"
done
check "gateway /system/status ready" bash -c "curl -fsS -m 5 $GW/system/status | jq -e '.ready == true'"
check "all components real" bash -c "curl -fsS -m 5 $GW/system/status | jq -e '[.components[].mode] | all(. == \"real\")'"

echo "gpu + models"
check "GPU visible inside the ollama container" "${COMPOSE[@]}" exec -T ollama nvidia-smi
MODELS=$("$PY" - "$APP/models/models.yaml" <<'PY'
import sys, yaml
c = yaml.safe_load(open(sys.argv[1]))
print(" ".join(sorted({c["embedding"], c["default"], c.get("latency_critical") or c["default"], *(c.get("by_task_class") or {}).values()})))
PY
)
EMBED=$("$PY" -c "import yaml,sys; print(yaml.safe_load(open(sys.argv[1]))['embedding'])" "$APP/models/models.yaml")
TAGS=$(curl -fsS -m 5 "$OLLAMA/api/tags" | jq -r '.models[].name')
for m in $MODELS; do
  check "model pulled: $m" grep -qxE "${m}(:latest)?" <<<"$TAGS"
done
for m in $MODELS; do
  if [[ $m == "$EMBED" ]]; then
    check "warm: $m" curl -fsS -m 120 "$OLLAMA/api/embed" -d "{\"model\":\"$m\",\"input\":\"warmup\",\"keep_alive\":-1}"
  else
    check "warm: $m" curl -fsS -m 180 "$OLLAMA/api/generate" -d "{\"model\":\"$m\",\"prompt\":\"ok\",\"stream\":false,\"keep_alive\":-1,\"options\":{\"num_predict\":1}}"
  fi
done

echo "sandboxes + browser"
check "image kairos/sandbox-base" docker image inspect kairos/sandbox-base:latest
check "image kairos/sandbox-browser" docker image inspect kairos/sandbox-browser:latest
check "browser smoke (vendor-docs through the sandbox)" "$PY" "$APP/scripts/browser_smoke.py"

echo "knowledge"
check "bundle valid (scripts/check_okf.py)" "$PY" "$APP/scripts/check_okf.py"
check "search 'apollo budget' returns hits" bash -c "curl -fsS -m 10 -H 'X-Kairos-User: preflight' -H 'X-Kairos-Org: acme' '$GW/knowledge/search?q=apollo%20budget&top_k=3' | jq -e '.hits | length > 0'"

echo "host"
check "/sovereign-data has > 10 GB free" bash -c "[ \$(df --output=avail -BG /sovereign-data | tail -1 | tr -dc 0-9) -gt 10 ]"
check "lid switch ignored" grep -rqs '^HandleLidSwitch=ignore' /etc/systemd/logind.conf.d/
check "tailscale up" tailscale status

echo
if [[ $FAIL -eq 0 ]]; then echo "preflight: all green"; else echo "preflight: $FAIL check(s) failed"; fi
exit "$FAIL"
