# Remote connection (connect to an already-running KB)

Use this when **Phase 0** chose **Remote connect** — the Postgres `db` service and
the `kb-mcp` daemon already run on another host, and this machine is a client. Do
**not** run `docker compose up` and do **not** run migrations: the remote stack is
canonical and already migrated.

## What you need from the user

1. **kb-mcp daemon URL** — e.g. `http://<host>:8765/mcp`, or `http://127.0.0.1:8765/mcp`
   if reached through a local tunnel.
2. **`DATABASE_URL`** — the remote Postgres URL for host-side reads (kb-lint, psql/psycopg).
   May point at `localhost:<port>` when reached through a tunnel.
3. **Reachability** — is the remote reachable directly, or only over **SSH** (so this
   machine must tunnel)? If SSH, get the SSH host alias (or HostName/User/Port).

If the daemon and DB are reachable directly (VPN, LAN, public bind), skip the tunnel
section and go straight to *Verify*.

## SSH tunnel (when the remote is only reachable over SSH)

Two ports must be forwarded: the kb-mcp daemon (default `8765`) and Postgres
(whatever `DATABASE_URL` points at, e.g. `15432`). Confirm the SSH host resolves and
the remote services are up first:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=8 <ssh-host> \
  'curl -s -o /dev/null -w "mcp:%{http_code}\n" --max-time 4 http://127.0.0.1:8765/mcp'
```

### One-shot tunnel (for the current session only)

```bash
ssh -f -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -L 127.0.0.1:8765:127.0.0.1:8765 \
  -L 127.0.0.1:15432:127.0.0.1:15432 \
  <ssh-host>
```

### Persistent auto-tunnel (recommended — survives reboot / network drops)

On macOS, install a launchd LaunchAgent so the tunnel auto-starts at login and
auto-reconnects when it drops (`KeepAlive`). Kill any one-shot tunnel first so the
ports are free, then bootstrap the agent. Template:

`~/Library/LaunchAgents/com.local.kb-tunnel.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.local.kb-tunnel</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/ssh</string>
    <string>-N</string>
    <string>-o</string><string>ExitOnForwardFailure=yes</string>
    <string>-o</string><string>ServerAliveInterval=60</string>
    <string>-o</string><string>ServerAliveCountMax=3</string>
    <string>-o</string><string>StrictHostKeyChecking=no</string>
    <string>-L</string><string>127.0.0.1:8765:127.0.0.1:8765</string>
    <string>-L</string><string>127.0.0.1:15432:127.0.0.1:15432</string>
    <string>-p</string><string><SSH_PORT></string>
    <string><USER>@<HOSTNAME></string>
  </array>
  <key>KeepAlive</key><true/>      <!-- auto-restart on drop -->
  <key>RunAtLoad</key><true/>      <!-- start at login -->
  <key>StandardOutPath</key><string>/tmp/kb-tunnel.log</string>
  <key>StandardErrorPath</key><string>/tmp/kb-tunnel.err</string>
  <key>ThrottleInterval</key><integer>10</integer>
</dict>
</plist>
```

Load it:

```bash
pkill -f "ssh -f -N.*8765:127.0.0.1:8765" 2>/dev/null   # free the ports if a one-shot is running
UID_NUM=$(id -u)
launchctl bootout   gui/$UID_NUM ~/Library/LaunchAgents/com.local.kb-tunnel.plist 2>/dev/null
launchctl bootstrap gui/$UID_NUM ~/Library/LaunchAgents/com.local.kb-tunnel.plist
launchctl print gui/$UID_NUM/com.local.kb-tunnel | grep -E 'state|pid'
```

Tunnel requires working SSH key auth to the host. If the host/port changes later,
edit the plist and re-run the `bootout`/`bootstrap` pair.

> Linux equivalent: a `systemd --user` unit running the same `ssh -N -L …` with
> `Restart=always`, or `autossh`. The contract is "two forwarded ports + auto-reconnect".

## Verify

```bash
set -a; . ./.env; set +a
curl -s -o /dev/null -w '8765/mcp -> %{http_code} (expect 406)\n' --max-time 5 http://127.0.0.1:8765/mcp
```

DB read — prefer `psql`, fall back to psycopg (the same path `kb.service` uses) when
the host has no `psql` client:

```bash
PSQL_URL="${DATABASE_URL/+psycopg/}"
psql "$PSQL_URL" -tAc "select count(*) from pages;" 2>/dev/null \
 || uv run python -c "import os,psycopg; c=psycopg.connect(os.environ['DATABASE_URL'].replace('+psycopg',''),connect_timeout=8); cur=c.cursor(); cur.execute('select count(*) from pages'); print('pages:',cur.fetchone()[0])"
```

A populated remote (non-zero `pages`, an `alembic_version` row) confirms you are a
client of a live KB — no schema/data init is needed on this machine.
