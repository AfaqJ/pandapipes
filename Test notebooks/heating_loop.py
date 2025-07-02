import pandapipes as pp
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.colors
import numpy as np

# ----------------------------
# 1. create closed-loop network
# ----------------------------
net = pp.create_empty_network(fluid="water", name="Simple Loop – 2 Consumers")

# Junctions (all start at 20 °C, 3 bar nominal)
j0 = pp.create_junction(net, pn_bar=3, tfluid_k=293.15, name="Pump Discharge")
j1 = pp.create_junction(net, pn_bar=3, tfluid_k=293.15, name="Consumer 1 In")
j2 = pp.create_junction(net, pn_bar=3, tfluid_k=293.15, name="Consumer 2 In")
j3 = pp.create_junction(net, pn_bar=3, tfluid_k=293.15, name="Pump Return")

# Forward pipe: j0 → j1
pp.create_pipe_from_parameters(
    net, j0, j1,
    length_km=0.05, diameter_m=0.08, k_mm=0.03,
    sections=4, name="Pipe A"
)

# Heat Exchanger 1 (10 kW): j1 → j2
pp.create_heat_exchanger(
    net,
    from_junction=j1, to_junction=j2,
    qext_w=10_000,             # 10 kW extracted
    diameter_m=0.08,
    length_km=0.01,
    sections=2,
    name="HX 1 (10 kW)"
)

# Heat Exchanger 2 (20 kW): j2 → j3
pp.create_heat_exchanger(
    net,
    from_junction=j2, to_junction=j3,
    qext_w=20_000,             # 20 kW extracted
    diameter_m=0.08,
    length_km=0.01,
    sections=2,
    name="HX 2 (20 kW)"
)

# Short return pipe (cool line): j3 → j0 is handled by the pump itself
pp.create_circ_pump_const_mass_flow(
    net,
    return_junction=j3,        # suction
    flow_junction=j0,          # discharge
    mdot_flow_kg_per_s=0.10,   # 0.10 kg/s
    p_flow_bar=3.5,            # adds ≈0.5 bar head
    t_flow_k=353.15,           # re-heat to 80 °C
    type="pt",                 # fixes P & T at j0
    name="Loop Pump"
)

# ----------------------------
# 2. static pipe-flow (steady)
# ----------------------------
pp.pipeflow(
    net,
    mode="sequential",          # use sequential instead of "all"
    friction_model="swamee-jain"
)

# Print results
print("\nJunction Results (Pressure and Temperature):")
print(net.res_junction[['p_bar', 't_k']])

print("\nPipe Results:")
if hasattr(net, 'res_pipe') and not net.res_pipe.empty:
    print("\nPipe Flow Results:")
    print(net.res_pipe[['v_mean_m_per_s', 'p_from_bar', 'p_to_bar', 't_from_k', 't_to_k']])

print("\nHeat Exchanger Results:")
if hasattr(net, 'res_heat_exchanger') and not net.res_heat_exchanger.empty:
    print(net.res_heat_exchanger[['p_from_bar', 'p_to_bar', 't_from_k', 't_to_k', 'vdot_m3_per_s']])

print("\nCirculation Pump Results:")
if hasattr(net, 'res_circ_pump_mass') and not net.res_circ_pump_mass.empty:
    print(net.res_circ_pump_mass)

# ----------------------------
# 3. Plot network
# ----------------------------
# Create temperature colormap (blue=cold to red=hot)
temp_colors = LinearSegmentedColormap.from_list('temp_colors', ['blue', 'yellow', 'red'])

# Get temperature range for coloring and extend it slightly for better spread
junction_temps = net.res_junction['t_k']
temp_min = junction_temps.min() - 5  # Extend range by 5K on each end
temp_max = junction_temps.max() + 5
temp_range = (temp_min, temp_max)

# Create figure
fig, ax = plt.subplots(figsize=(8, 6))  # Reduced figure size

# Plot network with temperature-based colors
collections = pp.plotting.simple_plot(net,
    ax=ax,
    plot_sinks=True,
    plot_sources=True,
    junction_size=1.5,     # Reduced from 3.0
    pipe_width=2.0,       # Reduced from 4.0
    heat_exchanger_size=1.5,  # Reduced from 3.0
    pump_size=1.5,        # Reduced from 3.0
    junction_color='lightblue',
    pipe_color='red',
    heat_exchanger_color='blue',
    circ_pump_mass_color='red',
    show_plot=False
)

# Wait for coordinates to be generated
if not hasattr(net, 'junction_geodata'):
    print("Waiting for coordinate generation...")
    plt.pause(1)

