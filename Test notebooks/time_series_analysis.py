import pandapipes as pp
import pandapower as ppw
import pandas as pd
import numpy as np
import tempfile
import logging
import os
import matplotlib.pyplot as plt

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

# Create empty network with water as fluid
net = pp.create_empty_network(fluid="water")

# Create junctions (all start at 20°C)
j0 = pp.create_junction(net, pn_bar=1, tfluid_k=293.15, name="j0")
j1 = pp.create_junction(net, pn_bar=1, tfluid_k=293.15, name="j1")
j2 = pp.create_junction(net, pn_bar=1, tfluid_k=293.15, name="j2")
j3 = pp.create_junction(net, pn_bar=1, tfluid_k=293.15, name="j3")
j4 = pp.create_junction(net, pn_bar=1, tfluid_k=293.15, name="j4")

# Create pipes forming a loop
pipes = [
    pp.create_pipe_from_parameters(net, from_junction=j0, to_junction=j1, length_km=1, diameter_m=0.1, name="Pipe 0-1"),
    pp.create_pipe_from_parameters(net, from_junction=j1, to_junction=j2, length_km=1, diameter_m=0.1, name="Pipe 1-2"),
    pp.create_pipe_from_parameters(net, from_junction=j2, to_junction=j3, length_km=1, diameter_m=0.1, name="Pipe 2-3"),
    pp.create_pipe_from_parameters(net, from_junction=j3, to_junction=j4, length_km=1, diameter_m=0.1, name="Pipe 3-4"),
    pp.create_pipe_from_parameters(net, from_junction=j4, to_junction=j0, length_km=1, diameter_m=0.1, name="Pipe 4-0")
]

# Create circulation pump (80°C supply temperature)
pp.create_circ_pump_const_pressure(net, 
                                 return_junction=j0, 
                                 flow_junction=j1, 
                                 p_flow_bar=5, 
                                 plift_bar=0.7, 
                                 t_flow_k=273.15 + 80)

# Create heat consumers with proper heat extraction (negative qext_w)
consumers = [
    pp.create_heat_consumer(
        net,
        from_junction=j1,
        to_junction=j2,
        diameter_m=0.1,
        controlled_mdot_kg_per_s=1.0,  # Increased flow rate for better heat transfer
        qext_w=-100000,  # Negative value for heat extraction
        name="Consumer 1"
    ),
    pp.create_heat_consumer(
        net,
        from_junction=j3,
        to_junction=j4,
        diameter_m=0.1,
        controlled_mdot_kg_per_s=1.0,  # Increased flow rate for better heat transfer
        qext_w=-100000,  # Negative value for heat extraction
        name="Consumer 2"
    )
]

# Time series setup
time_steps = 24
time = pd.date_range('2024-01-01', periods=time_steps, freq='h')

# Create heat demand profiles with proper negative values for heat extraction
consumer1_qext_profile = pd.Series(
    [-1 * (100000 + 50000 * np.sin(2 * np.pi * t / time_steps)) 
     for t in range(time_steps)], 
    index=time
)

consumer2_qext_profile = pd.Series(
    [-1 * (120000 + 40000 * np.cos(2 * np.pi * t / time_steps)) 
     for t in range(time_steps)], 
    index=time
)

# Create DFData class for time series data handling
class DFData:
    def __init__(self, data):
        self.data = data
    
    def get_time_step_value(self, time_step, profile_name=None, scale_factor=1.0):
        value = self.data.iloc[time_step]
        return value * scale_factor
    
    def get_time_steps_len(self):
        return len(self.data)

# Set up profiles
profiles = {
    "consumer1": DFData(consumer1_qext_profile),
    "consumer2": DFData(consumer2_qext_profile)
}

# Create controllers
from pandapower.control import ConstControl

