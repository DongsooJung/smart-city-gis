# Network Distance Accessibility

Straight-line (Euclidean) distance treats cities as frictionless planes. Real pedestrians follow a road and path network, and the difference between the two distance models is often large enough to change policy conclusions. This guide explains how `smart-city-gis` computes network-distance accessibility, how to rerun 2SFCA and 15-minute-city analyses on network distance, and how to validate the results.

## Why straight-line distance fails

Euclidean buffers systematically overestimate accessibility. The failure modes below are common in Korean urban contexts and elsewhere:

- **Water, rail, and highway barriers.** A river, railway yard, or expressway may cut a neighborhood in half. A park 300 m away as the crow flies can require a 1.5 km detour to the nearest crossing.
- **Gated or controlled-access complexes.** Large apartment compounds and institutional campuses often have one or two entrances. Residents across the street from a facility may walk several hundred extra meters to a gate.
- **One-way streets and turn restrictions.** Vehicle-based supply (e.g., ambulance stations) can be distance-asymmetric: the trip out and the trip back have different lengths. Pedestrian networks are mostly symmetric, but road networks are not.
- **Pedestrian-prohibited segments.** Expressway ramps, tunnels, and some bridges legally or practically exclude pedestrians. A straight line that crosses such a segment is not a walkable path.
- **Slope and walkability.** A 5 % grade over 400 m is not equivalent to 400 m of flat ground, especially for elderly populations. Plain network distance still ignores slope (see Limitations), but it at least follows real walkable geometry.

The net effect: straight-line 2SFCA scores tend to be optimistically biased near barriers and around gated land uses, and 15-minute-city scores based on circular buffers can claim category coverage that no resident can actually reach on foot.

## How network distance is computed

`smart-city-gis` builds accessibility on top of a routable graph. The methodology has four steps.

**1. Point-to-node snapping.** Each demand point, supply point, grid centroid, or amenity is snapped to its nearest graph node. Graph nodes must carry `x` (longitude) and `y` (latitude) attributes. Graphs produced by `osmnx.graph_from_place()` or `graph_from_polygon()` satisfy this automatically. The Euclidean offset from the point to its snapped node is the snapping error; it is not added to the path length.

**2. Weighted shortest paths.** All network distances are shortest-path lengths over edges weighted by the `length` attribute (meters). OSMnx graphs include `length` by default. Computations run in EPSG:5186 (Korea Transverse Mercator, meters); input GeoDataFrames in any CRS are reprojected internally, and CRS-less inputs are assumed to already be in EPSG:5186.

**3. Catchment cutoff.** The catchment radius is `d0 = travel_speed × catchment_minutes`, converted to meters. Pairs beyond `d0` receive weight zero under every decay function (`"gaussian"`, `"linear"`, `"threshold"`). Internally, shortest-path searches stop at `d0`, which is also the main performance lever.

**4. Unreachable pairs.** Pairs with no path, or whose path exceeds the cutoff, get distance `np.inf` and decay weight 0. They never contribute to accessibility; they do not raise errors.

The default walking speed is **4.5 km/h** (≈75 m/min), a standard moderate adult pace. A 15-minute catchment at this speed is 1,125 m of network distance.

## Rerunning 2SFCA with network distance

Build an analyzer with a network and pass it to the same call used for straight-line analysis:

```python
import osmnx as ox
import geopandas as gpd
from smartcity_gis.accessibility import AccessibilityAnalyzer

# Pedestrian network for the study area
G = ox.graph_from_place("Jongno-gu, Seoul, South Korea", network_type="walk")

analyzer = AccessibilityAnalyzer(network=G)

demand = gpd.read_file("census_blocks.geojson")   # has "population" column
supply = gpd.read_file("clinics.geojson")         # has "capacity" column

scores = analyzer.two_sfca(
    demand_points=demand,
    supply_points=supply,
    catchment_minutes=30,
    decay="gaussian",
    travel_speed=4.5,
    demand_col="population",
    supply_col="capacity",
    distance_method="auto",   # network is present -> network distance
)
print(scores.describe())
```

