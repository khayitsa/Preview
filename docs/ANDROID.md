# Feffel for Android

`android/` is a small native shell (one Java activity, no third‑party libraries) around the hosted
Feffel web app. The app itself is the Flask server; the APK is a full‑screen window onto it, so **the
server must be reachable over the internet** (for example on PythonAnywhere) for the APK to do anything.

## What the shell adds

| Need | How it's handled |
| --- | --- |
| Sign‑in persists | Cookies are accepted and flushed on pause |
| Uploading images/videos/files | `onShowFileChooser` → Android file picker |
| "Export publishing pack" ZIP | The page makes a `blob:` URL; a small hook streams it to **Downloads** via MediaStore |
| Other downloads (e.g. a media file) | Android `DownloadManager`, with the session cookie |
| External links | Opened in the browser; only your Feffel host stays in‑app |
| No connection | Local "Can't reach Feffel – Try again" page |
| Back button | Goes back in the web history, then closes the app |

Requires Android 10+ (API 29).

## 1. Host the server over HTTPS

Set these on the server (see `.env.example`):

```
FEFFEL_PUBLIC_URL=https://you.pythonanywhere.com
FEFFEL_SECURE_COOKIES=1
```

## 2. Build the APK

**Android Studio:** open the `android/` folder, then edit `feffelUrl` in `android/gradle.properties`
(or pass it on the command line) and press *Build ▸ Build APK(s)*.

**Command line** (needs JDK 17 and the Android SDK, `ANDROID_HOME` set):

```
cd android
./gradlew assembleDebug -PfeffelUrl=https://you.pythonanywhere.com
# → app/build/outputs/apk/debug/app-debug.apk
```

**GitHub Actions (no local setup):** push this project to your own repository, add a repository
variable `FEFFEL_URL` (Settings ▸ Secrets and variables ▸ Actions ▸ Variables), then run the
*Build Android APK* workflow. Download `Feffel-apk` from the run's artifacts.

## 3. Install

Copy `app-debug.apk` to the phone and open it (allow "install unknown apps" for your file manager or
browser when asked). The debug build is signed with Android's debug key, which is fine for your own
devices. For Play Store distribution you would build `assembleRelease` with your own keystore.

## Notes

* Changing the server address means rebuilding the APK – it is baked in at build time.
* If you point `feffelUrl` at a plain `http://` address (a LAN test server), cleartext traffic is
  enabled automatically for that build. Use HTTPS for anything real.
* The shell was written without being able to compile it in the authoring environment (Android SDK
  hosts were unreachable), so the first build is its first real test.
