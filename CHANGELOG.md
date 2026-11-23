# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.4.0] - 2026-11-23

### Added
- `compute_walkability(..., distance_method=...)` -- walkability index on road-network
  shortest paths (`"auto"` / `"straight"` / `"network"`), keeping only the nearest amenity
  and the per-category count so the working set stays at cells x categories
- `NetworkDistanceCalculator.nearest_by_category()` -- per-category minimum network
  distance and amenity counts without materializing a full distance matrix
- `NetworkDistanceCalculator.isolated_origins()` -- detects cells whose graph component
  holds no amenity at all, i.e. cells where a network distance cannot be computed
- `_network_isolated` column on `compute_walkability(..., distance_method="network")`
- Test suite `tests/test_network_isolation.py` (7 cases: fragment detection, label
  agnosticism, empty inputs, flag propagation, straight-mode behaviour)

### Changed
- Gangnam dashboard now scores walkability and the 15-minute city index on **network
  shortest-path distance** instead of straight-line distance; every label that claimed
  "straight distance" was corrected to "network distance"
- Dashboard aggregates exclude cells that are not computable: 396 cells, 380 scored,
  16 road-network-isolated cells (the published graph splits into 40 components, with
  96.7 % of nodes in the largest one). Isolated cells are rendered gray/dashed and
  labeled "not computable" on the map and in popups
- `docs/dashboard/data/grid.csv` and `grid.geojson` carry a `network_isolated` column /
  property, and `metric_basis` now reads `network_shortest_path_osm_tagged_nodes`
- `stats.json` adds `n_cells_scored`, `isolated_cells` and a `graph` block
  (nodes, edges, components, largest component share)

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
