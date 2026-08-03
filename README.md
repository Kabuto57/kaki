# Kaki

**Badminton games in Singapore, actually searchable.**

The `sg_badminton` Telegram group is where games get offered, and it works fine
until you want something specific. Telegram can search for a word. It cannot
answer "Wednesdays at Choa Chu Kang after 7pm under $10", which is the question
people actually have.

Kaki reads the group, understands the posts, and makes them filterable. Joining
still happens in the Telegram thread — Kaki finds the game, it does not run it.

---

## How it works

```
   Telegram group
         │
         │  Telethon, signed in as your account
         ▼
   ┌───────────────┐     stores every message verbatim
   │ ingest worker │────────────────────┐
   └───────────────┘                    ▼
         │                     ┌──────────────────┐
         │ parses each one     │  source_messages │  immutable
         ▼                     └──────────────────┘
   ┌───────────────┐                    │
   │     games     │◀───────────────────┘  re-derivable at any time
   └───────────────┘
         │
         ▼
   ┌───────────────┐        ┌──────────────┐
   │  FastAPI      │◀───────│  React app   │
   └───────────────┘        └──────────────┘
```

**The one design decision worth knowing:** raw messages and parsed games live in
separate tables. The parser is the part most likely to be wrong and most likely
to improve, so storing only its output would mean every fix applies to new posts
while months of history stays wrong. Because the original text is kept,
`scripts/reparse.py` fixes all of history locally — no re-fetching, no rate
limits, no Telegram round trip.

---

## Before you start

You need Telegram API credentials. A **bot token will not work**: the Bot API
deliberately does not expose message history, so a bot only ever sees messages
sent after it joins. Reading what has already been posted requires signing in as
a user, which is what `scripts/login.py` does, once.

1. Go to <https://my.telegram.org> and log in
2. **API development tools** → create an app (any name)
3. Copy the **api_id** and **api_hash**
4. Make sure that Telegram account has actually joined the group

The session file this produces is a credential. It is gitignored, and on a
server it should be readable only by the service user.

---

## Run it locally

**Backend**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# fill in TELEGRAM_API_ID and TELEGRAM_API_HASH

python -m scripts.init_db
python -m scripts.seed_venues
```

Sign in to Telegram once. This is interactive — phone number, the code Telegram
texts you, 2FA if you have it — which is why it cannot be part of the worker's
startup:

```bash
python -m scripts.login
```

Find the games topic. Without this the worker reads the whole group and most of
what it stores is conversation:

```bash
python -m scripts.list_topics
# put the id into TELEGRAM_TOPIC_ID in .env
```

Start the two halves in separate terminals:

```bash
python -m scripts.run_ingest              # backfills, then watches
uvicorn app.main:app --reload --port 8000 # the API
```

API docs are at <http://localhost:8000/docs>.

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. In dev, Vite proxies `/api` to the backend, so
CORS never comes up locally.

**Tests**

```bash
cd backend && python -m pytest -q     # 56 tests
```

---

## Deploy it for free

Three pieces, all on free tiers that do not expire:

| Piece | Where | Cost |
|---|---|---|
| API + ingest worker | Google Cloud `e2-micro` (Always Free) | $0 |
| Database | SQLite on that VM | $0 |
| Frontend | Vercel | $0 |

The worker has to run continuously, which rules out most "free tier" web hosts —
they sleep idle services, and a sleeping ingester silently stops collecting
games. A free always-on VM is the honest answer.

### 1. Create the VM

In the [Google Cloud console](https://console.cloud.google.com) →
**Compute Engine → VM instances → Create instance**. These settings exactly, or
it is not free:

- **Region**: `us-west1`, `us-central1`, or `us-east1` — only these qualify
- **Machine type**: `e2-micro`
- **Boot disk**: Ubuntu 24.04 LTS, **Standard persistent disk**, 30 GB
- **Firewall**: tick *Allow HTTP traffic* and *Allow HTTPS traffic*

Google requires a billing account on file. You will not be charged as long as
you keep to the settings above. Set a budget alert anyway:
**Billing → Budgets & alerts → Create budget → $1, alert at 100%**. It costs
nothing and means a mistake shows up the same day rather than at month end.

### 2. Install

SSH in from the console, then:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git

git clone https://github.com/YOUR_USERNAME/kaki.git
cd kaki/backend

python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

cp .env.example .env
nano .env
```

Fill in `.env`. Two things matter beyond the Telegram credentials:

