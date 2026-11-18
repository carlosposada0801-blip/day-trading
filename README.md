# Streaks

Count the days since you quit something: porn, social media, alcohol, nicotine, anything.
Earn medals as you go, with a black theme.

**Medals:** 1 day · 3 days · 1 week · 2 weeks · 1 month · 2 months · 3 months · 6 months ·
1 year · 2 years · 3 years · 5 years · 10 years.

## What it does

- **Live counter** for each streak (days, hours, minutes, seconds), with a ring showing
  progress to the next medal.
- **Celebrations:** confetti and the medal the moment you reach a milestone. Each one fires
  only once.
- **Your own rewards:** promise yourself something for a milestone (e.g. "new shoes" at 30
  days). It shows on the medal and in the celebration.
- **"I'm struggling" button:** a 90-second breathing guide, your reason for quitting, and an
  optional Bible verse. Tap "I made it through" to count the urge you beat.
- **Slips are handled kindly:** resetting keeps your best streak, every medal you've ever
  earned, and a history of past streaks with an optional note on what happened.
- **Several streaks at once**, each with its own icon, start date (you can enter one that
  began earlier) and "why".
- **Scripture encouragement** (KJV), on by default. Turn it off in Settings.

## Private by design

- **Nothing leaves your phone.** Everything is stored only on your device, in the browser's
  local storage. There's no account and no server.
- **PIN lock:** optional, asked when the app opens or after a minute away.
- **Backups:** save one from Settings now and then, and restore it on a new phone. Clearing
  your browser data erases your streaks.

## Use it on your phone

Once it's published (below), open the address in Safari (iPhone) or Chrome (Android), then:
- **iPhone:** Share → Add to Home Screen
- **Android:** ⋮ → Add to Home screen / Install app

It opens full-screen like an app and works offline.

On iPhone, add it to your home screen **first** and set up your streaks from there. The
home-screen version keeps its own storage, separate from Safari's.

## Publish it (free, GitHub Pages)

1. In this repo on GitHub: **Settings → Pages → Build and deployment → Source: GitHub
   Actions**.
2. Push to the repo (or run the "Publish to GitHub Pages" workflow from the Actions tab).
3. The address appears under Settings → Pages, like
   `https://<your-username>.github.io/day-trading/`.

The page's code is public on a public repo, but your streaks never are: they live only on
your phone.

## Run it locally

```bash
npm start   # http://localhost:8000
npm test    # streak logic tests
```

No build step. `site/` is plain HTML, CSS and JavaScript. The streak math lives in
`site/streak.js`, with tests in `tests/`.
