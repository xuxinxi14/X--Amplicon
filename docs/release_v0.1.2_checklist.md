# X-Amplicon v0.1.2 Release Metadata Checklist

Date prepared: 2026-05-15

This checklist records the metadata cleanup needed before creating GitHub release `v0.1.2` and letting Zenodo archive the release.

## Updated in this cleanup

- Root `CITATION.cff` now uses `license: GPL-3.0-only`.
- Root `CITATION.cff` now uses `version: "0.1.2"`.
- Root `CITATION.cff` release URL now points to `https://github.com/xuxinxi14/X--Amplicon/releases/tag/v0.1.2`.
- Inno Setup installer metadata now reports version `0.1.2` and outputs `X-Amplicon-Setup-v0.1.2.exe`.
- README installer names were updated from `X-Amplicon-Setup-v0.1.0.exe` to `X-Amplicon-Setup-v0.1.2.exe`.
- Old local runs, manuscripts, generated packages, media files and the large local SILVA database were moved under `_archive/pre_v0.1.2_cleanup_20260515/` instead of being deleted.

## Before publishing v0.1.2

1. Review `git status` and stage only intentional tracked changes.
2. Rebuild the Windows payload and installer so `X-Amplicon-Setup-v0.1.2.exe` exists under `dist/installer/`.
3. Rebuild Linux and macOS release archives if they will be attached to the release.
4. Confirm release assets carry GPL-3.0 project license files.
5. Create Git tag/release `v0.1.2` from the cleaned commit.
6. Confirm Zenodo archives `v0.1.2` and reports GPL-3.0-compatible license metadata.
7. Record the new Zenodo DOI, GitHub tag commit and release asset checksums in the manuscript review workspace.

## Important note

Editing Zenodo metadata for `v0.1.1` can reduce visible license mismatch, but it will not change files inside the existing `v0.1.1` source archive. A new `v0.1.2` release is the cleaner route for synchronizing `CITATION.cff`, source-tree license, GitHub release and Zenodo metadata.