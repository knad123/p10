import networkx as nx

class MPLS_Router:
    def __init__(self, name):
        self.name = name # Name
        self.forwarding_table = {} # 12 -> {'incoming_label': 12, 'outgoing_label': 12, 'next_hop': Randers, 'operation': swap}
        self.classification_table = {}

    # Add new forwarding rule
    def add_rule(self, incoming_label, outgoing_label, next_hop):
        # Pop operation
        if outgoing_label is None:
            operation = 'pop'
        # Swap operation
        else:
            operation = 'swap'

        rule = {'incoming_label': incoming_label, 'outgoing_label': outgoing_label, 'next_hop': next_hop, 'operation': operation}
        self.forwarding_table[incoming_label] = rule

    # Update rule in forwarding table
    def update_rule(self, incoming_label, outgoing_label, next_hop):
        if incoming_label in self.forwarding_table:
            rule = self.forwarding_table[incoming_label]
            rule['outgoing_label'] = outgoing_label
            rule['next_hop'] = next_hop

    # Remove rule
    def remove_rule(self, incoming_label):
        if incoming_label in self.forwarding_table:
            del self.forwarding_table[incoming_label]

    # Add new classification rule
    def add_classification_rule(self, target, incoming_label):
        self.classification_table[target] = incoming_label

    # Remove classification rule
    def remove_classification_rule(self, target):
        if target in self.classification_table:
            del self.classification_table[target]