# Add temperature annotations to junctions
if hasattr(net, 'junction_geodata'):
    for idx in net.junction.index:
        temp = net.res_junction.at[idx, 't_k']
        temp_c = temp - 273.15  # Convert to Celsius
        x = net.junction_geodata.at[idx, 'x']
        y = net.junction_geodata.at[idx, 'y']
        ax.annotate(f'{temp_c:.1f}°C', 
                    xy=(x, y),
                    xytext=(5, 5),
                    textcoords='offset points',
                    fontsize=8,
                    bbox=dict(facecolor='white', edgecolor='none', alpha=0.7))

ax.set_title("Temperature Distribution")

# Add colorbar with temperature range in Celsius
sm = plt.cm.ScalarMappable(cmap=temp_colors)
sm.set_array([])
cbar = plt.colorbar(sm, ax=ax)
cbar.set_label('Temperature [°C]')
# Convert Kelvin temperatures to Celsius for colorbar
temp_points = [temp_min, (temp_min + temp_max)/2, temp_max]
temp_labels = [f"{(t - 273.15):.1f}°C" for t in temp_points]
cbar.set_ticks([0, 0.5, 1])
cbar.set_ticklabels(temp_labels)

plt.tight_layout()
plt.show()

# Add result plots
fig_results, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 12))

# 1. Temperature Profile
junction_names = ['Pump Out', 'HX1 In', 'HX2 In', 'Pump In']
temps_c = net.res_junction['t_k'] - 273.15  # Convert to Celsius

ax1.plot(range(len(temps_c)), temps_c, 'ro-', linewidth=2)
ax1.set_xticks(range(len(temps_c)))
ax1.set_xticklabels(junction_names, rotation=45)
ax1.set_ylabel('Temperature [°C]')
ax1.set_title('Temperature Profile Across System')
ax1.grid(True)

# Add temperature drops at heat exchangers
for i in range(len(temps_c)-1):
    temp_drop = temps_c.iloc[i] - temps_c.iloc[i+1]
    if temp_drop > 0:  # Only annotate significant drops (heat exchangers)
        ax1.annotate(f'-{temp_drop:.1f}°C',
                    xy=((i + i+1)/2, (temps_c.iloc[i] + temps_c.iloc[i+1])/2),
                    xytext=(10, 10),
                    textcoords='offset points',
                    ha='left',
                    bbox=dict(facecolor='white', edgecolor='none', alpha=0.7))

# 2. Pressure Profile
pressures = net.res_junction['p_bar']

ax2.plot(range(len(pressures)), pressures, 'bs-', linewidth=2)
ax2.set_xticks(range(len(pressures)))
ax2.set_xticklabels(junction_names, rotation=45)
ax2.set_ylabel('Pressure [bar]')
ax2.set_title('Pressure Profile Across System')
ax2.grid(True)

# 3. Flow Rates
components = ['Pipe', 'HX1', 'HX2', 'Pump']
flow_rates = []

# Collect flow rates from different components
if hasattr(net, 'res_pipe') and not net.res_pipe.empty:
    flow_rates.append(net.res_pipe['v_mean_m_per_s'].iloc[0])
else:
    flow_rates.append(0)

if hasattr(net, 'res_heat_exchanger') and not net.res_heat_exchanger.empty:
    # Convert volumetric flow rates to velocity for consistency
    for _, hx in net.res_heat_exchanger.iterrows():
        flow_rates.append(hx['vdot_m3_per_s'] / (np.pi * (0.08/2)**2))  # Using pipe diameter of 0.08m

if hasattr(net, 'res_circ_pump_mass') and not net.res_circ_pump_mass.empty:
    flow_rates.append(net.res_circ_pump_mass['vdot_m3_per_s'].iloc[0] / (np.pi * (0.08/2)**2))

ax3.bar(components, flow_rates, color=['gray', 'blue', 'blue', 'red'])
ax3.set_ylabel('Flow Velocity [m/s]')
ax3.set_title('Flow Velocities in Components')
ax3.grid(True)

# Add heat exchanger power annotations
if hasattr(net, 'heat_exchanger') and not net.heat_exchanger.empty:
    for i, (_, hx) in enumerate(net.heat_exchanger.iterrows(), start=1):
        ax3.annotate(f'{hx["qext_w"]/1000:.1f} kW',
                    xy=(f'HX{i}', 0),
                    xytext=(0, 10),
                    textcoords='offset points',
                    ha='center')

plt.tight_layout()
plt.show() 