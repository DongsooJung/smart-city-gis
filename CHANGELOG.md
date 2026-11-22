# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] - 2026-11-22

### Added
- `pyproject.toml` packaging -- `pip install smartcity-gis` support
- Optional extras: `network` (OSMnx, Pandana), `viz` (Folium, matplotlib), `stats` (PySAL), `dev`
- PyPI publish workflow (`.github/workflows/publish.yml`): tests then upload on release
- `CHANGELOG.md`

### Fixed
- Add `scipy` to runtime dependencies -- used by `accessibility.py` (`scipy.spatial.distance.cdist`) but missing from `requirements.txt`

## [0.1.0] - 2026-04-16

### Added
- Initial public release: walkability index, Shannon diversity, `create_fishnet` grid
- 2SFCA / gravity accessibility, isochrones, 15-minute city score
- OSM Overpass collector and Gangnam interactive dashboard
