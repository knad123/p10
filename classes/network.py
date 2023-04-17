import networkx as nx

from classes.label_generator import MPLS_LabelGenerator
from classes.router import MPLS_Router

class MLPS_Network:
    def __init__(self):
        self.topology = nx.DiGraph()
        self.routers = {}
        self.label_generator = MPLS_LabelGenerator()

    def add_router(self, name):
        router = MPLS_Router(name=name)
        self.routers[name] = router

    def install_lsp(self, path):
        label = self.label_generator.get_new_label()

        for router_index in range(len(path) - 1):
            current_router = path[router_index]
            next_hop = path[router_index + 1]

            self.routers[current_router].add_rule(incoming_label=label, outgoing_label=label, next_hop=next_hop)