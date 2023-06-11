import concurrent.futures
import itertools
import math
import timeit

import networkx.exception
from functools import *
from networkx import shortest_path, diameter, shortest_simple_paths
import networkx as nx
from collections import defaultdict
import os
import random
from itertools import islice, cycle
import itertools
from typing import Dict, Tuple, List, Callable

import time
from classes.network import MPLS_Network


def SPUNGEET_split(network: MPLS_Network, conf, start_time, essence_state):
    genetic_weights = genetic_algorithm(network=network, loads=network.demands,
                                      capacities=nx.get_edge_attributes(network.topology, 'capacity'), conf=conf, start_time=start_time,
                                      time_limit=conf["update_interval"], essence_state=essence_state, weight_range=(len(network.demands.keys())*10))
    return genetic_weights


def genetic_algorithm(network, loads, capacities, conf, start_time, essence_state, generations=700,
                      population_size=200,
                      crossover_rate=0.9,
                      mutation_rate=0.7, time_limit=10, weight_range=1000):
    end_time = start_time + time_limit

    population = create_population(network, population_size, weight_range)

    # Run the genetic algorithm
    #for generation in range(generations):
    while time.time() < end_time:
        # Select parents
        a_class, b_class, c_class = selection(population, capacities, loads, network.topology, essence_state)
        #print(str(generation) + ": " + str(calculate_fitness(a_class[0], capacities, loads, network.topology)))
        # Generate the children
        # random_solutions = [{k: random.choice(v) for k, v in viable_paths.items()} for _ in range(int(population_size * 0.1))]
        children = a_class  # + random_solutions
        while len(children) < population_size:
            parent1 = random.choice(a_class)
            parent2 = random.choice(b_class + c_class)
            child = crossover(parent1, parent2)
            child = mutation(child, weight_range)
            children.extend([child])

        # Replace the population with the children
        population = children

    # Sort the population by fitness
    a_class, b_class, c_class = selection(population, capacities, loads, network.topology, essence_state)

    # Return the fittest individual

    weights = a_class[0]['demand_weights']

    demands_ordered = dict(sorted(weights.items(), key=lambda item: item[1], reverse=True))

    link_caps = capacities.copy()
    inverse_graph = essence_state.inverse_capacity_graph.to_directed().copy()

    pathdict = {}

    for (source, destination) in demands_ordered:
        load = loads[source, destination]
        pathdict[source,destination] = list(nx.all_shortest_paths(inverse_graph, source, destination, weight='weight'))

        longest_path_len = max([len(i) for i in pathdict[source,destination]]) - 1
        next_loads = {}
        for i in range(longest_path_len):

            # Find the number of splits and weights
            next_weights = {}
            next_hops = {}
            for path in pathdict[source,destination]:
                if i < len(path) - 1:
                    v1, v2 = path[i], path[i + 1]
                    if v1 not in next_weights:
                        next_weights[v1] = {}
                    if (v1, v2) not in next_hops:
                        next_hops[v1, v2] = 0
                    next_weights[v1][v2] = a_class[0]['edge_weights'][v1, v2]
                    next_hops[v1, v2] += 1

            # Apply load to links
            for path in pathdict[source,destination]:
                if i < len(path) - 1:
                    v1, v2 = path[i], path[i + 1]
                    weight = a_class[0]['edge_weights'][v1, v2]
                    total_next_hop_weight = sum(next_weights[v1][v2] for v2 in next_weights[v1])
                    if (total_next_hop_weight == 0) and (v1 in next_loads):
                        number_of_splits = len(next_weights[v1])
                        split_load = ((1 / number_of_splits) * next_loads[v1]) / next_hops[v1, v2]
                    elif (total_next_hop_weight == 0) and (v1 not in next_loads):
                        number_of_splits = len(next_weights[v1])
                        split_load = ((1 / number_of_splits) * load) / next_hops[v1, v2]
                    elif v1 in next_loads:
                        split_load = ((weight / total_next_hop_weight) * next_loads[v1]) / next_hops[v1, v2]
                    else:
                        split_load = ((weight / total_next_hop_weight) * load) / next_hops[v1, v2]

                    # Add load to next hops and remove load from previous nodes
                    if v2 not in next_loads:
                        next_loads[v2] = 0
                    next_loads[v2] += split_load
                    if v1 in next_loads:
                        next_loads[v1] -= split_load

                    link_caps[v1, v2] -= split_load

                    # Update inverse capacity
                    inverse_graph[v1][v2]['weight'] = 1 / max(link_caps[v1, v2], 1)

    essence_state.link_weights = a_class[0]['edge_weights']

    return pathdict

def create_population(network, population_size, weight_range):
    population = []
    for _ in range(population_size):
        individual = {}
        individual['demand_weights'] = {}
        individual['edge_weights'] = {}
        for src, tgt in network.demands:
            individual['demand_weights'][src,tgt] = random.randint(1,weight_range)
        for src, tgt in network.topology.edges:
            individual['edge_weights'][src,tgt] = random.randint(0,100)
        population.append(individual)
    return population


