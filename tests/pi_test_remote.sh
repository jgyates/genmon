#!/bin/bash
# -------------------------------------------------------------------------------
#    FILE: pi_test_remote.sh
# PURPOSE: The part of tests/run_pi_tests.sh that runs on the Raspberry Pi.
#          run_pi_tests.sh sends this file over ssh ("bash -s"), so it does not
#          have to be on the Pi already. It only uses a test copy of genmon in
#          the Pi user's home folder; a genmon installed on the Pi (e.g. in
#          /home/pi/genmon with /etc/genmon) is not changed or stopped.
#
#          Steps (STEPS, any of): update unit live
#            update  git pull the test copy (GENMON_DIR, a git checkout)
#            unit    the unit tests and the simulator tests, with genmon's own
#                    Python environment (GENMON_DIR/genenv)
#            live    for each capture in CAPTURES (tests/sim/captures): start
#                    gensim on this Pi with it, set the test genmon.conf for it,
#                    restart the test genmon, wait for it to read the
#                    controller, run tests/test_genmon_api.py against it, and
#                    check the new lines in its logs for errors
#
#          Settings (environment, the defaults are in the Pi user's home):
#            GENMON_DIR   test copy of genmon         (~/genmon)
#            CONF_DIR     its config folder           (~/genmonconfig)
#            LOG_DIR      its log folder              (~/genmonlogs)
#            SIM_DIR      gensim's folder             (~/gensim)
#            GENMON_PORT  genmon port                 (9182)
#            WEB_PORT     web interface port          (8182)
#            HTTPS_PORT   web interface HTTPS port    (8443)
#            SIM_PORT     gensim port, this Pi only   (9990)
#            CAPTURES     capture names, comma separated, or "all" (evo_ac)
#            KEEP         1: leave the test genmon and gensim running
#
#          The test genmon.conf is set for testing: multi_instance (so it runs
#          next to another genmon), its own ports and log folder, no email, no
#          update check, no feedback to the developer.
# -------------------------------------------------------------------------------

GENMON_DIR="${GENMON_DIR:-$HOME/genmon}"
CONF_DIR="${CONF_DIR:-$HOME/genmonconfig}"
LOG_DIR="${LOG_DIR:-$HOME/genmonlogs}"
SIM_DIR="${SIM_DIR:-$HOME/gensim}"
GENMON_PORT="${GENMON_PORT:-9182}"
WEB_PORT="${WEB_PORT:-8182}"
HTTPS_PORT="${HTTPS_PORT:-8443}"
SIM_PORT="${SIM_PORT:-9990}"
CAPTURES="${CAPTURES:-evo_ac}"
STEPS="${STEPS:-update unit live}"
KEEP="${KEEP:-0}"

PYTHON="$GENMON_DIR/genenv/bin/python"
FAILED=0
SUMMARY=""

note() { SUMMARY="$SUMMARY$1"$'\n'; echo "$1"; }
fail() { FAILED=1; note "FAIL  $1"; }
has_step() { [[ " $STEPS " == *" $1 "* ]]; }

if [ ! -x "$PYTHON" ]; then
  echo "Not found: $PYTHON (install genmon in $GENMON_DIR first: genmonmaint.sh -i)"
  exit 2
fi
cd "$GENMON_DIR" || exit 2

# one test run at a time: runs share the test genmon, gensim and their config.
# A folder is the lock (mkdir is atomic); it holds the run's process id, so the
# lock of a run that did not end normally (e.g. the ssh connection was lost) is
# taken over. Not flock: gensim and genmon would inherit its file descriptor
LOCK_DIR="$HOME/.genmon_pi_tests.lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  OTHER="$(cat "$LOCK_DIR/pid" 2>/dev/null)"
  if [ -n "$OTHER" ] && kill -0 "$OTHER" 2>/dev/null; then
    echo "Another genmon test run is in progress on this Pi (process $OTHER, started" \
      "$(ps -o lstart= -p "$OTHER" 2>/dev/null | xargs)); try again when it has finished"
    exit 3
  fi
  rm -rf "$LOCK_DIR"
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "Another genmon test run is starting on this Pi; try again when it has finished"
    exit 3
  fi
fi
echo $$ > "$LOCK_DIR/pid"
trap 'rm -rf "$LOCK_DIR"' EXIT

# -------------------------------------------------------------------------------
if has_step update; then
  echo "=== update $GENMON_DIR"
  if git pull -q --ff-only; then
    note "OK    updated to $(git log --oneline -1)"
  else
    fail "git pull (local changes in $GENMON_DIR?)"
  fi
fi

