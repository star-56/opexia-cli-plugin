#!/bin/bash
# OpexIA dev-log — Stop hook.
#
# When Claude finishes a task in a repo that has opted into the dev-log, this
# nudges Claude to enrich any commit entries the post-commit hook left as stubs
# (enriched: false) — filling the reasoning/logic and wiring the semantic graph
# edges. It blocks the stop with an instruction (Claude then runs the opexia:log
# enrich flow), and gives up after 2 no-progress rounds so it can NEVER loop.
#
# Fail-open everywhere: any problem => allow the stop (exit 0). Telemetry about
# the build must never trap the developer's session.

set +e

HOOK_INPUT=$(cat 2>/dev/null)

DEVLOG=".opexia/devlog"
ENTRIES="$DEVLOG/entries"
[ -d "$ENTRIES" ] || exit 0                     # repo hasn't opted in — allow stop

# Count entries still awaiting enrichment.
COUNT=$(grep -rl '^enriched: false' "$ENTRIES" 2>/dev/null | wc -l | tr -d ' ')
[ -n "$COUNT" ] || COUNT=0
[ "$COUNT" -gt 0 ] 2>/dev/null || exit 0        # nothing pending — allow stop

# session id (no jq dependency).
SESSION=$(printf '%s' "$HOOK_INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
[ -n "$SESSION" ] || SESSION="unknown"

# Loop guard: give up after 2 rounds with NO progress in the same session.
# State: "SESSION LASTCOUNT ATTEMPTS".
STATE="$DEVLOG/.enrich-state"
LAST_SESSION=""; LAST_COUNT=0; ATTEMPTS=0
if [ -f "$STATE" ]; then
  read -r LAST_SESSION LAST_COUNT ATTEMPTS < "$STATE" 2>/dev/null
  [ -n "$LAST_COUNT" ] || LAST_COUNT=0
  [ -n "$ATTEMPTS" ] || ATTEMPTS=0
fi

if [ "$SESSION" = "$LAST_SESSION" ]; then
  if [ "$COUNT" -lt "$LAST_COUNT" ] 2>/dev/null; then
    ATTEMPTS=0                                  # progress since last nudge — reset
  fi
else
  ATTEMPTS=0                                    # new session — reset
fi

if [ "$ATTEMPTS" -ge 2 ] 2>/dev/null; then
  # Two no-progress rounds — stop nagging so we never trap the session.
  echo "OpexIA dev-log: $COUNT entr(ies) still un-enriched; not blocking again this session. Run /opexia:log to finish." >&2
  exit 0
fi

NEXT=$((ATTEMPTS + 1))
printf '%s %s %s\n' "$SESSION" "$COUNT" "$NEXT" > "$STATE" 2>/dev/null

REASON="The OpexIA dev-log has ${COUNT} commit entr(ies) awaiting reasoning (enriched: false) under .opexia/devlog/entries/. Invoke the opexia:log skill and enrich them: for each pending entry fill What / Why-Logic / Decisions / Agent, add the semantic relations (implements, touches, driven_by, fixes), set enriched: true, then run the graph rebuild. After that you may stop."
MSG="OpexIA dev-log: enriching ${COUNT} pending commit entr(ies)"

# Stop-hook contract: block the stop and feed 'reason' back to Claude as the
# instruction to act on. No jq — REASON/MSG are controlled, quote/newline-free.
printf '{"decision":"block","reason":"%s","systemMessage":"%s"}\n' "$REASON" "$MSG"
exit 0
