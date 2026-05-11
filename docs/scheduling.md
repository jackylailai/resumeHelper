# Scrape Scheduling

The JD Database page includes a scrape control panel for interactive runs:

- update source, keyword, and per-source limit
- start a scrape schedule
- stop the currently active scrape runs
- stop the active runs and immediately queue a new keyword
- optionally evaluate pending listings after scraping

The stop action is cooperative. A running scraper may finish its current HTTP
request, then the backend marks the run as cancelled before inserting results.

## Cron

Use `scripts/cron/daily_scrape.sh` for an external daily scheduler. It runs the
existing CLI scrape flow and can evaluate pending listings after scrape.

Example crontab entry:

```cron
0 3 * * * RESUMEHELPER_ROOT=/path/to/resumeHelper RESUMEHELPER_SCRAPE_KEYWORD="backend engineer" /path/to/resumeHelper/scripts/cron/daily_scrape.sh
```

Useful environment variables:

```bash
RESUMEHELPER_SCRAPE_KEYWORD="backend engineer"
RESUMEHELPER_SCRAPE_SOURCE="all"
RESUMEHELPER_SCRAPE_LIMIT="25"
RESUMEHELPER_EVALUATE_LIMIT="100"
RESUMEHELPER_PROFILE_ID=""
RESUMEHELPER_NO_TAILOR="0"
RESUMEHELPER_QUIET="0"
RESUMEHELPER_LOG_DIR="/path/to/logs"
```

`RESUMEHELPER_SCRAPE_SOURCE=all` runs the default safe sources: 104 and
Yourator. Use `all_with_linkedin` when you explicitly want LinkedIn included.

## launchd

Minimal macOS launchd shape:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>resumehelper.daily-scrape</string>
  <key>ProgramArguments</key>
  <array>
    <string>/path/to/resumeHelper/scripts/cron/daily_scrape.sh</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>RESUMEHELPER_ROOT</key>
    <string>/path/to/resumeHelper</string>
    <key>RESUMEHELPER_SCRAPE_KEYWORD</key>
    <string>backend engineer</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>3</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
</dict>
</plist>
```
