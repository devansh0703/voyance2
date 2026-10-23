"""Precompute Voyance II artifacts: clustered port table, maritime graph, H3/HDBSCAN JSON."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from geo import PortMatcher, load_ports  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "data" / "processed"
MODELS = ROOT / "models"
ART.mkdir(parents=True, exist_ok=True)


def main():
    ports = load_ports(str(ROOT / "data" / "raw" / "unlocode.csv"))
    m = PortMatcher(ports, 15.0)
    m.ports.to_csv(ART / "ports-clustered.csv", index=False)
    print("ports-clustered:", len(m.ports))

    from backend.live import analytics as an
    G = an.build_maritime_graph(m.ports.reset_index(drop=True), max_nm=600.0)
    with (MODELS / "maritime_graph.pkl").open("wb") as f:
        pickle.dump(G, f)
    print("graph nodes/edges:", G.number_of_nodes(), G.number_of_edges())

    df = pd.read_parquet(ROOT / "data" / "interim" / "features-2024-07.parquet")
    df = df[df["vessel_type_group"].isin(["cargo", "tanker", "passenger"])]
    hexes = {r: an.h3_hexbin(df["lat"].to_numpy(), df["lon"].to_numpy(), r, top=300)
             for r in (3, 4, 5)}
    (ART / "h3-density.json").write_text(json.dumps(hexes))

    slow = df[df["sog"] < 1.0]
    anch = an.hdbscan_anchorages(slow["lat"].to_numpy(), slow["lon"].to_numpy())
    (ART / "anchorages.json").write_text(json.dumps(anch))
    print("h3 resolutions:", list(hexes), "| anchorage clusters:", len(anch["clusters"]))


if __name__ == "__main__":
    main()
