#!/bin/bash
# -------------------------------------------------------------------------------
#    FILE: run_pi_tests.sh
# PURPOSE: Tests genmon on a Raspberry Pi from this computer, over ssh:
#            - updates a test copy of genmon on the Pi (git pull)
#            - runs the unit tests and the simulator tests there, with the
#              Pi's Python and genmon's own Python environment
#            - runs genmon live: gensim on the Pi with the repository captures
#              (tests/sim/captures), the test genmon reading it over serial
#              over TCP, tests/test_genmon_api.py against genmon and the web
#              interface, and a check of the logs
#          The steps on the Pi are in tests/pi_test_remote.sh (sent over ssh,
#          see it for the details and settings).
#
#          It only uses the test copy in the Pi user's home folder (~/genmon,
#          its config in ~/genmonconfig, logs in ~/genmonlogs) with its own
#          ports, so a genmon installed on the Pi keeps running. That genmon
#          should have multi_instance = True in its genmon.conf: otherwise it
#          stops the test copy when it starts.
#
#  SET UP: once:
#            - an ssh login to the Pi without a password (ssh-keygen,
#              ssh-copy-id), with a name in ~/.ssh/config (default genmon-pi)
#            - the Pi user may use sudo without a password (genmon runs as
#              root)
#            - genmon installed in that user's home folder:
#                git clone https://github.com/jgyates/genmon.git
#                cd genmon && ./genmonmaint.sh -i -c ~/genmonconfig
#              (answer n to starting genmon on boot: the tests start and
#              stop it)
#
#   USAGE: tests/run_pi_tests.sh [options]
#            -H <name>     the ssh name of the Pi (default genmon-pi, or
#                          $GENMON_PI)
#            -c <names>    captures for the live test, comma separated
#                          (default evo_ac), or "all"
#            -s <steps>    steps: any of "update unit live" (default all)
#            -k            leave the test genmon and gensim running
#            -h            help
#
# EXAMPLES: tests/run_pi_tests.sh
#           tests/run_pi_tests.sh -c all
#           tests/run_pi_tests.sh -s live -c h100,powerzone -k
#
#          Exit code 0 if every step passed.
# -------------------------------------------------------------------------------

HOST="${GENMON_PI:-genmon-pi}"
CAPTURES="evo_ac"
STEPS="update unit live"
KEEP=0

while getopts "H:c:s:kh" opt; do
  case $opt in
    H) HOST="$OPTARG" ;;
    c) CAPTURES="$OPTARG" ;;
    s) STEPS="$OPTARG" ;;
    k) KEEP=1 ;;
    *) sed -n '2,46p' "$0"; exit 2 ;;
  esac
done

REMOTE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/pi_test_remote.sh"

if ! ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST" true; then
  echo "Can not log in to $HOST without a password (see SET UP in $0)"
  exit 2
fi

# the settings go to the remote script as environment values
printf -v ENV "STEPS=%q CAPTURES=%q KEEP=%q" "$STEPS" "$CAPTURES" "$KEEP"
for name in GENMON_DIR CONF_DIR LOG_DIR SIM_DIR GENMON_PORT WEB_PORT HTTPS_PORT SIM_PORT; do
  if [ -n "${!name}" ]; then
    printf -v ENV "%s %s=%q" "$ENV" "$name" "${!name}"
  fi
done

ssh -o BatchMode=yes "$HOST" "$ENV bash -s" < "$REMOTE"
