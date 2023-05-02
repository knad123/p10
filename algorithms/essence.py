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
from scoop import futures

import time

import random
from deap import base, creator, tools
from classes.network import MLPS_Network
from classes.essence_state import EssenceState


def essence(network, essence_state):
    # Define DEAP toolbox
    creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
    creator.create("Individual", list, fitness=creator.FitnessMin)
    toolbox = base.Toolbox()
    toolbox.register("attr_path", lambda x: [random.choice(paths) for paths in x], list(essence_state.pathdict.values()))
    toolbox.register("individual", tools.initIterate, creator.Individual, toolbox.attr_path)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)

    def evaluate(individual):
        return calculate_fitness(individual, nx.get_edge_attributes(network.topology, 'capacity'), network.demands),

    toolbox.register("evaluate", calculate_fitness, capacities=nx.get_edge_attributes(network.topology, 'capacity'), loads=network.demands)
    toolbox.register("mate", tools.cxTwoPoint)
    toolbox.register("mutate", tools.mutShuffleIndexes, indpb=0.05)
    toolbox.register("select", tools.selTournament, tournsize=3)

    # Define the genetic algorithm parameters
    population_size = 1000
    generations = 1000
    cxpb = 0.9
    mutpb = 0.7
    elite_percent = 0.2
    time_limit = 120  # in seconds

    # Initialize population
    if essence_state.current_population:
        population = [creator.Individual(ind) for ind in essence_state.current_population]
        population += toolbox.population(n=int(population_size * 0.8) - len(population))
    else:
        population = toolbox.population(n=population_size)

    # Run the genetic algorithm
    start_time = time.monotonic()
    elapsed_time = 0
    for generation in range(generations):
        # Select the parents
        parents = toolbox.select(population, len(population))

        # Clone the selected parents
        offspring = [toolbox.clone(ind) for ind in parents]

        # Apply crossover to the offspring
        for child1, child2 in zip(offspring[::2], offspring[1::2]):
            if random.random() < cxpb:
                toolbox.mate(child1, child2)

        # Apply mutation to the offspring
        for mutant in offspring:
            if random.random() < mutpb:
                toolbox.mutate(mutant)

        # Evaluate the fitness of the offspring
        fitnesses = toolbox.map(toolbox.evaluate, offspring)
        for ind, fit in zip(offspring, fitnesses):
            ind.fitness.values = fit

        # Combine the offspring and the parents
        population = parents + offspring

        # Select the next generation
        elite_size = int(population_size * elite_percent)
        population = tools.selBest(population, k=elite_size) + tools.selTournament(population, k=population_size - elite_size, tournsize=3)

        # Update the elapsed time
        end_time = time.monotonic()
        elapsed_time = end_time - start_time
        if elapsed_time > time_limit:
            break

    # Return the fittest individual
    best_individual = tools.selBest(population, k=1)[0]
    return {edge: best_individual[i] for i, edge in enumerate(network.topology.edges())}

def calculate_fitness(individual, capacities, loads):
    fitness = 0

    # Initialize the utilization of each link to 0
    utilization = {link: 0 for link in capacities.keys()}

    # Calculate the utilization of each link
    for path in individual:
        load = loads[path[0], path[-1]]
        for i in range(len(path) - 1):
            link = (path[i], path[i + 1])
            utilization[link] += load

    # Calculate the fitness using the fortz_func
    for link, capacity in capacities.items():
        u = utilization[link] / capacity
        fitness += fortz_func(u)

    return fitness


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
