import json
import os
import shutil
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--output_dir", type=str)
parser.add_argument("--num_topologies", type=int)
parser.add_argument("--topology_size", choices=["small", "medium", "large", "huge"])
parser.add_argument("--traffic_rate", choices=["slow", "medium", "fast"])

args = parser.parse_args()

os.makedirs(args.output_dir, exist_ok=True)

os.system(f"rm -rf {args.output_dir}/*")

with open("topology_info.json", "r") as f:
    topo_info = json.load(f)

with open("total_packets_pr_second_info.json", "r") as f:
    packets_per_second = json.load(f)

for topo in topo_info.keys():
    demand_name = topo[4:] + "_0000.yml"
    topo_info[topo]["demand"] = packets_per_second[demand_name]

all_topologies = topo_info.items()
if args.topology_size == "small":
    all_topologies = list(filter(lambda x: x[1]["num_nodes"] < 25, all_topologies))
elif args.topology_size == "medium":
    all_topologies = list(filter(lambda x: x[1]["num_nodes"] > 25 and x[1]["num_nodes"] < 45, all_topologies))
elif args.topology_size == "large":
    all_topologies = list(filter(lambda x: x[1]["num_nodes"] > 45 and x[1]["num_nodes"] < 85, all_topologies))
elif args.topology_size == "huge":
    all_topologies = list(filter(lambda x: x[1]["num_nodes"] > 85, all_topologies))

if args.traffic_rate == "slow":
    all_topologies = list(filter(lambda x: x[1]["demand"] > 5000 and x[1]["demand"] < 30000, all_topologies))
elif args.traffic_rate == "medium":
    all_topologies = list(filter(lambda x: x[1]["demand"] > 30000 and x[1]["demand"] < 400000, all_topologies))
elif args.traffic_rate == "fast":
    all_topologies = list(filter(lambda x: x[1]["demand"] > 400000, all_topologies))

all_topologies = all_topologies[:args.num_topologies]
white_list = [x[0] + ".json" for x in all_topologies]
for topo in white_list:
    shutil.copy(os.path.join("../topologies", topo), os.path.join(args.output_dir, topo))