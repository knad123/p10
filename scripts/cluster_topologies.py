import json
import shutil

with open("topology_info.json", "r") as f:
    topo_info = json.load(f)

with open("total_packets_pr_second_info.json", "r") as f:
    packets_per_second = json.load(f)

white_list = []
for topo, info in topo_info.items():
    demand_file = f"{topo.split('_')[1]}_0000.yml"
    topo_packets_per_second = packets_per_second[demand_file]
    if info["num_nodes"] < 100 and info["num_nodes"] > 20 and topo_packets_per_second < 300000 and topo_packets_per_second > 50000:
        white_list.append(topo + ".json")

for topo in white_list:
    shutil.copy("../topologies/"+topo, "../experiments/first_essence_experiments/topologies/"+topo)