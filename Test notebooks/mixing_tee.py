import pandapipes as pp
import pandapower as ppw
import pandas as pd
import numpy as np
import tempfile
import logging
import os
from pandapower.timeseries.output_writer import OutputWriter
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

# Create empty network with water as fluid
net = pp.create_empty_network(fluid="water")

# Create junctions with geodata for mixing tee configuration
j0 = pp.create_junction(net, pn_bar=5.0, tfluid_k=293.15, name="j0", geodata=(0, 0))    # Return point
j1 = pp.create_junction(net, pn_bar=6.0, tfluid_k=358.15, name="j1", geodata=(2, 1))    # Boiler 1 supply (85°C)
j2 = pp.create_junction(net, pn_bar=5.5, tfluid_k=348.15, name="j2", geodata=(2, -1))   # Boiler 2 supply (75°C)
j3 = pp.create_junction(net, pn_bar=5.8, tfluid_k=353.15, name="j3", geodata=(1, 0))    # Mixing point
j4 = pp.create_junction(net, pn_bar=5.2, tfluid_k=333.15, name="j4", geodata=(3, 0))    # Consumer point

# Add external grid as reference point
pp.create_ext_grid(net, junction=j0, p_bar=5.0, t_k=293.15, type="pt")

# Create pipes connecting the junctions with different diameters for better flow control
pp.create_pipe_from_parameters(net, from_junction=j3, to_junction=j0, length_km=0.1, diameter_m=0.15, name="Common Return")
pp.create_pipe_from_parameters(net, from_junction=j1, to_junction=j3, length_km=0.05, diameter_m=0.1, name="Boiler 1 Line")
pp.create_pipe_from_parameters(net, from_junction=j2, to_junction=j3, length_km=0.05, diameter_m=0.1, name="Boiler 2 Line")
pp.create_pipe_from_parameters(net, from_junction=j3, to_junction=j4, length_km=0.1, diameter_m=0.15, name="Supply Line")

# Create sources at boiler points with fixed mass flow and temperature
pp.create_source(net, 
                junction=j1,
                mdot_kg_per_s=0.3,  # 0.3 kg/s base flow
                name="Boiler 1")

pp.create_source(net,
                junction=j2,
                mdot_kg_per_s=0.2,  # 0.2 kg/s base flow
                name="Boiler 2")

# Create heat consumer with temperature control
pp.create_heat_consumer(
    net,
    from_junction=j3,
    to_junction=j4,
    diameter_m=0.15,
    qext_w=25000,  # 25 kW base load
    deltat_k=20,   # 20K temperature difference
    name="Main Consumer"
)

# Time series setup
time_steps = 24
time = pd.date_range('2024-01-01', periods=time_steps, freq='h')

# Create varying heat demand profile with minimum base load
consumer_profile = pd.Series(
    [25000 + 15000 * np.sin(2 * np.pi * t / time_steps) 
     for t in range(time_steps)], 
    index=time
)

# Create varying source flow profiles
source1_profile = pd.Series(
    [0.3 + 0.1 * np.sin(2 * np.pi * (t + 6) / 24) 
     for t in range(time_steps)],
    index=time
)

source2_profile = pd.Series(
    [0.2 + 0.05 * np.sin(2 * np.pi * t / 24 + np.pi) 
     for t in range(time_steps)],
    index=time
)

class DFData:
    def __init__(self, data):
        self.data = data
    
    def get_time_step_value(self, time_step, profile_name=None, scale_factor=1.0):
        value = self.data.iloc[time_step]
        return value * scale_factor

profiles = {
    "consumer": DFData(consumer_profile),
    "source1": DFData(source1_profile),
    "source2": DFData(source2_profile)
}

from pandapower.control import ConstControl
from pandapipes.timeseries.run_time_series import run_timeseries

# Set up controls
consumer_control = ConstControl(
    net,
    element='heat_consumer',
    variable='qext_w',
    element_index=[0],
    profile_name='consumer',
    data_source=profiles['consumer']
)

source1_control = ConstControl(
    net,
    element='source',
    variable='mdot_kg_per_s',
    element_index=[0],
    profile_name='source1',
    data_source=profiles['source1']
)

source2_control = ConstControl(
    net,
    element='source',
    variable='mdot_kg_per_s',
    element_index=[1],
    profile_name='source2',
    data_source=profiles['source2']
)

# Initialize output writer
from pandapipes.timeseries import init_default_outputwriter

output_path = "mixing_tee_results.xlsx"
ow = init_default_outputwriter(net, time_steps, output_path=output_path)

# Run simulation
print("\nRunning time series simulation...")
try:
    pp.timeseries.run_timeseries(net, 
                                time_steps=list(range(time_steps)), 
                                mode="sequential",
                                continue_on_divergence=True)
    print("Simulation completed successfully!")
except Exception as e:
    print(f"Simulation error: {str(e)}")
    print("\nAttempting single timestep simulation...")
    pp.pipeflow(net, mode="sequential")

# Collect results
output_data = {}
for key, value in net.output_writer.iat[0, 0].output.items():
    output_data[key] = value

# Save results
with pd.ExcelWriter(output_path) as writer:
    for key, df in output_data.items():
        df.to_excel(writer, sheet_name=key)

print(f"\nResults saved to: {output_path}")

# Create plots directory
if not os.path.exists('plots'):
    os.makedirs('plots')

