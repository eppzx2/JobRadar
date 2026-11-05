# JobRadar

JobRadar is a personal, on-demand vacancy dashboard for Azerbaijani career pages and job boards. Click **Fetch Jobs** to check enabled sources. You can reopen the app, adjust filters, or edit keywords offline after a fetch.

## Windows quick start

On Windows 10 or 11, open **PowerShell**. Click **Copy** in the upper-right corner of the code block below, paste it into PowerShell, and press **Enter**. The script uses your Windows user folder automatically. Connect to the internet for the first installation and approve the installer if Windows prompts you.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $repo = Join-Path $env:USERPROFILE 'JobRadar'

    function Install-PackageWithWinGet($id) {
        if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
            throw 'Install or update App Installer in Microsoft Store, then paste this block again.'
        }
        winget install --id $id --exact --source winget --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw "Installation failed: $id (exit $LASTEXITCODE)" }
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                    [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + $env:Path
    }

    if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) {
        Install-PackageWithWinGet 'Git.Git'
    }

    function Find-Python {
        foreach ($name in 'py.exe', 'python.exe', 'python3.exe') {
            $cmd = Get-Command $name -ErrorAction SilentlyContinue
            if (-not $cmd) { continue }
            if ($name -ne 'py.exe' -and $cmd.Source -like '*\Microsoft\WindowsApps\*') { continue }
            $options = @()
            if ($name -eq 'py.exe') { $options = @('-3') }
            $path = & $cmd.Source @options -c 'import sys; print(sys.executable) if sys.version_info >= (3, 11) else sys.exit(1)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $path) { return $path }
        }
        $standard = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
        if (Test-Path -LiteralPath $standard) { return $standard }
    }

    $python = Find-Python
    if (-not $python) {
        Install-PackageWithWinGet 'Python.Python.3.12'
        $python = Find-Python
        if (-not $python) { throw 'Python could not be found. Reopen PowerShell and paste this block again.' }
    }

    if (-not (Test-Path -LiteralPath $repo)) {
        git clone https://github.com/eppzx2/JobRadar.git "$repo"
        if ($LASTEXITCODE -ne 0) { throw 'Git clone failed.' }
    } else {
        if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) { throw "Existing folder is not a Git checkout: $repo" }
        $origin = git -C "$repo" remote get-url origin
        if ($origin -notin @('https://github.com/eppzx2/JobRadar.git', 'https://github.com/eppzx2/JobRadar', 'git@github.com:eppzx2/JobRadar.git')) {
            throw "Existing folder belongs to another repository: $repo"
        }
        git -C "$repo" pull --ff-only
        if ($LASTEXITCODE -ne 0) { throw 'Git pull failed. Check the message above.' }
    }

    Set-Location -LiteralPath $repo
    & $python app.py
}
```

If the dashboard does not open automatically, go to **http://localhost:8501**. Click **Fetch Jobs** to check for vacancies. To stop JobRadar, press **Ctrl+C** in PowerShell. To update and launch JobRadar later, paste the same block again.

## Run locally

Install Python 3.11 or later, open a terminal in the JobRadar project folder, and run one command.

**Linux / macOS**

```bash
python3 app.py
```

**Windows (PowerShell or Command Prompt)**

```powershell
py app.py
```

If your Windows installation provides the `python` command, `python app.py` works too. On any platform, `python3 app.py` works when `python3` points to a supported interpreter.

On first launch, JobRadar creates a private `.venv`, installs the packages in `requirements.txt`, and starts Streamlit. The first installation requires internet access. Subsequent launches use the same command and reuse installed packages. If the requirements change after a pull, the launcher installs missing or incompatible dependencies. On Debian/Ubuntu, install the matching `python3-venv` package if your Python installation lacks venv support.

Open **http://localhost:8501** (or the URL printed in the terminal). Press **Ctrl+C** to stop the app. The database is created on first launch. Click **Fetch Jobs** when you want to check the twelve configured sources.

Local execution is the simplest zero-cost deployment. For a private server, keep the application and its SQLite file on persistent disk. Binding to localhost suits a single-user workspace. For remote access, use an SSH tunnel or an authenticated private gateway. All users of one installation share configuration and history.

## First fetch

1. Open **Sources Management** to review, edit, disable, remove, or add a career page. Check each publisher's terms and disable a source if its terms prohibit collection.
2. Open **Keyword Management** to edit bilingual IT and cybersecurity role phrases or choose title-and-description matching. A match requires both a role phrase and a junior, trainee or internship marker in the title or employment type. Examples include *Junior Helpdesk Technician*, *İT üzrə təcrübəçi*, and *Texniki dəstək üzrə kiçik mütəxəssis*. Matching ignores case, accents and punctuation. Senior and data analytics titles are excluded even if the description mentions IT support. The standalone keyword IT only matches titles.
3. Click **Fetch Jobs**. Leave the app open while it works. Large boards can take several minutes. Description mode can take longer on its first run because some feeds require individual detail pages. Description lookups are limited to junior/intern candidates.
4. Expand **Latest source results** to see successful, partial, and failed checks. Use the company, keyword, location, employment type, and new-only filters to narrow the results.

**Dashboard metrics** summarize the last fetch. Sources checked counts attempts. Vacancies discovered counts unique vacancies read during that fetch. Matching vacancies uses the keyword settings in effect at fetch time. New vacancies counts first discoveries and New matches counts the subset that matched.

**Job views** show saved history using the current keywords and scope. New means first discovered in the latest fetch and persists across reloads. Earlier vacancies appear in Previously Discovered Jobs. Descriptions and requirements are shown in the vacancy card when the publisher supplies them. Click **Load from career page** for an uncached posting. Up to 100 snippets of 32,000 characters each are held in session memory. Older records carry an availability note when absent from the latest run. Removing or disabling a source preserves its history. An empty result can mean your keywords did not match even though the fetch found vacancies.

## Included sources

| Career page | Collection method |
| --- | --- |
| Bir | Public vacancy API used by the Bir career frontend, with offset pagination |
| Rabitəbank | Glorri employer feed, using the tenant ID embedded in the bank's branch data |
| Unibank | Vacancy cards paired with their Glorri application URLs |
| ABB | Paginated vacancy API advertised by the filter form |
| VTB Azerbaijan | Embedded Glorri employer feed |
| PASHA Insurance | Published Teamtailor jobs RSS with descriptions and locations |
| PASHA Life | Embedded Glorri employer feed |
| PASHA Bank | Glorri integration for the bank's public career tenant |
| JobSearch.az | Public vacancy API with publisher-provided pagination |
| [CyberJob.az](https://cyberjob.az/vacancies) | Paginated IT vacancy listings with job descriptions and requirements on the detail pages |
| HelloJob.az | Paginated vacancy cards and structured posting details |
| Glorri | Public portal API with offset pagination and the employer name for each posting |

The application follows publisher feeds exposed by these pages without running a browser. Where a supported source supplies a closing date, the parser excludes expired postings. Fields that the publisher omits are shown as unspecified. Detail enrichment for Glorri runs in description mode and also resolves short application links when needed for identity. The app only reads public pages. It does not submit applications.

## Add another board

Add the company name and exact career URL in **Sources Management**. Changes take effect on your next fetch. The seed list in `config/sources.json` is imported once into a new database. Editing it later does not overwrite your dashboard settings.

The generic parser recognizes JobPosting JSON-LD, including arrays and nested graphs, job-specific links on listing pages, and advertised jobs RSS feeds. For a conventional HTML board, you can add a rule in `config/selectors.json` without editing Python. Use the exact configured URL as the key. Replace the placeholder and selectors below with the actual page structure:

```json
{
  "<exact configured career URL>": {
    "card": "article.opening",
    "title": "h2",
    "link": "a.apply",
    "location": ".location",
    "employment": ".contract",
    "published": "time",
    "description": ".summary",
    "next": "a[rel=next]",
    "empty": ".no-openings"
  }
}
```

Only card, title, and link are required. The optional empty selector identifies an explicit zero-vacancy state. JS-only boards with a new API shape may need a dedicated adapter. Add one in `parsers/` and dispatch it in `scraper/engine.py`. Unrecognized markup produces a visible source error.

## Duplicate detection and reliability

- SQLite retains compact vacancy metadata, matching role labels and unique identity aliases for up to 30 days and 10,000 vacancies. Old descriptions are purged on upgrade. Full descriptions are never written to the database. Only the latest 30 source-check reports are retained. Cleanup runs after each completed fetch; a vacancy returning after eviction may be marked new. URL normalization removes tracking parameters, normalizes host/port, and preserves meaningful query IDs and hash routes.
- Glorri links can share a provider ID, a canonical portal slug, or an employer-scoped combination of title, location, and precise publication timestamp. The app resolves short Unibank links to canonical Glorri detail URLs. Structured postings without individual URLs can use an employer requisition ID.
- Different requisitions can share the same title. Records without a shared reliable identity stay separate. If an authoritative alias later connects records, the older first-discovery status survives.
- One fetch at a time per database. Network collection finishes before the SQLite write transaction, and a failed source cannot erase previously saved results. Timeouts, HTTP errors, pagination loops, and unsupported structures appear in source results. A partial source contributes only the vacancies already read.
- Each run checks robots.txt by origin, obeys applicable delays, and spaces requests. A missing robots file (404/410) is accepted. Inaccessible policies, protected pages, and rate limits stop collection for the affected resource. No scheduled fetches, automatic retries, or background workers.
- Unknown sites may publish incomplete metadata or change their markup. Saved jobs are discovery history, not a guarantee that an application remains open.

## Optional Telegram notifications

Copy `.env.example` to `.env` in the project directory. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` privately, start the bot chat (or add the bot to the destination chat), then restart JobRadar and enable **Telegram notifications → Send new matches** in the sidebar. Environment variables set by the host work too. Never commit your populated .env file.

