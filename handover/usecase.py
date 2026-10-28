import pandas as pd
import pandapipes as pp
import pandapipes.networks as nw
from pandapipes.plotting import (create_map_figure, convert_epsg_junction_geodata,
                                 convert_epsg_pipe_geodata)

net = nw.schutterwald_heat()

# Only the supply side has junction coordinates; place each return junction ~6 m next to its supply partner
names = net.junction.name
has_geo = net.junction_geodata.x.notna()
supply_of = pd.Series(names[has_geo].index, index=names[has_geo])
return_junctions = names.index[~has_geo]
partners = supply_of[names[return_junctions].str.removeprefix("return_")].values
shift = [5.0, -4.0]  # metres
net.junction_geodata.loc[return_junctions, ["x", "y"]] = \
    net.junction_geodata.loc[partners, ["x", "y"]].values + shift
is_return_pipe = net.pipe.from_junction.isin(return_junctions)
net.pipe_geodata.loc[is_return_pipe, "coords"] = net.pipe_geodata.loc[is_return_pipe, "coords"].apply(
    lambda coords: [[x + shift[0], y + shift[1]] for x, y in coords])

convert_epsg_junction_geodata(net, epsg_in=31467, epsg_out=4326)
convert_epsg_pipe_geodata(net, epsg_in=31467, epsg_out=4326)

pp.pipeflow(net, mode="sequential", iter=100)
net.res_pipe["t_to_c"] = net.res_pipe["t_to_k"] - 273.15

res = net.res_pipe
flow = res.mdot_from_kg_per_s.abs() > 1e-9
print("supply pipes   T [C]:", res.t_to_c[flow & ~is_return_pipe].agg(["min", "mean", "max"]).round(1).tolist())
print("return pipes   T [C]:", res.t_to_c[flow & is_return_pipe].agg(["min", "mean", "max"]).round(1).tolist())
pump = net.res_circ_pump_pressure
print(pump.T)
print("consumers: total heat [MW]:", round(net.heat_consumer.qext_w.sum()/1e6,2), " return T [C] min/mean/max:",
      (net.res_heat_consumer.t_to_k-273.15).agg(["min","mean","max"]).round(1).tolist())
fig = create_map_figure(net, pipe_result="t_to_c", colorbar_title="Water temperature [°C]", height=800, map_style="carto-positron")
fig.write_html("/tmp/claude-0/-home-user-pandapipes/3d79387f-d522-5cd2-9024-da587cb1d882/scratchpad/heat_positron.html")