# -------------------------------------------------------------------------------
if has_step unit; then
  echo "=== unit and simulator tests ($($PYTHON --version))"
  OUTPUT="$(GENMON_CAPTURES=tests/sim/captures "$PYTHON" -m unittest discover -s tests 2>&1)"
  RESULT="$(echo "$OUTPUT" | grep -E "^Ran [0-9]+ tests")  $(echo "$OUTPUT" | tail -1)"
  if echo "$OUTPUT" | tail -1 | grep -q "^OK"; then
    note "OK    unit tests: $RESULT"
  else
    echo "$OUTPUT" | grep -E "^(FAIL|ERROR):" | head -20
    fail "unit tests: $RESULT"
  fi
fi

# -------------------------------------------------------------------------------
stop_gensim() {
  if [ -f "$SIM_DIR/gensim.pid" ]; then
    kill "$(cat "$SIM_DIR/gensim.pid")" 2>/dev/null
    rm -f "$SIM_DIR/gensim.pid"
    sleep 1
  fi
}

wait_for_port() {  # port seconds
  for _ in $(seq 1 "$2"); do
    ss -ltn | grep -q ":$1 " && return 0
    sleep 1
  done
  return 1
}

# the capture's settings as KEY=VALUE lines (from tests/sim/captures)
capture_settings() {
  "$PYTHON" - "$1" <<'EOF'
import json, sys
name = sys.argv[1]
captures = json.load(open("tests/sim/captures/captures.json"))["captures"]
names = [c["name"] for c in captures]
if name == "all":
    print("NAMES=" + " ".join(names))
    sys.exit()
capture = next((c for c in captures if c["name"] == name), None)
if capture is None:
    sys.exit("unknown capture %s (one of: %s)" % (name, ", ".join(names)))
for key in ["file", "address", "controllertype", "model", "nominalkw", "controller"]:
    print("%s=%s" % (key.upper(), capture[key]))
settings = dict(capture.get("settings", {}))
settings["fueltype"] = capture.get("fueltype", "Natural Gas")
print("EXTRA=" + json.dumps(settings))
EOF
}

# set the test genmon.conf / mymail.conf (they belong to root)
configure_genmon() {  # address controllertype model nominalkw extra_json
  sudo -n "$PYTHON" - "$CONF_DIR" "$@" "$GENMON_PORT" "$WEB_PORT" "$HTTPS_PORT" "$SIM_PORT" "$LOG_DIR" <<'EOF'
import json, os, sys
sys.path.insert(0, os.getcwd())
from genmonlib.myconfig import MyConfig
conf_dir, address, controllertype, model, nominalkw, extra, genmon_port, web_port, https_port, sim_port, logs = sys.argv[1:]
conf = MyConfig(filename=os.path.join(conf_dir, "genmon.conf"), section="GenMon")
values = {
    "use_serial_tcp": "True", "serial_tcp_address": "127.0.0.1", "serial_tcp_port": sim_port,
    "modbus_tcp": "False", "address": address, "controllertype": controllertype, "model": model,
    "nominalkw": nominalkw, "server_port": genmon_port, "http_port": web_port, "https_port": https_port,
    "loglocation": logs.rstrip("/") + "/", "multi_instance": "True", "sitename": "Pi Test",
    "update_check": "False", "autofeedback": "False", "disableweather": "True",
}
values.update(json.loads(extra))
for key, value in values.items():
    conf.WriteValue(key, str(value))
mail = MyConfig(filename=os.path.join(conf_dir, "mymail.conf"), section="MyMail")
for key in ["disableemail", "disablesmtp", "disableimap"]:
    mail.WriteValue(key, "True")
EOF
}

# wait until genmon has read the controller; prints the controller name
wait_for_genmon() {
  "$PYTHON" - "$GENMON_PORT" <<'EOF'
import json, logging, sys, time
sys.path.insert(0, ".")
from genmonlib.myclient import ClientInterface
log = logging.getLogger("pi_test")
log.addHandler(logging.NullHandler())
log.propagate = False
end = time.time() + 120
while time.time() < end:
    try:
        client = ClientInterface(host="127.0.0.1", port=int(sys.argv[1]), log=log)
        info = json.loads(client.ProcessMonitorCommand("generator: start_info_json"))
        if info.get("Controller"):
            base = client.ProcessMonitorCommand("generator: getbase")
            if base and "retry" not in base.lower():
                print(info["Controller"])
                sys.exit(0)
    except Exception:
        pass
    time.sleep(3)
sys.exit(1)
EOF
}

