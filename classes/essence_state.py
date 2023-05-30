from typing import Tuple, List

import networkx
import networkx as nx
from networkx import shortest_path

from classes.network import MPLS_Network


class EssenceState:
    def __init__(self, network: MPLS_Network):
        self.pathdict = dict()
        self.stretchdict = dict()
        self.current_population = []
        self.congestion_weight = 1
        self.link_weights = {}


    def create_stretchdict(self, network: MPLS_Network):
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

    def create_pathdict(self, network: MPLS_Network):
        flow_to_graph = {f: network.topology for f in network.demands}
        for graph in flow_to_graph.values():
            for src, tgt in graph.edges:
                graph[src][tgt]["weight"] = 0

        input_data = [(src, tgt, flow_to_graph) for src, tgt in network.demands]
        results = list(map(find_paths_for_demand, input_data))

        pathdict = dict()
        for result, (src, tgt) in zip(results, network.demands):
            pathdict[(src, tgt)] = result

        self.pathdict = pathdict

    def all_shortest_path_pathdict(self, network: MPLS_Network):
        for src,tgt in network.demands.keys():
            self.pathdict[src,tgt] = list(networkx.all_shortest_paths(network.topology, src, tgt, weight=None))
    def create_shortest_path_pathdict(self, network: MPLS_Network):
        for src,tgt in network.demands.keys():
            self.pathdict[src,tgt] = find_paths_within_percentage_increase(network.topology, src, tgt, 0.2)

def find_paths_within_percentage_increase(graph, source, target, percentage_increase):
    shortest_path_length = nx.shortest_path_length(graph, source, target)
    max_path_length = shortest_path_length * (1 + percentage_increase)

    paths = []
    for path in nx.all_simple_paths(graph, source, target):
        path_length = len(path) - 1

        if path_length <= max_path_length:
            paths.append(path)

    return paths


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