controllers = [
    ConstControl(
        net,
        element='heat_consumer',
        variable='qext_w',
        element_index=[0],
        profile_name='consumer1',
        data_source=profiles['consumer1']
    ),
    ConstControl(
        net,
        element='heat_consumer',
        variable='qext_w',
        element_index=[1],
        profile_name='consumer2',
        data_source=profiles['consumer2']
    )
]

# Create output directory
output_dir = os.path.join(os.getcwd(), "simulation_results")
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Initialize output_writer DataFrame in net
if "output_writer" not in net:
    net["output_writer"] = pd.DataFrame(columns=["object"])
    net.output_writer.loc[0, "object"] = None

# Import necessary output writer components
from pandapower.timeseries.output_writer import OutputWriter
from pandapipes.timeseries import init_default_outputwriter

def custom_init_default_outputwriter(net, time_steps, **kwargs):
    output_writer = kwargs.get("output_writer", None)
    if output_writer is not None:
        net.output_writer.iat[0, 0] = output_writer
    if "output_writer" not in net or net.output_writer.iat[0, 0] is None:
        ow = OutputWriter(net, time_steps, output_path=tempfile.gettempdir(), log_variables=[])

        # Define a mapping of network components to result variables
        component_to_variables = {
            'sink': [('res_sink', 'mdot_kg_per_s')],
            'source': [('res_source', 'mdot_kg_per_s')],
            'ext_grid': [('res_ext_grid', 'mdot_kg_per_s')],
            'pipe': [('res_pipe', 'v_mean_m_per_s'),
                     ('res_pipe', 't_from_k'),
                     ('res_pipe', 't_to_k')],
            'junction': [('res_junction', 'p_bar'),
                         ('res_junction', 't_k')],
            'heat_consumer': [('heat_consumer', 'qext_w')]
        }

        # Iterate through the mapping and log variables for existing components
        for component, variables in component_to_variables.items():
            if hasattr(net, component):  # Check if the component exists in the network
                for var, value in variables:
                    ow.log_variable(var, value)

        logger.info("No output writer specified. Using default:")
        logger.info(ow)
        logger.info("Using custom output writer configuration.")
    return net.output_writer.iat[0, 0]

# Initialize the output writer with custom configuration
output_path = os.path.join(output_dir, "simulation_results.csv")
ow = custom_init_default_outputwriter(net, time_steps, output_path=output_path)

# Run time series simulation
print("\nRunning time series simulation...")
pp.timeseries.run_timeseries(net, 
                            time_steps=list(range(time_steps)), 
                            continue_on_divergence=True,
                            mode="sequential",  # Using sequential mode for proper thermal calculations
                            verbose=True)
print("Simulation completed!")

# Get results from output writer
output_data = {}
for key, value in net.output_writer.iat[0, 0].output.items():
    output_data[key] = value
    print(f"Available key: {key}")  # Debug print to see available keys

# Save results to Excel
output_path = os.path.join(output_dir, "simulation_results.xlsx")
with pd.ExcelWriter(output_path) as writer:
    for key, df in output_data.items():
        sheet_name = str(key).replace('.', '_')[:31]
        df.to_excel(writer, sheet_name=sheet_name)

print(f"\nResults saved to: {output_path}")

# Create visualizations
plt.style.use('seaborn-v0_8')

# 1. Temperature Distribution Plot
plt.figure(figsize=(12, 6))
temps = output_data['res_junction.t_k'] - 273.15  # Convert to Celsius
pipe_temps_from = output_data['res_pipe.t_from_k'] - 273.15
pipe_temps_to = output_data['res_pipe.t_to_k'] - 273.15

# Plot junction temperatures
plt.subplot(2, 1, 1)
for i, name in enumerate(['Pump Out', 'HX1 In', 'HX1 Out', 'HX2 In', 'HX2 Out']):
    plt.plot(time, temps.iloc[:, i], '-o', label=name, markersize=4)

plt.title('Junction Temperatures', fontsize=12)
plt.ylabel('Temperature [°C]')
plt.grid(True, alpha=0.3)
plt.legend()

