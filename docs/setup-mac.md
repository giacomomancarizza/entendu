# Setup on a Mac (about 15 minutes, once)

## 1. Install

```bash
brew install ffmpeg python
git clone https://github.com/giacomomancarizza/entendu ~/entendu && cd ~/entendu
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[whisper]"
cp .env.example .env
```

## 2. Claude API key

Create a key at console.anthropic.com and put it in `.env` as `ANTHROPIC_API_KEY`.

## 3. Spotify

Spotify only gives an app access to your account if the app is registered. This is a private
registration, nothing is published.

1. Go to developer.spotify.com/dashboard and click **Create app**.
2. Name: `Entendu`. Redirect URI: `http://127.0.0.1:8888/callback`. Tick **Web API**.
3. In the app settings copy **Client ID** and **Client Secret** into `.env`.
4. If you get a 403 error later, add your Spotify email under **User Management**.

Note: since February 2026 Spotify requires the owner of a Development Mode app to have Premium.

Then authorize once and check what Spotify sees, without downloading anything:

```bash
entendu lesson --dry-run
```

A browser window asks you to accept; after that the token is cached in `data/`.

## 4. The button (Shortcuts)

1. Open **Shortcuts** (Comandi Rapidi) and create a new shortcut called **Lezione di francese**.
2. Add the action **Run Shell Script** with:
   ```bash
   export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"   # Shortcuts starts with a minimal PATH
   cd ~/entendu && .venv/bin/entendu lesson
   ```
3. In the shortcut details tick **Pin in Menu Bar** and, if you want, add a keyboard shortcut.

Press it when you get to work: a notification tells you when the lesson is ready and it opens.
If Spotify cannot tell which episode you heard, a small window asks you to pick it.
