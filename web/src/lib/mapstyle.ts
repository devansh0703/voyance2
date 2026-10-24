/** Shared MapLibre style: visible real geography (OSM raster) — land, coasts,
 *  cities — used by every Voyance II map so tracks read like maritime traffic. */

export function voyanceMapStyle() {
  return {
    version: 8 as const,
    sources: {
      osm: {
        type: 'raster' as const,
        tiles: [
          'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        ],
        tileSize: 256,
        attribution: '© OpenStreetMap contributors (ODbL)',
        maxzoom: 19,
      },
    },
    layers: [
      { id: 'bg', type: 'background' as const, paint: { 'background-color': '#cfd8dd' } },
      { id: 'osm', type: 'raster' as const, source: 'osm', paint: { 'raster-opacity': 0.96 } },
    ],
  }
}
