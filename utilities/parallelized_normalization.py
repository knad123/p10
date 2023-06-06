import json
import os
import shutil
import yaml
import concurrent.futures

def scale_down_network(dictionary, average_capacity):
    # Calculate the scaling factor for link bandwidth
    total_bandwidth = sum(link['bandwidth'] for link in dictionary['network']['links'])
    scaling_factor = total_bandwidth / (len(dictionary['network']['links']) * average_capacity)

    # Scale down link bandwidth
    for link in dictionary['network']['links']:
        link['bandwidth'] = int(link['bandwidth'] / scaling_factor)

    return dictionary, scaling_factor

demands = "../scaled_demands"
topo = "../scaled_topologies"

if os.path.exists(demands):
    shutil.rmtree(demands)
os.mkdir(demands)

if os.path.exists(topo):
    shutil.rmtree(topo)
os.mkdir(topo)

def process_topology(topology_file):
    with open(topology_file, "r") as f:
        topology_info = json.load(f)

    total_bandwidth = 0
    for link in topology_info['network']['links']:
        total_bandwidth += link['bandwidth']

    dictionary, scaling_factor = scale_down_network(topology_info, 500000)

    topology_name = os.path.basename(topology_file).split(".json")[0]
    scaled_topology_file = os.path.join(topo, os.path.basename(topology_file))
    with open(scaled_topology_file, "w") as topo_file:
        json.dump(dictionary, topo_file)

    return topology_name, scaling_factor

def process_demand(demand_file, scaling_factor):
    demand_name = os.path.basename(demand_file).split("_")[0]
    topology_name = demand_name.split(".json")[0]
    if demand_name == topology_name:
        output = os.path.join(demands, os.path.basename(demand_file))
        with open(demand_file, "r") as file:
            flows_with_load = []
            for (x, y, z) in yaml.load(file, Loader=yaml.BaseLoader):
                flows_with_load.append([x, y, int(z)])
        updated_flows = []
        for (src, tgt, load) in flows_with_load:
            updated_flows.append([src, tgt, int(load / scaling_factor)])
        with open(output, "w") as o:
            o.write(str(updated_flows))

# Process topologies in parallel
topology_files = [os.path.join("../topologies", file) for file in os.listdir("../topologies")]

with concurrent.futures.ThreadPoolExecutor() as executor:
    results = executor.map(process_topology, topology_files)

scaling_factors = {}
for topology_name, scaling_factor in results:
    scaling_factors[topology_name] = scaling_factor

# Process demands in parallel
demand_files = [os.path.join("../demands", file) for file in os.listdir("../demands")]

with concurrent.futures.ThreadPoolExecutor() as executor:
    executor.map(process_demand, demand_files, scaling_factors.values())