# Plot pipe temperatures
plt.subplot(2, 1, 2)
for i, name in enumerate(['Pipe 0-1', 'Pipe 1-2', 'Pipe 2-3', 'Pipe 3-4', 'Pipe 4-0']):
    plt.plot(time, pipe_temps_from.iloc[:, i], '--', label=f'{name} (From)', alpha=0.7)
    plt.plot(time, pipe_temps_to.iloc[:, i], '-', label=f'{name} (To)', alpha=0.7)

plt.title('Pipe Temperatures (From/To)', fontsize=12)
plt.xlabel('Time')
plt.ylabel('Temperature [°C]')
plt.grid(True, alpha=0.3)
plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
plt.tight_layout()
plt.savefig(os.path.join(output_dir, 'temperature_distribution.png'), dpi=300, bbox_inches='tight')
plt.show()

# 2. Heat Demand Plot
plt.figure(figsize=(12, 6))
heat_demand1 = -output_data['heat_consumer.qext_w'].iloc[:, 0] / 1000  # Convert to kW
heat_demand2 = -output_data['heat_consumer.qext_w'].iloc[:, 1] / 1000  # Convert to kW

plt.plot(time, heat_demand1, '-o', label='Consumer 1', markersize=4)
plt.plot(time, heat_demand2, '-o', label='Consumer 2', markersize=4)
plt.title('Heat Demand Over Time', fontsize=12, pad=20)
plt.xlabel('Time')
plt.ylabel('Heat Demand [kW]')
plt.grid(True, alpha=0.3)
plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
plt.tight_layout()
plt.savefig(os.path.join(output_dir, 'heat_demand.png'), dpi=300, bbox_inches='tight')
plt.show()

# 3. Pressure Distribution Plot
plt.figure(figsize=(12, 6))
pressures = output_data['res_junction.p_bar']
for i, name in enumerate(['Pump Out', 'HX1 In', 'HX2 In', 'Pump In']):
    plt.plot(time, pressures.iloc[:, i], '-o', label=name, markersize=4)

plt.title('Pressure Distribution in Network', fontsize=12, pad=20)
plt.xlabel('Time')
plt.ylabel('Pressure [bar]')
plt.grid(True, alpha=0.3)
plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
plt.tight_layout()
plt.savefig(os.path.join(output_dir, 'pressure_distribution.png'), dpi=300, bbox_inches='tight')
plt.show()

# 4. Flow Velocity Plot
plt.figure(figsize=(12, 6))
velocities = output_data['res_pipe.v_mean_m_per_s']
for i, name in enumerate(['Pipe 0-1', 'Pipe 1-2', 'Pipe 2-3', 'Pipe 3-4', 'Pipe 4-0']):
    plt.plot(time, velocities.iloc[:, i], '-o', label=name, markersize=4)

plt.title('Flow Velocities in Pipes', fontsize=12, pad=20)
plt.xlabel('Time')
plt.ylabel('Velocity [m/s]')
plt.grid(True, alpha=0.3)
plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
plt.tight_layout()
plt.savefig(os.path.join(output_dir, 'flow_velocities.png'), dpi=300, bbox_inches='tight')
plt.show()

# Print summary statistics
print("\nSimulation Summary:")
print(f"Average Supply Temperature: {temps.iloc[:, 0].mean():.1f}°C")
print(f"Average Return Temperature: {temps.iloc[:, -1].mean():.1f}°C")
print(f"Average Heat Demand (Consumer 1): {heat_demand1.mean():.1f} kW")
print(f"Average Heat Demand (Consumer 2): {heat_demand2.mean():.1f} kW")
print(f"Peak Heat Demand (Consumer 1): {heat_demand1.max():.1f} kW")
print(f"Peak Heat Demand (Consumer 2): {heat_demand2.max():.1f} kW")
print(f"Average Flow Velocity: {velocities.abs().mean().mean():.2f} m/s") 