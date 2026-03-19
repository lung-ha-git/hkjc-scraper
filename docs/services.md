# System Services

## Overview

All services use macOS `launchd` via `launchctl`. Plist files are stored in `~/Library/LaunchAgents/`.

## Services

| Service | Label | Port | Purpose | Auto-Start |
|--------|-------|------|---------|------------|
| Pipeline | `com.fatlung.hkjc-pipeline` | - | Daily data sync + ML training | ✅ Daily 7AM |
| API | `com.fatlung.hkjc-api` | 3001 | Backend REST API | ✅ On boot |
| Webapp | `com.fatlung.hkjc-webapp` | 3000 | Frontend UI | ✅ On boot |

## Service Files

### Pipeline (`com.fatlung.hkjc-pipeline.plist`)
```xml
<key>Label</key>
<string>com.fatlung.hkjc-pipeline</string>

<key>ProgramArguments</key>
<array>
    <string>/usr/bin/python3</string>
    <string>/path/to/daily_pipeline.py</string>
</array>

<key>StartCalendarInterval</key>
<array>
    <dict>
        <key>Hour</key><integer>7</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
</array>

<key>RunAtLoad</key>
<false/>

<key>KeepAlive</key>
<false/>
```

### API (`com.fatlung.hkjc-api.plist`)
```xml
<key>Label</key>
<string>com.fatlung.hkjc-api</string>

<key>ProgramArguments</key>
<array>
    <string>/opt/homebrew/bin/node</string>
    <string>/path/to/server/index.cjs</string>
</array>

<key>WorkingDirectory</key>
<string>/path/to/web-app</string>

<key>RunAtLoad</key>
<true/>

<key>KeepAlive</key>
<true/>
```

### Webapp (`com.fatlung.hkjc-webapp.plist`)
```xml
<key>Label</key>
<string>com.fatlung.hkjc-webapp</string>

<key>ProgramArguments</key>
<array>
    <string>/bin/bash</string>
    <string>-c</string>
    <string>cd /path/to/web-app && /opt/homebrew/bin/node ./node_modules/.bin/vite</string>
</array>

<key>RunAtLoad</key>
<true/>

<key>KeepAlive</key>
<true/>
```

## Commands

```bash
# List all HKJC services
launchctl list | grep com.fatlung

# Check service status
launchctl print gui/$(id -u)/com.fatlung.hkjc-api
launchctl print gui/$(id -u)/com.fatlung.hkjc-webapp
launchctl print gui/$(id -u)/com.fatlung.hkjc-pipeline

# Stop/Start services
launchctl stop com.fatlung.hkjc-api
launchctl start com.fatlung.hkjc-api
launchctl stop com.fatlung.hkjc-webapp
launchctl start com.fatlung.hkjc-webapp

# Restart pipeline immediately
launchctl kickstart -kp gui/$(id -u)/com.fatlung.hkjc-pipeline

# Unload/Load services
launchctl unload ~/Library/LaunchAgents/com.fatlung.hkjc-api.plist
launchctl load ~/Library/LaunchAgents/com.fatlung.hkjc-api.plist

# View logs
tail -f ~/path/to/web-app/logs/api-stderr.log
tail -f ~/path/to/web-app/logs/webapp-stderr.log
tail -f ~/path/to/pipeline/logs/launchd-stderr.log
```

## Notes

- `KeepAlive: true` means service will auto-restart if it crashes
- `RunAtLoad: true` means service starts on system boot
- Pipeline uses `StartCalendarInterval` for daily scheduling, not KeepAlive
- All services run under user GUI context (not system)

## Locations

- Service plists: `~/Library/LaunchAgents/`
- Logs: Each project has its own logs directory
- Working directories must be correct for relative paths to work

## Common Issues

### Node/npm not found
If service fails with "env: node: No such file or directory":
- Use full path: `/opt/homebrew/bin/node` not just `node`
- Set PATH in EnvironmentVariables if using bash -c

### Service spawn scheduled but not running
Run `launchctl kickstart -kp gui/<uid>/<service-label>` to force start

### MongoDB connection refused
- Ensure MongoDB is running: `brew services start mongodb-community`
- Check connection in `.env` file
