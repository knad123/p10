import numpy as np

import networkx as nx
from collections import defaultdict
import os
import random
from itertools import islice, cycle, permutations
import itertools
from typing import Dict, Tuple, List, Callable

import time
from classes.network import MPLS_Network
from classes.essence_state import EssenceState

def CASA(network: MPLS_Network):
    mpls_topology = network.topology
    mpls_demands = network.demands

    matrix = generate_arborescences(mpls_topology)

    return matrix

def generate_arborescence(graph, root, length):
    arborescence = []
    visited = set()
    queue = [(root, None)]  # Keep track of the parent node in the queue

    while queue:
        node, parent = queue.pop(0)

        for neighbor in graph.neighbors(node):
            if neighbor != parent and neighbor not in visited and len(arborescence) < length:
                arborescence.append((node, neighbor))
                visited.add(neighbor)
                queue.append((neighbor, node))  # Add the parent-child relationship to the queue

        if len(arborescence) == length:
            break

    return arborescence

def generate_arborescences(mpls_graph):
    graph = nx.Graph(mpls_graph)
    nodes = list(graph.nodes)
    edges = list(graph.edges)
    num_nodes = len(nodes)
    num_edges = len(edges)
    arborescences = [[] for _ in range(num_nodes)]
    k = 10
    q = 4

    for _ in range(k):
        available_nodes = nodes.copy()
        random.shuffle(available_nodes)

        for i, node in enumerate(available_nodes):
            arb_length = random.randint(1, 4)
            arborescence = generate_arborescence(graph, node, arb_length)
            arborescences[i].append(arborescence)

    bibd_matrix = [[] for _ in range(num_nodes)]

    for i in range(num_nodes):
        for j in range(k):
            row = arborescences[i][j]
            bibd_matrix[i].append(row)

    return bibd_matrix


def is_link_disjoint(arborescence, mpls_graph, u, v):
    return arborescence[u] != v and arborescence[v] != u and not path_exists(arborescence, mpls_graph, u, v)

def path_exists(arborescence, u, v):
    return arborescence[v] == u or arborescence[u] == v or arborescence[u] == arborescence[v] or arborescence[v] == arborescence[arborescence[u]]

def generate_random_prime_power(start, end):
    prime_power = None
    while prime_power is None:
        prime = generate_random_prime(start, end)
        power = random.randint(2, 10)  # Adjust the power range as needed
        prime_power = prime ** power
    return prime_power

def generate_random_prime(start, end):
    prime = None
    while prime is None:
        num = random.randint(start, end)
        if is_prime(num):
            prime = num
    return prime

def is_prime(n):
    if n <= 1:
        return False
    if n == 2 or n == 3:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True

def is_prime_power(number):
    if number <= 1:
        return False

    # Find the largest possible exponent 'p'
    max_exponent = 2
    while max_exponent ** 2 <= number:
        max_exponent += 1

    # Check if the number is divisible by prime numbers up to the max exponent
    for prime in range(2, max_exponent):
        if is_prime(prime) and number % (prime ** get_exponent(number, prime)) == 0:
            return True

    return False

def get_exponent(number, prime):
    exponent = 0
    while number % prime == 0:
        exponent += 1
        number //= prime
    return exponent
