# Changelog

All notable changes to this project will be documented in this file.

## [v5.84] - 2026-09-01
### Added
- **Scaled-Asset Consolidation (Experimental):** Scaled-down duplicates of a larger asset are consolidated to reuse the larger asset with composed transforms — supports any rotation, flip, and scale (free-angle ORB matching), minimum 50% scale ratio, regions only.
### Improved
- **Consolidation Chain Resolution:** Chains of scaled/mirrored consolidations are resolved to their terminal assets with composed transforms, and long chains (e.g. 0.32 net scale) now get direct ORB re-verification with wide scale bounds instead of relying on composition alone.
- **Mirror/Match Accuracy:** Replaced the histogram gate with an error-blob gate — eliminates text false positives (e.g. stroked text variants) while allowing genuine mirrored/rotated matches that were previously rejected.

## [v5.83] - 2026-09-01
### Fixed
- **Digit-Ending Sequence Bases (Critical):** Sequences whose base path itself ends with digits (e.g. expl_000 with frames expl_00000.png...) were not resolved at all — "source PNG not found" — and the sequence was silently skipped. The resolver now also treats an unmatched ref as a raw prefix followed by frame digits, and the exported JSON path keeps the original sequence base intact instead of stripping its digits.

### Added
- **Stale Temp Folder Sweep:** At the start of each run, leftover spine_temp_* folders from previous interrupted/aborted runs (older than 1 hour) are automatically removed from the output folder (unless "Keep temporary files" is enabled).

## [v5.82] - 2026-09-01
### Added
- **Asset Size Statistics:** The Processing Statistics report now shows the total size of all exported assets in MB — a grand total across all skeletons (with JPEG/PNG breakdown) plus per-skeleton totals next to the JPEG/PNG file counts.

## [v5.81] - 2026-09-01
### Fixed
- **Skin Sequence Paths (Critical):** In projects using skins, same-named sequences from different skins collapsed into one shared output folder. Frames of the second skin were silently skipped (never copied) and both skins' JSON paths pointed at the first skin's files. Sequence folders now preserve skin-owned folder prefixes (e.g. png/pink/glow, png/gold/glow), so each skin keeps its own frames and correct paths.

### Added
- **Destination Collision Warning:** If two different source files ever map to the same output destination, a red warning is printed in the Info panel naming the skin, file, and conflicting source instead of silently dropping the frame.

## [v5.80] - 2026-07-09
### Fixed
- **Reference Image Crash (Critical):** Processing failed silently ("Sorting step failed: expected str... not NoneType") for projects containing reference images, preventing the .spine file from being created. Reference images now get a proper destination in the global images folder.
- **Shared Image Folder Duplication:** When an image is shared between projects (e.g. sparkle.png used in both persistence and logo), the sorter now keeps the folder name from the JSON/skeleton path (logo/png/...) instead of adopting the .spine file name (logo_v2/png/...), preventing duplicate folders.
- **Sequences Excluded from Consolidation:** Sequence frames are never merged by duplicate/similar-image consolidation anymore — neighbouring frames are visually similar and merging them broke animations.

### Added
- **Crash Diagnostics:** Native crashes and uncaught errors are logged to ~/spine_sorter_crash.log; the full Info log is mirrored to ~/spine_sorter_session.log for post-mortem diagnosis. Sorting failures now show a full traceback in the log.

## [v5.79] - 2026-07-09
### Changed
- **Fix Attachment Names:** The option is now enabled by default. Users who explicitly disabled it keep their saved preference.

## [v5.78] - 2026-07-08
### Added
- **Fix Attachment Names (Settings):** New option that renames attachments whose names differ from their image paths so the name exactly matches the path (prevents runtime lookup issues in game engines). Works for regions, meshes, linked meshes AND sequences. All references are updated automatically: slot setup-pose attachments, animation attachment-swap timelines, deform/FFD timelines, Spine 4.x sequence (`attachments`) timelines, and linked-mesh parents. Ambiguous renames (same name, different paths across skins) and name collisions are skipped safely with a warning.

### Fixed
- **Consolidation Crash:** Fixed `NameError: 'similarity_mode' is not defined` that aborted processing whenever similar-image groups were found during consolidation.

## [v5.77] - 2026-03-18
### Test
- Version lock verification release — confirms v5.76 EXE correctly blocks on outdated version check.