# 1. Network visualization with temperatures
def plot_network_timestep(net, timestep, temperatures, velocities, ax=None):
    if ax is None:
        _, ax = plt.subplots(1, 1, figsize=(10, 8))
    
    # Create color maps
    temp_min = temperatures.min()
    temp_max = temperatures.max()
    
    # Map temperatures to colors (red=hot, blue=cold)
    junction_colors = []
    for temp in temperatures:
        normalized_temp = (temp - temp_min) / (temp_max - temp_min)
        junction_colors.append((normalized_temp, 0, 1-normalized_temp))
    
    # Plot network
    pp.plotting.simple_plot(
        net,
        plot_sinks=True,
        sink_size=1.0,
        junction_size=2.0,
        pipe_width=3.0,
        junction_color=junction_colors,
        ax=ax,
        show_plot=False
    )
    
    # Add temperature labels
    for i, (x, y) in enumerate(zip(net.junction_geodata.x, net.junction_geodata.y)):
        ax.annotate(f'{temperatures[i]:.1f}°C', 
                   (x, y), 
                   xytext=(10, 10),
                   textcoords='offset points')
    
    # Add velocity labels to pipes
    for i, (from_idx, to_idx) in enumerate(zip(net.pipe.from_junction, net.pipe.to_junction)):
        from_x = net.junction_geodata.x[from_idx]
        from_y = net.junction_geodata.y[from_idx]
        to_x = net.junction_geodata.x[to_idx]
        to_y = net.junction_geodata.y[to_idx]
        
        mid_x = (from_x + to_x) / 2
        mid_y = (from_y + to_y) / 2
        
        ax.annotate(f'{velocities[i]:.3f} m/s',
                   (mid_x, mid_y),
                   xytext=(0, 10),
                   textcoords='offset points',
                   ha='center')
    
    ax.set_title(f'Network State at Hour {timestep}')
    return ax

# Create visualization for multiple timesteps
fig, axes = plt.subplots(2, 3, figsize=(20, 12))
axes = axes.flatten()

# Select timesteps to plot
selected_timesteps = [0, 6, 12, 18, 23]

# Get temperature and velocity data
junction_temps = output_data['res_junction.t_k'] - 273.15
pipe_velocities = output_data['res_pipe.v_mean_m_per_s']

# Plot each timestep
for i, timestep in enumerate(selected_timesteps):
    plot_network_timestep(
        net, 
        timestep, 
        junction_temps.iloc[timestep], 
        pipe_velocities.iloc[timestep], 
        ax=axes[i]
    )

# Remove extra subplot
axes[-1].remove()

plt.tight_layout()
plt.savefig('plots/mixing_tee_network.png', dpi=300, bbox_inches='tight')
plt.show()

# 2. Temperature profiles over time
plt.figure(figsize=(12, 6))
for i, name in enumerate(['j0', 'j1', 'j2', 'j3', 'j4']):
    plt.plot(time, junction_temps.iloc[:, i], '-o', label=f'Junction {name}', markersize=4)

plt.title('Temperature Profiles Over Time')
plt.xlabel('Time')
plt.ylabel('Temperature [°C]')
plt.grid(True, alpha=0.3)
plt.legend()
plt.tight_layout()
plt.savefig('plots/mixing_temperatures.png', dpi=300, bbox_inches='tight')
plt.show()

# 3. Flow velocities over time
plt.figure(figsize=(12, 6))
for i, name in enumerate(['Common Return', 'Boiler 1 Line', 'Boiler 2 Line', 'Supply Line']):
    plt.plot(time, pipe_velocities.iloc[:, i], '-o', label=name, markersize=4)

plt.title('Flow Velocities Over Time')
plt.xlabel('Time')
plt.ylabel('Velocity [m/s]')
plt.grid(True, alpha=0.3)
plt.legend()
plt.tight_layout()
plt.savefig('plots/mixing_velocities.png', dpi=300, bbox_inches='tight')
plt.show()

# 4. Mixing analysis
print("\nMixing Analysis:")
print("\nAverage Temperatures:")
for i, name in enumerate(['Return (j0)', 'Boiler 1 (j1)', 'Boiler 2 (j2)', 'Mixed (j3)', 'Consumer (j4)']):
    avg_temp = junction_temps.iloc[:, i].mean()
    print(f"{name}: {avg_temp:.1f}°C")

# Calculate theoretical mixed temperature
def calculate_mixed_temperature(m1, T1, m2, T2):
    return (m1 * T1 + m2 * T2) / (m1 + m2)

# Get mass flows
mass_flows = output_data['res_pipe.v_mean_m_per_s'] * (np.pi * 0.1**2 / 4) * 1000  # m/s * area * density

print("\nFlow Contribution:")
boiler1_flow = abs(mass_flows.iloc[:, 1].mean())
boiler2_flow = abs(mass_flows.iloc[:, 2].mean())
total_flow = boiler1_flow + boiler2_flow

print(f"Boiler 1: {boiler1_flow:.2f} kg/s ({boiler1_flow/total_flow*100:.1f}%)")
print(f"Boiler 2: {boiler2_flow:.2f} kg/s ({boiler2_flow/total_flow*100:.1f}%)")

# Calculate theoretical mixed temperature
avg_T1 = junction_temps.iloc[:, 1].mean()  # Boiler 1
avg_T2 = junction_temps.iloc[:, 2].mean()  # Boiler 2
theoretical_mix = calculate_mixed_temperature(boiler1_flow, avg_T1, boiler2_flow, avg_T2)
actual_mix = junction_temps.iloc[:, 3].mean()  # j3 temperature

print(f"\nMixing Temperature Analysis:")
print(f"Theoretical Mixed Temperature: {theoretical_mix:.1f}°C")
print(f"Actual Mixed Temperature: {actual_mix:.1f}°C")
print(f"Difference: {abs(theoretical_mix - actual_mix):.1f}°C") 