log_sizes() {  # "file size" for each log file
  for f in "$LOG_DIR"/*.log; do
    [ -f "$f" ] && echo "$f $(stat -c %s "$f")"
  done
}

new_log_errors() {  # the log sizes from before: errors in the lines added since
  local before="$1"
  for f in "$LOG_DIR"/*.log; do
    [ -f "$f" ] || continue
    local size
    size="$(echo "$before" | awk -v f="$f" '$1 == f {print $2}')"
    # (the api test reads register 0000, which only Evolution / Nexus have)
    tail -c +"$(( ${size:-0} + 1 ))" "$f" | grep -iE "error|unable|traceback" \
      | grep -v "Register  not known:0000" | sed "s|^|$(basename "$f"): |"
  done
}

if has_step live; then
  if [ "$CAPTURES" = "all" ]; then
    CAPTURES="$(capture_settings all | sed -n 's/^NAMES=//p' | tr ' ' ',')"
  fi
  if [ -z "$CAPTURES" ]; then
    fail "no captures to test"
  fi
  mkdir -p "$SIM_DIR" "$LOG_DIR"
  if [ ! -f "$CONF_DIR/genmon.conf" ]; then
    echo "=== making $CONF_DIR (genmonmaint.sh -s)"
    sudo -n bash "$GENMON_DIR/genmonmaint.sh" -s -c "$CONF_DIR" > /dev/null
  fi
  IFS=',' read -r -a CAPTURE_LIST <<< "$CAPTURES"
  for CAPTURE in "${CAPTURE_LIST[@]}"; do
    echo "=== live test: $CAPTURE"
    SETTINGS="$(capture_settings "$CAPTURE")" || { fail "$CAPTURE: unknown capture"; continue; }
    FILE="$(echo "$SETTINGS" | sed -n 's/^FILE=//p')"
    ADDRESS="$(echo "$SETTINGS" | sed -n 's/^ADDRESS=//p')"
    CONTROLLERTYPE="$(echo "$SETTINGS" | sed -n 's/^CONTROLLERTYPE=//p')"
    MODEL="$(echo "$SETTINGS" | sed -n 's/^MODEL=//p')"
    NOMINALKW="$(echo "$SETTINGS" | sed -n 's/^NOMINALKW=//p')"
    CONTROLLER="$(echo "$SETTINGS" | sed -n 's/^CONTROLLER=//p')"
    EXTRA="$(echo "$SETTINGS" | sed -n 's/^EXTRA=//p')"

    sudo -n bash "$GENMON_DIR/startgenmon.sh" stop -c "$CONF_DIR" > /dev/null 2>&1
    stop_gensim
    printf "[gensim]\naddress = %s\nregister_file = %s\nserver_socket = %s\nbind_address = 127.0.0.1\nlog_location = %s/\n" \
      "$ADDRESS" "$GENMON_DIR/tests/sim/captures/$FILE" "$SIM_PORT" "$SIM_DIR" > "$SIM_DIR/gensim.conf"
    nohup "$PYTHON" "$GENMON_DIR/tests/sim/gensim.py" "$SIM_DIR/" > "$SIM_DIR/console.txt" 2>&1 &
    echo $! > "$SIM_DIR/gensim.pid"
    if ! wait_for_port "$SIM_PORT" 15; then
      fail "$CAPTURE: gensim did not start (see $SIM_DIR/console.txt)"
      continue
    fi

    configure_genmon "$ADDRESS" "$CONTROLLERTYPE" "$MODEL" "$NOMINALKW" "$EXTRA"
    BEFORE="$(log_sizes)"
    sudo -n bash "$GENMON_DIR/startgenmon.sh" start -c "$CONF_DIR" > /dev/null 2>&1
    # (the client prints genmon's greeting to stderr)
    DETECTED="$(wait_for_genmon 2>/dev/null)"
    if [ -z "$DETECTED" ]; then
      fail "$CAPTURE: genmon did not answer (see $LOG_DIR/genmon.log)"
      continue
    fi
    PROBLEMS=""
    if [[ "$DETECTED" != "$CONTROLLER"* ]]; then
      PROBLEMS="$PROBLEMS, controller is \"$DETECTED\" (expected \"$CONTROLLER\")"
    fi
    wait_for_port "$WEB_PORT" 30
    API="$("$PYTHON" tests/test_genmon_api.py -p "$GENMON_PORT" -w "$WEB_PORT" 2>&1)"
    API_RESULT="$(echo "$API" | tail -1)"
    if ! echo "$API_RESULT" | grep -q " 0 failed"; then
      echo "$API" | grep "^FAIL" | head -10
      PROBLEMS="$PROBLEMS, api test failed"
    fi
    ERRORS="$(new_log_errors "$BEFORE")"
    if [ -n "$ERRORS" ]; then
      echo "$ERRORS" | head -10
      PROBLEMS="$PROBLEMS, $(echo "$ERRORS" | wc -l) error lines in the logs"
    fi
    if [ -z "$PROBLEMS" ]; then
      note "OK    $CAPTURE: $DETECTED, api test $API_RESULT"
    else
      fail "$CAPTURE: $DETECTED, api test $API_RESULT${PROBLEMS}"
    fi
  done
  if [ "$KEEP" != "1" ]; then
    sudo -n bash "$GENMON_DIR/startgenmon.sh" stop -c "$CONF_DIR" > /dev/null 2>&1
    stop_gensim
  fi
fi

echo
echo "=== summary"
printf "%s" "$SUMMARY"
exit $FAILED