## [v5.76] - 2026-03-18
### Fixed
- **Version Lock (Critical):** The update check was silently skipped in PyInstaller EXEs due to SSL certificate errors (common on Windows/Mac when CA certs aren't bundled). The check now retries without SSL verification as a fallback, and blocks launch entirely if GitHub cannot be reached — preventing stale versions from running undetected.

## [v5.75] - 2026-03-18
### Fixed
- **Version Gatekeeper:** `version.txt` is now automatically updated by `push_new_version.bat` on every release, ensuring users on outdated versions are always prompted to update.
- **Version Lock:** Fixed a gap where versions 5.73 and 5.74 could launch without an update prompt because `version.txt` was never bumped after publishing.

## [v5.74] - 2026-03-18
### Changed
- Internal version bump.

## [v5.73] - 2026-03-03
### Fixed
- **Build:** Fixed GitHub Actions workflow — PDF manual is now generated fresh in CI and correctly bundled into the EXE via `--add-data`. Fixed broken `EXTRA` variable pattern that caused PyInstaller to receive malformed arguments.
- **Help File:** Fixed "Manual Not Found" error in distributed EXE. App now uses `sys._MEIPASS` (correct PyInstaller temp dir) to locate the bundled manual instead of `__file__`.

## [v5.72] - 2026-03-03
### Fixed
- **Sequence Copy:** Fixed sequence frames not being copied when consolidation was enabled. Sequence frames could incorrectly appear in the consolidation map (as near-duplicates of other images), causing them to be silently filtered out before the copy step. Sequences are now always exempt from this filter.
- **Sequence Resolution:** Fixed sequences with a path like `ambient/png/folder/base_name_` not being resolved to their frame files (`base_name_01.png`, `base_name_02.png`, etc.). The file resolver now expands trailing-underscore references into all numbered variants during the initial scan.
- **Duplicate Check Cleanup:** Removed duplicate `if not is_hash_candidate` gate in the no-OpenCV fallback path of the image similarity function, and removed a stale comment that had been placed inside unreachable dead code.

## [v5.71] - 2026-02-21
### Added
- **New Checkbox:** Added **"Consolidate Duplicate Images"** checkbox. When enabled, identical images (by content/SHA1) are merged into a single file to save space, and all JSON references are remapped to this single file.
- **New Checkbox:** Added **"Check for Errors Only (No Export)"** checkbox. Use this to run a quick validation scan (missing files, animation integrity) without modifying any files or creating exports.

### Fixed
- **Multi-Skeleton Export Logic:** Fixed a critical issue where exporting multiple skeletons from a single source file would result in separate files or overwrites. Now, all skeletons from the same source `input_path` are correctly merged into a single destination `.spine` project file.
- **Reporting Metrics:** Corrected the "Total used images in Spine" statistic to accurately count unique image paths used in the final project, ignoring duplicates and unused attachments.
- **Duplicate Consolidation:** Fixed the JSON path construction for consolidated images. Previously, consolidated images might point to the old filename in the JSON, causing "Missing Image" errors in Spine. Now, the JSON path correctly points to the consolidated (primary) image file.
- **Report Cleanliness:** Suppressed duplicate image group warnings in the final verified report when "Consolidate Duplicates" is enabled. The report now treats resolved duplicates as success rather than warnings.

## [v5.70]
### Fixed
- **Version Fetching:** "Fetch All" now correctly handles "-beta" versions (e.g., 4.2.69-beta) in the version launcher, preventing download errors for beta releases.

## [v5.69]
### Added
- **Version Launcher:** Added "Fetch All" button to allow downloading specific patch versions (e.g., 4.1.18, 4.0.57) directly from the official archive.

## [v5.68]
### Fixed
- **macOS Compatibility:** Resolved an issue where the Spine Version Launcher would show a limited list of versions on macOS laptops.

## [v5.67]
### Added
- **Version Management:** Added "Active Spine Version" switcher dropdown.
- **Launcher:** Added "LAUNCH SPINE" button to launch the specific version selected.
- **Export Workflow:** "Open after export" now respects the chosen version in the dropdown.
- **Documentation:** Fixed application crash when clicking the "Help" button; docs now open correctly.
### Improved
- **Stability:** Cleaned up project structure and temporary file handling.
