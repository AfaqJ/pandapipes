"""Demo for the PR screenshot: a network with no pressure reference fails to converge."""
import pandapipes as pp
import pandapipes.explain

pandapipes.explain.enable()          # model defaults to llama3.1:8b; see the note below for a smaller one

net = pp.create_empty_network(fluid="water")
j0 = pp.create_junction(net, pn_bar=5, tfluid_k=293.15)
j1 = pp.create_junction(net, pn_bar=5, tfluid_k=293.15)
pp.create_pipe_from_parameters(net, j0, j1, length_km=1, inner_diameter_mm=100)
pp.create_sink(net, junction=j1, mdot_kg_per_s=1)   # note: no ext_grid, so no pressure reference

pp.pipeflow(net)
