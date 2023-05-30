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
from classes.essence_state import EssenceState


def essence_weight_setting(network: MPLS_Network, essence_state: EssenceState, conf, start_time):
    genetic_weights = genetic_algorithm(network=network, loads=network.demands,
                                      capacities=nx.get_edge_attributes(network.topology, 'capacity'),
                                      essence_state=essence_state, conf=conf, start_time=start_time,
                                      time_limit=conf["update_interval"])
    return genetic_weights


def genetic_algorithm(network, loads, capacities, essence_state, conf, start_time, generations=1000,
                      population_size=200,
                      crossover_rate=0.9,
                      mutation_rate=0.7, time_limit=118, weight_range=1000):
    end_time = start_time + time_limit

    if not essence_state.current_population:
        population = create_population(network, population_size, weight_range)
    else:
        new_population = create_population(network, int(population_size * 0.8), weight_range)
        population = essence_state.current_population + new_population

    # Run the genetic algorithm
    #for generation in range(generations):
    while time.time() < end_time:
        # Select parents
        a_class, b_class, c_class = selection(population, capacities, loads, essence_state)
        #print(str(generation) + ": " + str(calculate_fitness(a_class[0], capacities, loads, essence_state)))
        # Generate the children
        # random_solutions = [{k: random.choice(v) for k, v in viable_paths.items()} for _ in range(int(population_size * 0.1))]
        children = a_class  # + random_solutions
        while len(children) < population_size:
            parent1 = random.choice(a_class)
            parent2 = random.choice(b_class + c_class)
            child1, child2 = two_point_crossover(parent1, parent2, crossover_rate)
            child1 = mutate(child1, mutation_rate, weight_range)
            child2 = mutate(child2, mutation_rate, weight_range)
            children.extend([child1, child2])

        # Replace the population with the children
        population = children

    # Sort the population by fitness
    a_class, b_class, c_class = selection(population, capacities, loads, essence_state)

    essence_state.current_population = population[:int(len(population) * 0.2)]
    # Return the fittest individual
    return a_class[0]

def create_population(network, population_size, weight_range):
    population = []
    for _ in range(population_size):
        individual = {}
        for src, tgt in network.topology.edges:
            individual[src,tgt] = random.randint(0,weight_range)
        population.append(individual)
    return population


def selection(population, capacities, loads, essence_state):
    congestion = [calculate_fitness(individual, capacities, loads, essence_state) for individual in
                  population]

    # Zip the fitness values and the population together
    fitness_population = zip(congestion, population)

    # Sort the list of tuples by the fitness values
    sorted_fitness_population = sorted(fitness_population, key=lambda x: x[0])

    # Extract the individuals from the sorted list of tuples
    population = [individual for fitness, individual in sorted_fitness_population]

    # Select the top 50% of the population as parents
    # num_parents = int(len(population) * 0.5)
    # parents = population[:num_parents]

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


def calculate_fitness(individual, capacities, loads, essence_state):
    # Initialize the utilization of each link to 0
    link_loads = {link: 0 for link in capacities.keys()}

    # Calculate the utilization of each link
    for (source, destination), paths in essence_state.pathdict.items():
        load = loads[source, destination]
        longest_path_len = max([len(i) for i in paths]) - 1
        next_hops = {}
        next_loads = {}
        for i in range(0, longest_path_len):
            for path in paths:
                src, tgt = path[i], path[i + 1]
                if src not in next_hops:
                    next_hops[src] = {}
                next_hops[src][tgt] = individual[src, tgt]
            for path in paths:
                src, tgt = path[i], path[i + 1]
                total_next_hop_weights = sum(next_hops[src][tgt] for tgt in next_hops[src])

                if total_next_hop_weights == 0:
                    split_load = load
                    next_loads[tgt] = split_load
                else:
                    if src in next_loads:
                        split_load = (individual[src, tgt] / total_next_hop_weights) * next_loads[src]
                    else:
                        split_load = (individual[src, tgt] / total_next_hop_weights) * load

                next_loads[tgt] = split_load

                link_loads[src, tgt] += split_load

    # Calculate the congestion component of the fitness
    congestion = 0
    for link, capacity in capacities.items():
        utilization = link_loads[link] / capacity
        congestion += fortz_func(utilization)
    return congestion

    # return max(link_loads.values())


def mutate(individual, mutation_rate, weight_range):
    # Determine if the individual should be mutated
    if random.random() > mutation_rate:
        return individual

    # Choose a random source-destination pair to mutate
    src, tgt = random.choice(list(individual.keys()))

    # Choose a new path for the pair from the viable paths
    individual[src, tgt] = random.randint(0,weight_range)

    return individual


def normalize(value):
    min_value = min(value)
    range_value = max(value) - min_value
    if range_value == 0:
        return value
    else:
        normalized_values = [(x - min_value) / range_value for x in value]
        return normalized_values


def normalize_values(congestion, stretch):
    normalized_congestion = normalize(congestion)
    normalized_stretch = normalize(stretch)
    return normalized_congestion, normalized_stretch


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