```bash
# Generate a real one — the app refuses to start in production without it
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

```ini
SECRET_KEY=<the value you just generated>
ENVIRONMENT=production
CORS_ORIGINS=https://your-frontend.vercel.app
DATABASE_URL=sqlite:////home/YOUR_USER/kaki/backend/data/kaki.db
```

Note the four slashes in the SQLite URL — that is an absolute path, and it
matters because systemd will not run from the directory you are standing in.

```bash
mkdir -p data
./.venv/bin/python -m scripts.init_db
./.venv/bin/python -m scripts.seed_venues
./.venv/bin/python -m scripts.login          # interactive, once
./.venv/bin/python -m scripts.list_topics    # then set TELEGRAM_TOPIC_ID
```

### 3. Run both services under systemd

```bash
sudo tee /etc/systemd/system/kaki-api.service > /dev/null <<EOF
[Unit]
Description=Kaki API
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$HOME/kaki/backend
ExecStart=$HOME/kaki/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/kaki-ingest.service > /dev/null <<EOF
[Unit]
Description=Kaki Telegram ingest worker
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$HOME/kaki/backend
ExecStart=$HOME/kaki/backend/.venv/bin/python -m scripts.run_ingest
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now kaki-api kaki-ingest
```

Check both, and watch the first backfill:

```bash
systemctl status kaki-api kaki-ingest
journalctl -u kaki-ingest -f
```

The first run backfills history and takes a few minutes. It is safe to
interrupt — ingestion is idempotent, so restarting picks up where it left off
rather than duplicating anything.

### 4. HTTPS

The API listens on localhost only. Caddy puts it on the internet with a
certificate, and renews it without being asked:

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy

sudo tee /etc/caddy/Caddyfile > /dev/null <<'EOF'
api.yourdomain.com {
    reverse_proxy 127.0.0.1:8000
}
EOF

sudo systemctl reload caddy
```

Point an `A` record at the VM's external IP first. If you do not have a domain
yet, a free option like DuckDNS works and Caddy will still issue a certificate.

### 5. Frontend on Vercel

```bash
cd frontend
npx vercel --prod
```

Set `VITE_API_URL` to `https://api.yourdomain.com` in the Vercel project's
environment variables, then redeploy.

Finally, put the Vercel URL into `CORS_ORIGINS` in the backend `.env` and
restart it — the browser will refuse the requests otherwise:

```bash
sudo systemctl restart kaki-api
```

---

## Operating it

**Is it still collecting?** This is the failure that hides: the worker dies, the
feed slowly empties, and nothing errors because the API is perfectly healthy.

```bash
curl https://api.yourdomain.com/ingest/status
```

`last_run_at` going stale is the signal to look at
`journalctl -u kaki-ingest -n 100`.

**After improving the parser**, fix history too:

```bash
cd ~/kaki/backend
./.venv/bin/python -m scripts.reparse
sudo systemctl restart kaki-ingest
```

**Adding a venue.** Posts naming a venue Kaki does not know still appear, with
the raw text shown instead of a clean name — so gaps are visible rather than
silent. To fix one, add it to `app/ingest/venue_catalogue.py`:

```python
("my_venue", "My Sports Hall", "West", ["my sports hall", "msh"], (1.3521, 103.8198)),
```

Aliases matter more than the official name — people type "CCK", not "Choa Chu
Kang Sports Hall". Get coordinates by right-clicking the spot in Google Maps.
Then:

```bash
./.venv/bin/python -m scripts.seed_venues
./.venv/bin/python -m scripts.reparse
```

**Backups.** SQLite is one file:

```bash
sqlite3 ~/kaki/backend/data/kaki.db ".backup '/tmp/kaki-backup.db'"
```

Worth a weekly cron job. The messages are the irreplaceable part — games can
always be re-derived.

---

## When SQLite is not enough

SQLite is genuinely fine here: one writer, a few readers, a database that will
sit in the low hundreds of megabytes for years. Move to Postgres when you have
a specific reason — more than one machine writing, or you want managed backups
and point-in-time recovery.

The code already supports both. Create a free Postgres on
[Supabase](https://supabase.com) or [Neon](https://neon.tech), then:

```ini
DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname
```

```bash
./.venv/bin/python -m scripts.init_db
./.venv/bin/python -m scripts.seed_venues
sudo systemctl restart kaki-api kaki-ingest
```

The `UTCDateTime` column type in `app/core/types.py` exists partly for this
transition: it guarantees timestamps behave identically on both backends, so
moving does not silently shift every game by eight hours.

---

## What's in here

```
backend/
  app/
    main.py              FastAPI assembly, error handling, CORS
    config.py            settings from environment
    db.py                engine and session
    models.py            schema — read the docstring first
    schemas.py           request/response shapes
    core/
      security.py        password hashing, JWT
      errors.py          domain errors, mapped to status codes in one place
      types.py           UTCDateTime — read this before touching timestamps
    ingest/
      parser.py          free text → structured game
      venue_catalogue.py the venue list and its aliases
      service.py         message storage and game derivation
      telegram.py        Telethon client, backfill and live watch
    services/
      discovery.py       filtering and ranking
    api/routes/          auth, games, venues, me, ops
  scripts/               init_db, seed_venues, login, list_topics,
                         run_ingest, reparse
  tests/                 56 tests

frontend/
  src/
    App.jsx              the feed — filters live in the URL
    components/          GameCard, Filters
    lib/api.js           one place that talks to the API
    lib/format.js        UTC → Singapore time, in one place
    styles.css           design tokens
```

---

## Honest limitations

**The parser will be wrong sometimes.** The input is whatever someone typed on a
phone. It grades its own confidence and shows the original text when unsure,
rather than presenting a guess as fact — but it will still miss things. The
*Test the reader* path (`scripts/reparse.py` plus the tests) is how you improve
it against real posts.

**It depends on a group you do not control.** An admin changing settings, or
your account losing access, stops the supply. `Game.source` already has a
`native` value for the day games are posted directly to Kaki; that is the exit
from this dependency, and it costs one unused column today rather than a
migration on a live table later.

**Joining still happens in Telegram.** Deliberately. Building an RSVP the host
never sees would split the source of truth and eventually get someone stood up
at a court.
