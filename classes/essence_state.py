import networkx as nx
from networkx import shortest_path

from classes.network import MLPS_Network
import concurrent.futures
import os


class EssenceState:
    def __init__(self, network: MLPS_Network):
        self.pathdict = dict()
        self.stretchdict = dict()
        self.current_population = []
        self.congestion_weight = 1

    def create_stretchdict(self, network: MLPS_Network):
        shortest_paths_len = dict()
        stretch_dict = {}

        for src, tgt in network.demands.keys():
            shortest_paths_len[(src, tgt)] = len(shortest_path(network.topology, src, tgt))

        # Create stretch dictionary, so it does not have to be recomputed in the genetic algorithm
        for src, tgt in network.demands.keys():
            # Calculate the stretch value for each path between the source and destination
            for path in self.pathdict[src, tgt]:
                path_tuple = tuple(path)
                path_len = len(path)
                stretch_dict[path_tuple] = (path_len / shortest_paths_len[src, tgt])

        self.stretchdict = stretch_dict

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

        self.pathdict = pathdict


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