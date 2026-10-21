# Android notes

> Status: the iOS path is proven end to end. The Android path in templates/make-video.sh is
> written from the tools' documentation and has NOT been run yet. Do a `--dry-run`, then a
> short recording, and check the sync before relying on it. Update this file with what you learn.

## Recording
- Prefer **scrcpy** (`brew install scrcpy`): `scrcpy -s <serial> --no-playback --no-audio --record=out.mp4 --max-fps=60`.
  Stop with SIGINT so the file is finalised. No length limit.
- `adb shell screenrecord` caps at 180 s per file (`--time-limit` max 180) and stores on the device;
  a demo run with two devices is longer than that. Only use it for short single-device demos,
  then `adb pull`.
- Recording start for marks: scrcpy logs when recording begins; the template greps for it.
  If the log line differs in your scrcpy version, sync visually instead: have the flow tap
  something obvious right after a `mark`, and adjust `rec_<key>` in marks.txt by the offset.

## Location
- Maestro `setLocation` works on Android emulators too; keep using it inside flows (same
  "override outlives the run" caveat).
- Manual alternative: `adb -s <serial> emu geo fix <LNG> <LAT>` (note: longitude first).
- Emulator needs Google Play services' location enabled; on API 30+ allow the app
  "precise" location once by hand, or grant with `adb shell pm grant <pkg> android.permission.ACCESS_FINE_LOCATION`.

## Clean status bar (System UI demo mode)
```
adb shell settings put global sysui_demo_allowed 1
adb shell am broadcast -a com.android.systemui.demo -e command enter
adb shell am broadcast -a com.android.systemui.demo -e command clock -e hhmm 0941
adb shell am broadcast -a com.android.systemui.demo -e command battery -e level 100 -e plugged false
adb shell am broadcast -a com.android.systemui.demo -e command notifications -e visible false
# exit: adb shell am broadcast -a com.android.systemui.demo -e command exit
```

## Networking (dev builds and local APIs)
- The emulator reaches the Mac's localhost at `10.0.2.2`; or map ports so `localhost` works:
  `adb -s <serial> reverse tcp:8081 tcp:8081` (Metro) and the same for a local API port.
- Maestro's `runScript` JavaScript (flows/lib/mark.js) runs on the **host**, not the device,
  so posting marks to `http://127.0.0.1:8787` works for Android flows unchanged.

## Maestro on Android
- `maestro test --udid <serial>`; multiple emulators in parallel work (separate adb serials).
- `testID` maps to `resource-id` on Android (React Native sets it), so `id:` selectors carry over.
- Dev-build warning toast (LogBox) looks the same; the dismiss point may need adjusting for
  the emulator's aspect ratio and navigation bar.

## Mixed iOS + Android in one video
- edit.py scales each recording by its own aspect ratio, so an iPhone and a Pixel sit side by
  side at the same height with slightly different widths. That reads fine; say so to the user
  rather than forcing equal frames.

## Device frame
- Emulator recordings include no rounded corners; edit.py's corner mask (13% of width)
  approximates a modern phone. Pixel-style punch-hole cameras are not drawn.
