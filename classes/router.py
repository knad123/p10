import networkx as nx
from typing import Any, Dict, List, Union

class MPLS_Router:
    def __init__(self, name: str):
        self.name = name # Name
        self.forwarding_table = {} # 12 -> {'incoming_label': 12, 'outgoing_label': 12, 'next_hop': Randers, 'operation': swap}
        self.classification_table = {}

    # Add new forwarding rule
    def add_rule(self, incoming_label: int, outgoing_label: int, next_hop: str, priority: int, protection = False):
        # Pop operation
        if outgoing_label is None:
            operation = 'pop'
        # Push operation
        elif incoming_label is None or protection:
            operation = 'push'
        # Swap operation
        else:
            operation = 'swap'

        rule = {'incoming_label': incoming_label, 'outgoing_label': outgoing_label, 'next_hop': next_hop, 'operation': operation, 'priority': priority}
        if incoming_label not in self.forwarding_table:
            self.forwarding_table[incoming_label] = {}
        self.forwarding_table[incoming_label][priority, next_hop] = rule

    # Update rule in forwarding table
    def update_rule(self, incoming_label: int, outgoing_label: int, next_hop: str, priority: int):
        if incoming_label in self.forwarding_table:
            rule = self.forwarding_table[incoming_label, priority]
            rule['outgoing_label'] = outgoing_label
            rule['next_hop'] = next_hop
            rule['priority'] = priority

    # Remove rule
    def remove_rule(self, incoming_label: int):
        if incoming_label in self.forwarding_table:
            del self.forwarding_table[incoming_label]

    # Add new classification rule
    def add_classification_rule(self, target: str, incoming_label: int):
        self.classification_table[target] = incoming_label

    def add_classification_rule_for_weight_split_essence(self, source, target, id, source_host: str, target_host: str, incoming_label: int, weight = 1):
        self.classification_table[source, target, incoming_label] = (weight, source_host, target_host, id)

    # Remove classification rule
    def remove_classification_rule(self, target: str):
        if target in self.classification_table:
            del self.classification_table[target]
