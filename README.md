# Margin — a Bible you can write in

A wide-margin study Bible for iPad and Apple Pencil. Read the **NIV**, **NLT** or **ASV**, then
underline, highlight and write notes right on the page, the way you would in a paper journaling Bible.

## What it does

- **Three translations.** Switch between NIV, NLT and ASV with one tap. Each translation keeps its own notes, because the words sit in different places on the page.
- **Wide ruled margin** beside the text, plus a ruled writing area under every chapter. Use *⋯ → Add writing space* whenever you need more room.
- **Apple Pencil ink.** Pressure-sensitive pen, translucent highlighter, and an eraser that removes whole strokes. Undo and redo work too (also ⌘Z / ⇧⌘Z with a keyboard).
- **Palm rejection.** With *Only Apple Pencil draws* turned on (the default), your fingers scroll and pinch while only the Pencil draws, so you can rest your hand on the screen. Turn it off to draw with a finger or mouse.
- **Notes stay put.** The page is always laid out at the same width and scaled to fit your screen, so your notes line up with the same words in portrait, landscape, or when you zoom.
- **Works offline.** The app and every chapter you've opened are saved on the device.
- **Backups.** *⋯ → Back up all notes* saves a file you can keep in iCloud Drive. *Restore from backup* loads it back in.

## Using it on your iPad

The app is a set of static files. Nothing needs building or installing.

1. Host the folder anywhere that serves HTTPS. The easiest option is **GitHub Pages**: in the repo, open *Settings → Pages* and deploy from this branch's root.
2. Open the site in **Safari** on the iPad.
3. Tap **Share → Add to Home Screen**. It now opens full-screen like a normal app.

To try it on a computer, run `python3 -m http.server` in this folder and open http://localhost:8000.

## How it's built

| File | Purpose |
| --- | --- |
| `index.html`, `styles.css` | Page layout: toolbar, paper page, ruled margin |
| `js/app.js` | Navigation, tools, Pencil input, undo/redo, saving, backup |
| `js/ink.js` | Drawing engine (tiled canvases, pressure strokes, highlighter, eraser) |
| `js/bible.js` | Fetches chapter text and caches it |
| `js/storage.js` | IndexedDB storage for notes and downloaded chapters |
| `js/books.js` | The 66 books and their chapter counts |
| `sw.js`, `manifest.webmanifest` | Offline support and Home Screen app |

Scripture text is fetched while the app runs from the free [bolls.life](https://bolls.life) API.
ASV falls back to [getbible.net](https://getbible.net) if needed.

## About the translations

The **ASV** (1901) is in the public domain. The **NIV** (© Biblica) and **NLT** (© Tyndale House) are
copyrighted. This app doesn't include their text. It loads chapters from bolls.life for your personal
study and caches them only on your own device. If you ever publish this app for other people, check the
publishers' licensing terms first.