Only first-seen matches from the active fetch are eligible. The database commits before notification delivery. An old vacancy that matches newly edited keywords stays previously discovered. Delivery stops on a Telegram error and reports the count sent; failed or interrupted messages are not replayed automatically. This avoids duplicate messages after ambiguous delivery failures. Credentials stay on the server.

## Project layout and maintenance

| Path | Responsibility |
| --- | --- |
| `app.py`, `frontend/` | Streamlit dashboard, filters, source and keyword management |
| `scraper/` | On-demand workflow, policy-aware HTTP, adapter routing |
| `parsers/` | Career APIs, RSS, structured HTML and optional CSS rules |
| `matching/` | Job model, identity normalization, deadline checks and keyword matching |
| `database/` | SQLite schema, initialization, preferences, identity merge |
| `notifications/` | Optional Telegram delivery |
| `config/` | Real seed URLs and optional HTML parser rules |
| `tests/fixtures/` | Synthetic vacancies, isolated from the production sources |

After the first launch, run the offline tests from the project root:

```bash
.venv/bin/python -m unittest discover -v
```

On Windows, use `.venv\Scripts\python.exe -m unittest discover -v`.

Tests use temporary databases and simulated sources. They cover duplicate identities across pages and sessions, separate requisitions with identical titles, source failure isolation, notification eligibility, case-insensitive matching, parser behavior, and the dashboard's manual-only fetch trigger. Sample postings never enter the live database.

Back up `data/jobradar.sqlite3` with the app stopped. To change its location, set `JOBRADAR_DB` in the environment or .env. The app requires local DNS for public-address validation by default. In a managed network where a trusted egress proxy enforces public-only destinations and handles DNS, the operator can set `JOBRADAR_TRUST_EGRESS_PROXY=1` alongside the proxy settings. Leave this unset for ordinary local use.