`distance_method="auto"` selects network distance whenever a network is attached and falls back to straight-line distance otherwise. To force a mode, use `"straight"` or `"network"`; `"network"` without a network raises `ValueError`. Comparing both modes isolates the network effect:

```python
straight = analyzer.two_sfca(demand, supply, distance_method="straight")
network = analyzer.two_sfca(demand, supply, distance_method="network")
delta = network - straight   # negative deltas = Euclidean optimism
```

To inspect the underlying distance surface directly:

```python
D = analyzer.network_distance_matrix(
    origins=demand,
    destinations=supply,
    cutoff_m=2250,   # 30 min at 4.5 km/h; beyond this -> np.inf
)
```

`D` is a NumPy array in meters with `np.inf` for unreachable or cutoff-exceeding pairs. Passing `cutoff_m` is strongly recommended for large problems.

## Rerunning the 15-minute-city score

```python
from smartcity_gis.accessibility import fifteen_min_city_score

grid = gpd.read_file("analysis_grid.geojson")
amenities = gpd.read_file("pois.geojson")  # has "category" column

score = fifteen_min_city_score(
    grid,
    amenities,
    network=G,
    minutes=15,
    travel_speed=4.5,
    essential_categories=None,  # default set
    distance_method="auto",
)
```

The score counts, per grid cell, how many essential categories (0–6) have at least one amenity reachable within 15 minutes. With `network=G`, reachability is judged on actual network distance rather than a 1,125 m circle. Expect scores to drop in cells near rivers, rail corridors, and gated complexes — that drop is the point of the analysis.

## Walkability score on network distance

`compute_walkability` accepts the same `distance_method` switch, so the walkability index can be built on real walk paths instead of circles:

```python
from smartcity_gis import compute_walkability

walk = compute_walkability(grid, amenities, network=G, decay="exponential")
walk["walkability_score"]        # 0-100, network shortest-path based
walk["_network_isolated"]         # True where no distance can be computed
```

In network mode the implementation keeps only the nearest amenity per category and the number of amenities per category, so the working set stays at *cells × categories* instead of the full *cells × amenities* distance matrix.

## Road-network fragments: cells where no score can be computed

Selected highway graphs are rarely a single connected component. A cell whose nearest node sits in a fragment that contains **no** amenity has no path to any facility at all, so its network distance is undefined — not "far away", but unmeasurable. Such cells would silently become `0` and drag every aggregate down, which reads like a real accessibility finding when it is a data artifact.

`NetworkDistanceCalculator.isolated_origins()` detects this topologically — distance-independent, because the criterion is *which component the node belongs to*:

```python
from smartcity_gis.accessibility import NetworkDistanceCalculator

isolated = NetworkDistanceCalculator(G).isolated_origins(cell_xy, amen_xy)
```

`compute_walkability(..., distance_method="network")` returns the same information as the `_network_isolated` column. Keep the score at `0` for schema compatibility, but **exclude flagged cells from means, histograms and threshold rates**, and label them on the map as "not computable" rather than "no access".

Real measurement on the published Gangnam dashboard (15,574 nodes, 18,820 edges): the graph splits into **40 components**, with 15,063 nodes (96.7 %) in the largest one. Of 396 grid cells, **16** attach to amenity-free fragments. Aggregates therefore cover 380 cells (mean walkability 43.1, 93.9 % of cells reaching a 15-minute score of 4 or more), and the dashboard ships the flag in `grid.csv` / `grid.geojson` as `network_isolated`.

Note that a cell *inside* a component that does contain amenities but has none within the catchment radius is **not** isolated — that is a genuine low-accessibility result and must stay in the statistics.

## Validating the 2SFCA conservation property

2SFCA obeys a conservation law: with exactly one demand point and one supply point, both within catchment of each other, the accessibility score equals the supply-to-demand ratio. This is the cheapest end-to-end test of the network pipeline:

