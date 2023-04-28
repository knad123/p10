import networkx as nx

from classes.network import MLPS_Network
import concurrent.futures
import os


class EssenceState:
    def __init__(self, network: MLPS_Network):
        self.pathdict = create_pathdict(self, network)
        self.current_population = []


def create_pathdict(self, network: MLPS_Network):
    flow_to_graph = {f: network.topology for f in network.demands}
    for graph in flow_to_graph.values():
        for src, tgt in graph.edges:
            graph[src][tgt]["weight"] = 0

    input_data = [(src, tgt, flow_to_graph) for src, tgt in network.demands]
    with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        results = list(executor.map(find_paths_for_demand, input_data))

    pathdict = dict()
    for result, (src, tgt) in zip(results, network.demands):
        pathdict[(src, tgt)] = result

    return pathdict


def find_paths_for_demand(args):
    src, tgt, flow_to_graph = args
    unique_paths = []
    paths = []
    while True:
        path = nx.shortest_path(flow_to_graph[(src, tgt)], src, tgt, weight="weight")
        for v1, v2 in zip(path[:-1], path[1:]):
            w = flow_to_graph[(src, tgt)][v1][v2]["weight"]
            w = w * 2 + 1
            flow_to_graph[(src, tgt)][v1][v2]["weight"] = w
        paths.append(path)
        if path not in unique_paths:
            unique_paths.append(path)
        if paths.count(path) == 3:
            paths = unique_paths
            break

    return paths
