# Spine Sorter v5.77

**A smart automation tool for Spine 2D animation projects.**  
Sorts images, detects missing files, validates animations, and ensures your exports are game-ready.

---

## Download

| Platform | Link |
|----------|------|
| **Windows** | [SpineSorter-Windows.exe](https://github.com/saleklar/spine-sorter/releases/latest/download/SpineSorter-Windows.exe) |
| **Mac** | [SpineSorter-Mac.zip](https://github.com/saleklar/spine-sorter/releases/latest/download/SpineSorter-Mac.zip) |
| **All Releases** | [github.com/saleklar/spine-sorter/releases](https://github.com/saleklar/spine-sorter/releases) |

---

## What It Does

- **Smart Sorting** — Automatically separates JPEGs (opaque) from PNGs (transparent)
- **Broken Link Detector** — Finds images referenced in JSON that are missing on disk
- **Animation Guardian** — Compares project animations vs exported output, flags missing clips
- **Visibility Police** — Detects hidden/invisible slots that would be invisible in-game
- **Consolidate Duplicates** — Merges visually identical images to save space, remaps all JSON references
- **Validate Only Mode** — Run a health check without touching any files
- **Version Manager** — Choose exactly which installed Spine version to use per project

---

## How To Use

1. **Browse** — Select the folder containing your `.spine` files
2. **Select** — Pick the character file from the list
3. **Run** — Click `Run Selected File`
4. **Review** — A popup report shows results; save it with `Save As`

Click the **`?`** button in the app to open the full manual.

---

## Changelog

### v5.77
- Test: Version lock verification release

### v5.76
- Fixed: Version lock now works correctly in PyInstaller EXE — SSL cert errors no longer silently bypass the update check

### v5.75
- Fixed: Version gatekeeper now correctly blocks outdated versions — `version.txt` is auto-updated on every release via `push_new_version.bat`

### v5.74
- Internal version bump

### v5.73
- Fixed: Help button now works in the distributed EXE — manual is bundled and always accessible
- Fixed: GitHub Actions build failures caused by broken shell argument quoting

### v5.72
- Fixed: Removed duplicate logic gate in image similarity fallback path

### v5.71
- New: "Consolidate Duplicate Images" checkbox
- New: "Check for Errors Only" checkbox (validation without export)
- Fixed: Multi-skeleton export now merges correctly into one `.spine` file
- Fixed: Consolidated images now update JSON paths correctly

### v5.69
- New: "Fetch All" button to retrieve all historical Spine versions

### v5.67
- Feature: Active Version Switcher (dropdown) and Quick Launcher
- Fixed: "Open after export" now respects selected Spine version

---

## Requirements (running from source)

```
pip install -r requirements.txt
python "spine sorter 257.py"
```
