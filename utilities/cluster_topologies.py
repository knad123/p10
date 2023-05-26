import json
import shutil

with open("topology_info.json", "r") as f:
    topo_info = json.load(f)

with open("total_packets_pr_second_info.json", "r") as f:
    packets_per_second = json.load(f)

white_list = []
white_list_cap = 10
for topo, info in topo_info.items():
    demand_name = topo[4:] + "_0000.yml"
    if info["num_nodes"] < 40 and info["num_nodes"] > 15 and packets_per_second[demand_name] > 50000 and packets_per_second[demand_name] < 500000:
        white_list.append(topo + ".json")
        if len(white_list) >= white_list_cap:
            break

for topo in white_list:
    shutil.copy("../topologies/"+topo, "../experiments/frr_test/"+topo)