# Just want to run the app? Download it here.

The ready-to-run Windows app — Zaggregate v1.0.2 — is a free download
on the **[latest release](https://github.com/alex-zagorianos/Zaggregate/releases/latest)**
page. No Python, no build tools, no source code needed.

## Get the app (about 2 minutes)

1. Open the [latest release](https://github.com/alex-zagorianos/Zaggregate/releases/latest)
   and, under **Assets**, download **`Zaggregate-v1.0.2.zip`**.
2. Extract it anywhere (right-click → *Extract All…*).
3. Open the extracted `Zaggregate/JobProgram` folder and **double-click
   `Zaggregate-Desktop.bat`** — the app opens in its own window.
   (`Zaggregate-Web.bat` opens the same app in your browser instead; plain
   `JobProgram.exe` also opens the desktop app.)

Want to check the download? `SHA256SUMS.txt` on the same release page carries
the zip's checksum (`certutil -hashfile <zip> SHA256` on Windows).

## First launch

Windows may show an "unknown publisher" warning once (the app is safe — it
just isn't code-signed yet). Click **More info → Run anyway**, or see
`JobProgram/FIRST-RUN.txt` inside the download for the two safe ways past it.

That's it — a short setup wizard opens, or use **Set up with AI** to configure
everything with one paste. Everything stays on your computer: no account, no
cloud, no telemetry.

## Why isn't the app in this folder anymore?

It used to be — but shipping the built app inside the repository added ~50 MB
to its history with every version. Each release zip is now built from this
exact source by GitHub Actions and attached to the Release instead. Curious
how it works, or want to run from source? Start at the
[main README](../README.md).
