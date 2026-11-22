# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.3.0] - 2026-11-22

### Added
- Network distance accessibility: `two_sfca(..., distance_method="network")` computes
  catchment weights from road-network shortest paths instead of straight-line distance
- `AccessibilityAnalyzer.network_distance_matrix(origins, destinations, cutoff_m)` --
  public pairwise network distance surface in meters (`np.inf` for unreachable pairs)
- `NetworkDistanceCalculator` (exported from the package root) with node snapping,
  edge-length weighting, and catchment cutoff
- `fifteen_min_city_score(..., network=...)` now judges reachability on actual network
  distance instead of ignoring the `network` argument
- `distance_method` option (`"auto"` / `"straight"` / `"network"`) on 2SFCA and the
  15-minute city score
- `docs/network_distance.md` -- methodology, validation checklist, and performance guidance
- Test suite `tests/test_network_distance.py` (17 cases: distance matrix, unreachable
  components, both reachability directions, conservation law, cutoff semantics)

### Changed
- `_decay` now evaluates only inside the catchment radius, so unreachable (`inf`) pairs
  are weighted 0 without infinite arithmetic
- `get_isochrone` shares the graph-node coordinate helper with the new calculator

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
