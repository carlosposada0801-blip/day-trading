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
- **Daily check-in:** commit to the day each morning and rate it each evening, with a
  running check-in streak.
- **Verse of the day** on the home screen (when scripture is on).
- **Patterns:** shows when you tend to slip or get urges (time of day, day of the week) and
  which words keep coming up in your reset notes, plus your average streak to beat.
- **Urge plan:** write your steps ahead of time ("phone in another room", "go for a walk");
  they show as a checklist on the "I'm struggling" screen.
- **Accountability partner:** save a friend's number to get "Text" and "Call" buttons on the
  struggling screen and a "Tell them" button when you earn a medal.
- **Share:** makes an image of your streak or medal. Shares are worded privately by default
  ("14 days on my streak"); turn that off in Settings to name the habit.
- **Time and money back:** enter how much time or money it used to take each day to see
  what you've gotten back.
- **Reminders through your calendar:** Settings makes calendar events for your morning and
  evening check-ins and for upcoming medal days. Your phone's calendar sends the alerts,
  and titles are discreet.
- **Blocker guide:** step-by-step setup of the phone's own content filters and app limits
  (Screen Time on iPhone; Private DNS and Digital Wellbeing on Android).
- **Explained as you go:**
  - A short welcome walkthrough the first time you open it.
  - Tap any medal to see what that milestone means.
  - Each stat says what it counts.
  - Settings has a "How Streaks works" guide and answers to common questions.

## Private by design

- **Nothing leaves your phone.** Everything is stored only on your device, in the browser's
  local storage. There's no account and no server.
- **PIN lock:** optional, asked when the app opens or after a minute away.
- **Backups:** save one from Settings now and then, and restore it on a new phone. Clearing
  your browser data erases your streaks.

## What it can't do (yet)

It's a website you add to your home screen, so it can't send push notifications on its own
or show a home-screen widget. The calendar reminders cover the first. A widget needs an App
Store / Play Store version of the app.

## Use it on your phone

Once it's published (below), open the address in Safari (iPhone) or Chrome (Android), then:
- **iPhone:** Share → Add to Home Screen
- **Android:** ⋮ → Add to Home screen / Install app

It opens full-screen like an app and works offline.

On iPhone, add it to your home screen **first** and set up your streaks from there. The
home-screen version keeps its own storage, separate from Safari's.

## Or use it on your Claude account (no GitHub setup)

`site/claude.html` (built with `npm run build:claude`) runs the same app as a private page on
your Claude account. Only you can open it, and your streaks are saved privately to your
account, so they're the same on your phone and your computer. Differences from the website
version:
- Calendar reminders use Google Calendar links.
- Backups and share images go through Claude's save prompt.
- It opens inside Claude rather than as a home-screen app.

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
