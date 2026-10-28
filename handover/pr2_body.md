## What

Adds `pandapipes.plotting.create_map_figure`: an interactive plotly plot of a network on a web map, **without any access token or account**.

This replaces my earlier PR #714, which needed a Mapbox token and used `go.Scattermapbox` (since removed from plotly). This version uses plotly's MapLibre traces (`go.Scattermap`, plotly >= 5.24) with the built-in token-free styles (`carto-positron`, `open-street-map`, ...).

## Use case: temperatures in a district heating loop

The tutorial draws the *Schutterwald* district heating grid that ships with pandapipes. The central pump heats the water to 70 °C; the supply pipes cool down along the way (49-70 °C) and the return pipes carry the cooled water back (35-56 °C). Pipes without flow are drawn grey and excluded from the color range.

<!-- ATTACH SCREENSHOT HERE -->

```python
from pandapipes.plotting import create_map_figure, convert_epsg_junction_geodata, convert_epsg_pipe_geodata

convert_epsg_junction_geodata(net, epsg_in=31467, epsg_out=4326)   # only if coordinates are projected
convert_epsg_pipe_geodata(net, epsg_in=31467, epsg_out=4326)
pp.pipeflow(net, mode="sequential")
net.res_pipe["t_to_c"] = net.res_pipe.t_to_k - 273.15
create_map_figure(net, pipe_result="t_to_c", colorbar_title="Water temperature [°C]").show()
```

## Features

- Junctions, pipes (uses `pipe_geodata` if present), ext_grids, sources, sinks, pumps, valves and other branch components
- Optional pipe coloring by any `net.res_pipe` column with a colorbar (one trace per color bin, so it stays fast on large networks)
- Map is fitted to the network automatically
- Clear errors for projected coordinates, missing results and unknown columns; junctions without coordinates are skipped with a warning
- New helper `convert_epsg_pipe_geodata`, the pipe counterpart of `convert_epsg_junction_geodata`

## Safe to add

- No new required dependency: plotly is imported lazily; `plotly>=5.24` is in the optional `plotting` and `test` extras. `import pandapipes` works without plotly and the function raises a clear install hint.
- Existing plotting functions (`simple_plot`) are untouched.
- The basemap tiles are loaded by the browser from public tile servers, so seeing the background needs internet; the figure itself is built offline.

## Tests and docs

- `test_plotly_map.py` (13 tests, no network or token needed)
- Tutorial `tutorials/plotly_map_plotting.ipynb` (passes with nbmake), docs page, CHANGELOG entry
