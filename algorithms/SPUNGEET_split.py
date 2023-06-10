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

    demands_ordered = sorted(a_class[0], key=lambda weights: a_class[0][weights], reverse=True)

    inverse_graph = essence_state.inverse_capacity_graph.copy()

    pathdict = {}
    link_caps = capacities.copy()

    for (src, tgt) in demands_ordered:
        paths = list(nx.all_shortest_paths(inverse_graph, src, tgt))
        pathdict[src, tgt] = paths
        demand = loads[(src, tgt)] / len(paths)
        for path in paths:
            # Apply load to each link in the path
            for i in range(len(path) - 1):
                v1, v2 = path[i], path[i + 1]

                # Subtract load from capacity
                link_caps[v1, v2] -= demand

                # Update inverse capacity
                inverse_graph[v1][v2]['weight'] = 1 / max(link_caps[v1, v2], 1)

    return pathdict

def create_population(network, population_size, weight_range):
    population = []
    for _ in range(population_size):
        individual = {}
        for src, tgt in network.demands:
            individual[src,tgt] = random.randint(1,weight_range)
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
    child = {}
    for demand in p1.keys():
        total_value = p1[demand] + p2[demand]

        random_value = random.randint(0, total_value)
        if random_value < p1[demand]:
            child[demand] = p1[demand]
        else:
            child[demand] = p2[demand]
    return child

def mutation(c, weight_range):
    if random.random() < 0.01:
        for src, tgt in c:
            c[src, tgt] = random.randint(1, weight_range)
        return c
    else:
        return c


def calculate_fitness(individual, capacities, demands, topology, essence_state):
    # Initialize the utilization of each link to 0
    link_loads = {link: 0 for link in capacities.keys()}

    demands_ordered = sorted(individual, key=lambda weights: individual[weights], reverse=True)

    link_caps = capacities.copy()
    inverse_graph = essence_state.inverse_capacity_graph.to_directed().copy()

    pathdict = {}

    for (src,tgt) in demands_ordered:
        paths = list(nx.all_shortest_paths(inverse_graph, src, tgt))
        pathdict[src,tgt] = paths
        demand = demands[(src,tgt)] / len(paths)
        for path in paths:
            # Apply load to each link in the path
            for i in range(len(path) - 1):
                v1, v2 = path[i], path[i+1]

                # Subtract load from capacity
                link_caps[v1,v2] -= demand

                # Update inverse capacity
                inverse_graph[v1][v2]['weight'] = 1 / max(link_caps[v1,v2], 1)

                link_loads[(v1,v2)] += demand


    # Calculate the congestion component of the fitness
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