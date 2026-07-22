"""
시각화 유틸리티

정적(Matplotlib) 코로플레스와 인터랙티브(Folium) 지도, 그리고
브라우저용 대시보드 데이터(GeoJSON/JSON) 내보내기를 제공한다.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import geopandas as gpd

logger = logging.getLogger(__name__)

WGS84 = 4326


def choropleth_png(
    gdf: gpd.GeoDataFrame,
    column: str,
    out_path: str,
    cmap: str = "YlGn",
    title: Optional[str] = None,
    figsize: tuple[int, int] = (12, 12),
) -> str:
    """GeoDataFrame 컬럼을 코로플레스 PNG로 저장."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=figsize)
    gdf.plot(column=column, cmap=cmap, legend=True, ax=ax, edgecolor="none")
    if title:
        ax.set_title(title, fontsize=15)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def folium_choropleth(
    gdf: gpd.GeoDataFrame,
    column: str,
    center: Optional[tuple[float, float]] = None,
    zoom: int = 13,
    fill_color: str = "YlGn",
):
    """Folium 인터랙티브 코로플레스 지도 반환(folium.Map)."""
    import folium

    g = gdf.to_crs(WGS84) if gdf.crs and gdf.crs.to_epsg() != WGS84 else gdf
    if center is None:
        c = g.geometry.union_all().centroid if hasattr(g.geometry, "union_all") else g.geometry.unary_union.centroid
        center = (c.y, c.x)

    m = folium.Map(location=center, zoom_start=zoom, tiles="CartoDB positron")
    folium.Choropleth(
        geo_data=g.__geo_interface__,
        data=g.reset_index(),
        columns=["index", column],
        key_on="feature.id",
        fill_color=fill_color,
        fill_opacity=0.75,
        line_opacity=0.1,
        legend_name=column,
    ).add_to(m)
    return m


def export_dashboard_geojson(
    gdf: gpd.GeoDataFrame,
    out_path: str,
    keep_cols: Optional[list[str]] = None,
) -> str:
    """
    대시보드(브라우저)용 GeoJSON을 EPSG:4326으로 내보낸다.

    좌표 정밀도를 6자리로 낮춰 파일 크기를 줄인다.
    """
    g = gdf.to_crs(WGS84) if gdf.crs and gdf.crs.to_epsg() != WGS84 else gdf
    if keep_cols is not None:
        cols = [c for c in keep_cols if c in g.columns] + ["geometry"]
        g = g[cols]

    geo = json.loads(g.to_json())
    Path(out_path).write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")
    logger.info("대시보드 GeoJSON 저장: %s (%d features)", out_path, len(g))
    return out_path
