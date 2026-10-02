#!/bin/zsh
# Start (or stop) the project's own PostgreSQL (port 5435) and MongoDB (port 27018) under data/, so nothing system-wide is touched.
#   ./run.sh start | stop
set -e
BIN=$HOME/micromamba/envs/analyst/bin
cd "$(dirname "$0")"
case "$1" in
  start)
    if [ ! -d data/pgdata ]; then $BIN/initdb -D data/pgdata -U postgres -A trust >/dev/null; fi
    $BIN/pg_ctl -D data/pgdata -o "-p 5435 -c shared_buffers=1GB -c work_mem=256MB -c max_wal_size=4GB" -l data/pg.log start >/dev/null
    mkdir -p data/mongodata
    nohup $BIN/mongod --dbpath data/mongodata --port 27018 --bind_ip 127.0.0.1 --logpath data/mongo.log >/dev/null 2>&1 &   # --fork is not supported on macOS
    until nc -z 127.0.0.1 27018 2>/dev/null; do sleep 0.5; done
    echo "postgres :5435, mongodb :27018";;
  stop)
    $BIN/pg_ctl -D data/pgdata stop >/dev/null || true
    [ -s data/mongodata/mongod.lock ] && kill "$(cat data/mongodata/mongod.lock)" 2>/dev/null || true   # --shutdown is Linux-only
    echo stopped;;
esac
