import networkx as nx

class MPLS_Router:
    def __init__(self, name):
        self.name = name
        self.forwarding_table = {}

    # Add new forwarding rule
    def add_rule(self, incoming_label, outgoing_label, next_hop):
        self.forwarding_table[incoming_label] = (outgoing_label, next_hop)

    # Update rule in forwarding table
    def update_rule(self, incoming_label, outgoing_label, next_hop):
        if incoming_label in self.forwarding_table:
            self.forwarding_table[incoming_label] = (outgoing_label, next_hop)

    # Remove rule
    def remove_rule(self, incoming_label):
        if incoming_label in self.forwarding_table:
            del self.forwarding_table[incoming_label]