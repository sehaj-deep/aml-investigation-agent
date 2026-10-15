#!/usr/bin/env bash
# Start the demo: a fresh Postgres loaded with the reviewed demo cases, then the tool
# server, the API, the worker and nginx (the public port, 7860). Nothing persists: every
# restart begins from the same reviewed state.
set -euo pipefail

PGBIN=/usr/lib/postgresql/17/bin
export PGDATA=/tmp/pgdata
POSTGRES_PASSWORD="$(python -c 'import secrets; print(secrets.token_hex(16))')"
GUIDANCE_READER_PASSWORD="$(python -c 'import secrets; print(secrets.token_hex(16))')"
export POSTGRES_PASSWORD GUIDANCE_READER_PASSWORD

echo "$POSTGRES_PASSWORD" > /tmp/pgpass
"$PGBIN/initdb" -D "$PGDATA" -U aml --pwfile=/tmp/pgpass --auth=scram-sha-256 > /tmp/initdb.log
rm -f /tmp/pgpass
"$PGBIN/pg_ctl" -D "$PGDATA" -w -l /tmp/postgres.log \
  -o "-c listen_addresses=127.0.0.1 -c unix_socket_directories=/tmp" start
PGPASSWORD="$POSTGRES_PASSWORD" "$PGBIN/createdb" -h 127.0.0.1 -U aml aml

python space/seed.py

python -m aml_agent.tools.mcp_server --http &
python -m aml_agent.api &
python -m aml_agent.worker &

exec nginx -c /app/space/nginx.conf -g 'daemon off;'
