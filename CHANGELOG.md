# Changelog

All notable changes to this project will be documented in this file.

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