```python
import geopandas as gpd
from shapely.geometry import Point

one_demand = gpd.GeoDataFrame({"population": [1000]},
                              geometry=[Point(953000, 1952000)], crs="EPSG:5186")
one_supply = gpd.GeoDataFrame({"capacity": [50]},
                              geometry=[Point(953500, 1952500)], crs="EPSG:5186")

a = analyzer.two_sfca(one_demand, one_supply, distance_method="network")
assert abs(a.iloc[0] - 50 / 1000) < 1e-9, a.iloc[0]
```

The test must use real coordinates that snap onto the graph. If the result is not `capacity / population`, check in order: (1) the two points snap to connected nodes (query `network_distance_matrix` for the pair — it must be finite); (2) the network distance between the snapped nodes is below `d0` (otherwise the decay weight is 0 and the score is 0); (3) the CRS of the inputs is declared correctly.

## Performance guidance

Network accessibility scales poorly if run naively. Practical rules:

- **Always pass a cutoff.** `network_distance_matrix(..., cutoff_m=...)` truncates Dijkstra searches at the catchment radius. Without it, every origin explores the entire graph.
- **Match the cutoff to the analysis.** For `catchment_minutes=15` at 4.5 km/h, `cutoff_m=1125`. Tighter cutoffs give near-linear speedups.
- **Trim the graph.** Extract the network for the study area plus a buffer equal to the largest catchment radius, not for the whole country. Remove unreachable components with `ox.utils_graph.get_largest_component(G)`.
- **Reuse the analyzer.** One `AccessibilityAnalyzer(network=G)` caches the prepared graph; repeated `two_sfca` calls on the same graph avoid re-preprocessing. Do not rebuild the graph per call.
- **Control grid size.** Cost grows roughly as `origins × cutoff-limited search area`. For fine grids over large cities, aggregate demand to coarser cells or run per-district.
- **Pandana (not implemented yet).** The current implementation runs Dijkstra on `networkx`. A future backend could use `pandana`'s contracted graph for very large origin sets; treat this as an optimization to come, not an available option today.

## Limitations

- **Snapping error.** Points are assigned to the nearest node; the final meters from the node to the actual door are ignored. In dense networks this is small; around large blocks it can reach 100–200 m.
- **Undirected assumption.** Shortest paths ignore one-way restrictions. This is acceptable for pedestrian analyses and a real caveat for vehicle-based supply.
- **Constant speed.** A single 4.5 km/h pace is applied to every edge. Slope, surface quality, signal delays, and demographic variation (children, elderly) are not modeled.
- **Optional dependencies.** If `osmnx` or `pandana` is not installed, network-backed construction is unavailable. An analyzer created without a network silently computes **straight-line** distances under `distance_method="auto"` — a Euclidean approximation. Always confirm which mode was used (force `"network"` if network distance is a methodological requirement).

## Validation checklist

1. The graph has `x`/`y` on nodes and `length` (meters) on edges; confirm with one node and one edge inspection.
2. Input GeoDataFrames carry a CRS, or are verified to already be in EPSG:5186.
3. `distance_method` is what you intend; use `"network"` to fail loudly instead of falling back.
4. `network_distance_matrix` on a sample of known nearby pairs returns finite, plausible distances.
5. Unreachable test pairs return `np.inf`, not an exception.
6. The single-demand/single-supply conservation test passes (score = supply/demand).
7. A pair placed just beyond `d0` scores exactly 0 under all three decay functions.
8. Network scores are ≤ straight-line scores near a known barrier (river, rail yard, expressway).
9. 15-minute-city scores decrease (or stay flat) when switching from straight-line to network mode, never increase systematically.
10. A rerun with `catchment_minutes` halved produces no scores above the original run.
11. Reusing one analyzer across calls gives identical results to building a fresh analyzer (cache consistency).
12. Performance run uses `cutoff_m` and a trimmed, largest-connected-component graph.
13. `isolated_origins` flags only amenity-free fragments, and flagged cells are excluded from every published aggregate.