def selection(population, capacities, loads, topology, essence_state):
    congestion = [calculate_fitness(individual, capacities.copy(), loads, topology, essence_state) for individual in
                  population]

    # Zip the fitness values and the population together
    fitness_population = zip(congestion, population)

    # Sort the list of tuples by the fitness values
    sorted_fitness_population = sorted(fitness_population, key=lambda x: x[0])

    # Extract the individuals from the sorted list of tuples
    population = [individual for fitness, individual in sorted_fitness_population]

    a_class = population[:int(len(population) * 0.2)]
    b_class = population[int(len(population) * 0.2):int(len(population) * 0.9)]
    c_class = population[int(len(population) * 0.9):]

    return a_class, b_class, c_class

def crossover(p1, p2):
    child = {'demand_weights': {}, 'edge_weights': {}}
    for demand in p1['demand_weights'].keys():
        if random.random() < 0.7:
            child['demand_weights'][demand] = p1['demand_weights'][demand]
        else:
            child['demand_weights'][demand] = p2['demand_weights'][demand]

    for edge in p1['edge_weights'].keys():
        if random.random() < 0.7:
            child['edge_weights'][edge] = p1['edge_weights'][edge]
        else:
            child['edge_weights'][edge] = p2['edge_weights'][edge]
    return child

def mutation(c, weight_range):
    if random.random() < 0.01:
        for src, tgt in c['demand_weights']:
            c['demand_weights'][src, tgt] = random.randint(1, weight_range)
        for src, tgt in c['edge_weights']:
            c['edge_weights'][src, tgt] = random.randint(1, 100)
        return c
    else:
        return c


def calculate_fitness(individual, capacities, demands, topology, essence_state):
    # Initialize the utilization of each link to 0
    link_loads = {link: 0 for link in capacities.keys()}

    weights = individual['demand_weights']

    demands_ordered = dict(sorted(weights.items(), key=lambda item: item[1], reverse=True))

    link_caps = capacities.copy()
    inverse_graph = essence_state.inverse_capacity_graph.to_directed().copy()

    for (source, destination) in demands_ordered:
        load = demands[source, destination]
        paths = nx.all_shortest_paths(inverse_graph, source, destination, weight='weight')
        longest_path_len = max([len(i) for i in paths]) - 1
        next_loads = {}
        for i in range(longest_path_len):

            # Find the number of splits and weights
            next_weights = {}
            next_hops = {}
            for path in paths:
                if i < len(path) - 1:
                    v1, v2 = path[i], path[i + 1]
                    if v1 not in next_weights:
                        next_weights[v1] = {}
                    if (v1, v2) not in next_hops:
                        next_hops[v1, v2] = 0
                    next_weights[v1][v2] = individual['edge_weights'][v1, v2]
                    next_hops[v1, v2] += 1

            # Apply load to links
            for path in paths:
                if i < len(path) - 1:
                    v1, v2 = path[i], path[i + 1]
                    weight = individual['edge_weights'][v1, v2]
                    total_next_hop_weight = sum(next_weights[v1][v2] for v2 in next_weights[v1])
                    if (total_next_hop_weight == 0) and (v1 in next_loads):
                        number_of_splits = len(next_weights[v1])
                        split_load = ((1 / number_of_splits) * next_loads[v1]) / next_hops[v1, v2]
                    elif (total_next_hop_weight == 0) and (v1 not in next_loads):
                        number_of_splits = len(next_weights[v1])
                        split_load = ((1 / number_of_splits) * load) / next_hops[v1, v2]
                    elif v1 in next_loads:
                        split_load = ((weight / total_next_hop_weight) * next_loads[v1]) / next_hops[v1, v2]
                    else:
                        split_load = ((weight / total_next_hop_weight) * load) / next_hops[v1, v2]

                    # Add load to next hops and remove load from previous nodes
                    if v2 not in next_loads:
                        next_loads[v2] = 0
                    next_loads[v2] += split_load
                    if v1 in next_loads:
                        next_loads[v1] -= split_load

                    link_caps[v1, v2] -= split_load

                    # Update inverse capacity
                    inverse_graph[v1][v2]['weight'] = 1 / max(link_caps[v1, v2], 1)

                    link_loads[v1, v2] += demands[v1, v2]

    congestion = 0
    for link, capacity in capacities.items():
        utilization = link_loads[link] / capacity
        congestion += fortz_func(utilization) * capacity
    return congestion

def fortz_func(u):
    if u <= 1 / 20:
        return u * 0.1
    if u <= 1 / 10:
        return u * 0.3 - 0.01
    if u <= 1 / 6:
        return u * 1 - 0.08
    if u <= 1 / 3:
        return u * 2 - 0.24666
    if u <= 1 / 2:
        return u * 5 - 1.24666
    if u <= 2 / 3:
        return u * 10 - 3.74666
    if u <= 9 / 10:
        return u * 20 - 10.41333
    if u <= 1:
        return u * 70 - 55.41333
    if u <= 11 / 10:
        return u * 500 - 485.41333
    else:
        return u * 5000 - 5435.41333