import json
import os
import shutil
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--output_dir", type=str)
parser.add_argument("--num_topologies", type=int)
parser.add_argument("--topology_size", choices=["small", "medium", "large", "huge"])

args = parser.parse_args()

os.makedirs(args.output_dir, exist_ok=True)

os.system(f"rm -rf {args.output_dir}/*")

with open("topology_info.json", "r") as f:
    topo_info = json.load(f)

for topo in topo_info.keys():
    demand_name = topo[4:] + "_0000.yml"

all_topologies = topo_info.items()
if args.topology_size == "small":
    all_topologies = list(filter(lambda x: x[1]["num_nodes"] < 25, all_topologies))
elif args.topology_size == "medium":
    all_topologies = list(filter(lambda x: x[1]["num_nodes"] > 25 and x[1]["num_nodes"] < 45, all_topologies))
elif args.topology_size == "large":
    all_topologies = list(filter(lambda x: x[1]["num_nodes"] > 45 and x[1]["num_nodes"] < 85, all_topologies))
elif args.topology_size == "huge":
    all_topologies = list(filter(lambda x: x[1]["num_nodes"] > 85, all_topologies))

all_topologies = all_topologies[:args.num_topologies]
white_list = [x[0] + ".json" for x in all_topologies]
for topo in white_list:
    shutil.copy(os.path.join("../scaled_topologies", topo), os.path.join(args.output_dir, topo))