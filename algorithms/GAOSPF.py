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


def GAOSPF(network: MPLS_Network, conf, start_time):
    genetic_weights = genetic_algorithm(network=network, loads=network.demands,
                                      capacities=nx.get_edge_attributes(network.topology, 'capacity'), conf=conf, start_time=start_time,
                                      time_limit=conf["update_interval"])
    return genetic_weights


def genetic_algorithm(network, loads, capacities, conf, start_time, generations=700,
                      population_size=200,
                      crossover_rate=0.9,
                      mutation_rate=0.7, time_limit=10, weight_range=65535):
    end_time = start_time + time_limit

    population = create_population(network, population_size, weight_range)

    # Run the genetic algorithm
    #for generation in range(generations):
    while time.time() < end_time:
        # Select parents
        a_class, b_class, c_class = selection(population, capacities, loads, network.topology)
        #print(str(generation) + ": " + str(calculate_fitness(a_class[0], capacities, loads, network.topology)))
        # Generate the children
        # random_solutions = [{k: random.choice(v) for k, v in viable_paths.items()} for _ in range(int(population_size * 0.1))]
        children = a_class  # + random_solutions
        while len(children) < population_size:
            parent1 = random.choice(a_class)
            parent2 = random.choice(b_class + c_class)
            child = crossover(parent1, parent2)
            children.extend([child])

        # Replace the population with the children
        population = children

    # Sort the population by fitness
    a_class, b_class, c_class = selection(population, capacities, loads, network.topology)

    # Return the fittest individual

    # Create a copy of the topology graph
    updated_topology = network.topology.copy()

    for edge, weight in a_class[0].items():
        updated_topology.add_edge(*edge, weight=weight)

    shortest_path_dict = {}
    for (src, tgt) in loads:
        shortest_path_dict[src, tgt] = list(nx.all_shortest_paths(updated_topology, src, tgt, weight='weight'))

    return shortest_path_dict

def create_population(network, population_size, weight_range):
    population = []
    for _ in range(population_size):
        individual = {}
        for src, tgt in network.topology.edges:
            individual[src,tgt] = random.randint(1,weight_range)
        population.append(individual)
    return population


def selection(population, capacities, loads, topology):
    congestion = [calculate_fitness(individual, capacities, loads, topology) for individual in
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

def crossover(p1, p2, K=0.7, pg = 0.01):
    c = {}
    for gene in p1:
        rand_num = random.random()
        if rand_num < pg:
            c[gene] = random.randint(1, 65535)
        elif rand_num < K:
            c[gene] = p1[gene]
        else:
            c[gene] = p2[gene]
    return c


def calculate_fitness(individual, capacities, loads, topology):
    # Initialize the utilization of each link to 0
    link_loads = {link: 0 for link in capacities.keys()}

    # Create a copy of the topology graph
    updated_topology = topology.copy()

    for edge, weight in individual.items():
        updated_topology.add_edge(*edge, weight=weight)

    shortest_path_dict = {}
    for (src, tgt) in loads:
        shortest_path_dict[src, tgt] = list(nx.all_shortest_paths(updated_topology, src, tgt, weight='weight'))

    # Calculate the utilization of each link
    for (source, destination), paths in shortest_path_dict.items():
        load = loads[source, destination]
        longest_path_len = max([len(i) for i in paths])
        next_hops = {}
        next_loads = {}
        for i in range(longest_path_len):
            for path in paths:
                if i < len(path) - 1:
                    src,tgt = path[i], path[i + 1]
                    if src not in next_hops:
                        next_hops[src] = {}
                    next_hops[src][tgt] = capacities[src,tgt]
            for path in paths:
                if i < len(path) - 1:
                    src,tgt = path[i], path[i+1]

                    if src in next_loads:
                        split_load = (1 / len(next_hops[src])) * next_loads[src]
                    else:
                        split_load = (1 / len(next_hops[src])) * load

                    next_loads[tgt] = split_load

                    link_loads[src,tgt] += split_load

    # Calculate the congestion component of the fitness
    congestion = 0
    for link, capacity in capacities.items():
        utilization = link_loads[link] / capacity
        congestion += fortz_func(utilization)
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