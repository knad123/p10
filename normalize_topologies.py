import json
import os
import yaml


def scale_down_network(dictionary, average_capacity):
    # Calculate the scaling factor for link bandwidth
    total_bandwidth = sum(link['bandwidth'] for link in dictionary['network']['links'])
    scaling_factor = total_bandwidth / (len(dictionary['network']['links']) * average_capacity)

    # Scale down link bandwidth
    for link in dictionary['network']['links']:
        link['bandwidth'] = int(link['bandwidth'] / scaling_factor)

    return dictionary, scaling_factor

os.mkdir("scaled_topologies")
os.mkdir("scaled_demands")

for topology in os.listdir("topologies"):
    with open(os.path.join("topologies", topology), "r") as f:
        topology_info = json.load(f)

    total_bandwidth = 0
    for link in topology_info['network']['links']:
        total_bandwidth += link['bandwidth']

    dictionary, scaling_factor = scale_down_network(topology_info, 500000)

    with open(os.path.join("scaled_topologies", topology), "w") as topo:
        json.dump(dictionary, topo)

    topology_name = topology.split(".json")[0]
    topology_name = topology_name.split("_")[1]
    for demand in os.listdir("demands"):
        if demand.__contains__(topology_name):
            output = os.path.join("scaled_demands", demand)
            with open("/home/andreas/Documents/GitHub/p10/demands/" + demand, "r") as file:
                flows_with_load = []
                for (x,y,z) in yaml.load(file, Loader=yaml.BaseLoader):
                    flows_with_load.append([x,y, int(z)])
            updated_flows = []
            for (src,tgt,load) in flows_with_load:
                updated_flows.append([src,tgt,int(load/scaling_factor)])
            with open(output, "w") as o:
                o.write(str(updated_flows))