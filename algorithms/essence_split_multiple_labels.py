import concurrent.futures
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
from classes.network import MPLS_Network
from classes.essence_state import EssenceState


def essence_split_multiple_labels(network: MPLS_Network, essence_state: EssenceState, conf, start_time):
    genetic_path_weights = genetic_algorithm(viable_paths=essence_state.pathdict, loads=network.demands,
                                      capacities=nx.get_edge_attributes(network.topology, 'capacity'),
                                      essence_state=essence_state, conf=conf, start_time=start_time, time_limit=conf["update_interval"])
    return genetic_path_weights

def genetic_algorithm(viable_paths, loads, capacities, essence_state, conf, start_time, generations=1000, population_size=200,
                      crossover_rate=0.7,
                      mutation_rate=0.2, time_limit=118, weight_range=10):
    end_time = start_time + time_limit
    if not essence_state.current_population:
        population = create_population(population_size, weight_range, essence_state.pathdict)
    else:
        new_population = create_population(int(population_size * 0.8), weight_range, essence_state.pathdict)
        population = essence_state.current_population + new_population

    # Run the genetic algorithm
    # for generation in range(generations):

    # Select parents
    a_class, b_class, c_class = selection(population, capacities, loads, essence_state.pathdict)

    while time.time() < end_time:
    #for generation in range(generations):
        #print(str(generation) + ": " + str(calculate_fitness(a_class[0], capacities, loads, essence_state.pathdict)))
        # Generate the children
        # random_solutions = [{k: random.choice(v) for k, v in viable_paths.items()} for _ in range(int(population_size * 0.1))]
        children = []#a_class
        while len(children) < population_size:
            parent1 = random.choice(a_class)
            parent2 = random.choice(b_class)
            child1, child2 = two_point_crossover(parent1, parent2, crossover_rate)
            child1 = mutate(child1, mutation_rate, weight_range, essence_state.pathdict)
            child2 = mutate(child2, mutation_rate, weight_range, essence_state.pathdict)
            children.extend([child1, child2])

        # Replace the population with the children
        population = children

        # Select parents
        a_class, b_class, c_class = selection(population, capacities, loads, essence_state.pathdict)

    # Return the fittest individual
    return a_class[0]

def create_population(population_size, weight_range, pathdict):
    population = []
    for _ in range(population_size):
        individual = {}
        for (src, tgt), paths in pathdict.items():
            individual[src, tgt] = []
            for path in paths:
                path_weight = random.randint(0,weight_range)
                individual[src,tgt].append(path_weight)

        for (src, tgt), weights in individual.items():
            summed_weight = 0
            for weight in weights:
                summed_weight += weight

            if summed_weight == 0:
                random_path_index = random.randint(0, len(pathdict[src,tgt])-1)
                individual[src,tgt][random_path_index] = 1

        population.append(individual)
    return population

def selection(population, capacities, loads, pathdict):
    congestion = [calculate_fitness(individual, capacities, loads, pathdict) for individual in population]

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

def calculate_fitness(individual, capacities, loads, pathdict):
    # Initialize the utilization of each link to 0
    link_load = {link: 0 for link in capacities.keys()}

    summed_weight = {}
    for (src,tgt), weights in individual.items():
        summed_weight[src,tgt] = sum(weights)

    # Calculate the utilization of each link
    for (src,tgt), weights in individual.items():
        for path_index ,weight in enumerate(weights):
            if weight == 0:
                continue
            path = pathdict[src,tgt][path_index]
            for i in range(len(path) - 1):
                load = loads[src,tgt] * (weight / summed_weight[src,tgt])
                link = (path[i], path[i + 1])
                link_load[link] += load

    #max_link_util = max([linkLoad for linkLoad in link_load.values()])

    #return max_link_util

    # Calculate the congestion component of the fitness
    congestion = 0
    for link, capacity in capacities.items():
        utilization = link_load[link] / capacity
        congestion += fortz_func(utilization)

    return congestion

def mutate(individual, mutation_rate, weight_range, pathdict):
    # Determine if the individual should be mutated
    if random.random() > mutation_rate:
        return individual

    # Choose a random source-destination pair to mutate
    src, tgt = random.choice(list(individual.keys()))


    new_path_weights = [random.randint(0,weight_range) for _ in range(len(individual[src,tgt]))]

    if sum(new_path_weights) > 0:
        individual[src, tgt] = new_path_weights
        return individual
    else:
        new_path_weights = [random.randint(1,weight_range) for _ in range(len(individual[src,tgt]))]
        individual[src, tgt] = new_path_weights
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
