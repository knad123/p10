import itertools
import math

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
from classes.network import MLPS_Network


def essence(network: MLPS_Network):
    G = network.topology
    flow_to_graph = {f: network.topology for f in network.demands}
    for graph in flow_to_graph.values():
        for src, tgt in graph.edges:
            graph[src][tgt]["weight"] = 0

    pathdict = dict()

    for src, tgt in network.demands:
        pathdict[(src, tgt)] = []

    for src, tgt in network.demands:
        unique_paths = []
        while True:
            path = nx.shortest_path(flow_to_graph[(src, tgt)], src, tgt, weight="weight")
            for v1, v2 in zip(path[:-1], path[1:]):
                w = flow_to_graph[(src, tgt)][v1][v2]["weight"]
                w = w * 2 + 1
                flow_to_graph[(src, tgt)][v1][v2]["weight"] = w
            pathdict[(src, tgt)].append(path)
            if path not in unique_paths:
                unique_paths.append(path)
            if pathdict[(src, tgt)].count(path) == 3:
                pathdict[(src, tgt)] = unique_paths
                break

    genetic_paths = genetic_algorithm(viable_paths=pathdict, loads=network.demands,
                                      capacities=nx.get_edge_attributes(network.topology, 'capacity'))

    return genetic_paths


def genetic_algorithm(viable_paths, loads, capacities, generations=100, population_size=50, crossover_rate=0.9,
                      mutation_rate=0.7, elite_percent=0.2):
    # Initialize the population
    population = [{k: random.choice(v) for k, v in viable_paths.items()} for i in range(population_size)]

    # Run the genetic algorithm
    for generation in range(generations):
        # Select parents
        a_class, b_class, c_class = class_selection(population, capacities, loads)
        #print(str(generation) + ": " + str(calculate_fitness(a_class[0], capacities, loads)))
        # Generate the children
        # random_solutions = [{k: random.choice(v) for k, v in viable_paths.items()} for _ in range(int(population_size * 0.1))]
        children = a_class  # + random_solutions
        while len(children) < population_size:
            parent1 = random.choice(a_class)
            parent2 = random.choice(b_class + c_class)
            child1, child2 = two_point_crossover(parent1, parent2, crossover_rate)
            child1 = mutate(child1, mutation_rate, viable_paths)
            child2 = mutate(child2, mutation_rate, viable_paths)
            children.extend([child1, child2])

        # Replace the population with the children
        population = children

    # Sort the population by fitness
    population.sort(key=lambda x: calculate_fitness(x, capacities, loads))

    # Return the fittest individual
    return population[0]


def class_selection(population, capacities, loads):
    # Sort the population by fitness
    population.sort(key=lambda x: calculate_fitness(x, capacities, loads))

    # Select the top 50% of the population as parents
    a_class = population[:int(len(population) * 0.2)]
    b_class = population[int(len(population) * 0.2):int(len(population) * 0.9)]
    c_class = population[int(len(population) * 0.9):]

    return a_class, b_class, c_class


def two_point_crossover(individual1, individual2, crossover_probability):
    # Check if crossover should happen
    if random.random() > crossover_probability:
        return individual1, individual2

    # Select two random points in the individuals
    point1 = random.randint(1, len(individual1) - 1)
    point2 = random.randint(point1 + 1, len(individual1))

    # Create the offspring by exchanging the elements between the two points
    offspring1 = {}
    offspring2 = {}
    i = 0
    for (src, tgt), path in individual1.items():
        if i < point1:
            offspring1[(src, tgt)] = path
            offspring2[(src, tgt)] = individual2[(src, tgt)]
        elif i < point2:
            offspring1[(src, tgt)] = individual2[(src, tgt)]
            offspring2[(src, tgt)] = path
        else:
            offspring1[(src, tgt)] = path
            offspring2[(src, tgt)] = individual2[(src, tgt)]
        i += 1

    return offspring1, offspring2


def calculate_fitness(individual, capacities, loads):
    fitness = 0

    # Initialize the utilization of each link to 0
    utilization = {link: 0 for link in capacities.keys()}

    # Calculate the utilization of each link
    for (source, destination), path in individual.items():
        load = loads[source, destination]
        for i in range(len(path) - 1):
            link = (path[i], path[i + 1])
            utilization[link] += load

    # Calculate the fitness using the fortz_func
    for link, capacity in capacities.items():
        u = utilization[link] / capacity
        fitness += fortz_func(u)

    return fitness


def mutate(individual, mutation_rate, viable_paths):
    # Determine if the individual should be mutated
    if random.random() > mutation_rate:
        return individual

    # Choose a random source-destination pair to mutate
    source, destination = random.choice(list(individual.keys()))

    # Choose a new path for the pair from the viable paths
    new_path = random.choice(viable_paths[(source, destination)])

    # Mutate the individual
    individual[(source, destination)] = new_path

    return individual


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
