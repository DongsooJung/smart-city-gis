# Smart City GIS Analytics

> GIS-based urban analytics platform for smart city planning and policy simulation

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![QGIS](https://img.shields.io/badge/QGIS-3.x-589632?style=flat-square&logo=qgis&logoColor=white)](https://qgis.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

## Problem

Korean urban planning decisions often rely on fragmented data across multiple government agencies. Planners lack integrated spatial analysis tools that combine census data, transportation networks, land use, and real estate transactions into actionable intelligence.

## Solution

An end-to-end GIS analytics pipeline that:

1. **Ingests** multi-source Korean spatial data (NSDI, KOSIS, MOLIT, V-World)
2. **Processes** coordinate transformations (EPSG:5186 ↔ EPSG:4326), geocoding, spatial joins
3. **Analyzes** accessibility indices, walkability scores, land use mix entropy
4. **Visualizes** interactive maps with Folium/Kepler.gl for stakeholder presentations

## Applied Projects

| Project | Client/Partner | Year | Methods |
|---------|---------------|------|---------|
| Suwon Military Airport Relocation Impact | Research Institute | 2023 | Buffer analysis, DID |
| Gimpo Smart Regeneration Feasibility | KDI | 2023 | Accessibility index, cost-benefit |
| Bucheon Station Area Development | Municipal Gov't | 2022 | Land use analysis, 3D modeling |

## Tech Stack

- **GIS Core:** GeoPandas, Shapely, Fiona, Rasterio, QGIS (PyQGIS)
- **Visualization:** Folium, Kepler.gl, Deck.gl, Matplotlib
- **APIs:** V-World, Kakao Local, SGIS (통계지리정보서비스)
- **Database:** PostGIS, SQLAlchemy
- **Compute:** Dask (large-scale spatial operations)

## Repository Structure

```
smart-city-gis/
├── src/
│   ├── data_ingestion/         # API connectors (V-World, KOSIS, MOLIT)
│   ├── preprocessing/          # CRS transform, geocoding, cleaning
│   ├── analysis/               # Accessibility, walkability, land use mix
│   └── visualization/          # Map generators (Folium, Kepler.gl)
├── notebooks/
│   ├── 01_data_collection.ipynb
│   ├── 02_spatial_preprocessing.ipynb
│   ├── 03_accessibility_analysis.ipynb
│   └── 04_interactive_dashboard.ipynb
├── data/
│   └── README.md
├── docs/
│   ├── data_dictionary.md
│   └── crs_reference.md
├── tests/
├── requirements.txt
└── LICENSE
```

## Quick Start

```bash
git clone https://github.com/DongsooJung/smart-city-gis.git
cd smart-city-gis
pip install -r requirements.txt
jupyter notebook notebooks/01_data_collection.ipynb
```

## License

MIT License

## Author

**Dongsoo Jung** — Ph.D. Candidate, Seoul National University  
Smart City Engineering · Civil & Environmental Engineering
