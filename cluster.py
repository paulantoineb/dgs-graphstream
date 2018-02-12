#!/usr/bin/env python3

import os
import tempfile
import logging
import itertools
import subprocess

from graph import add_node_attribute_to_graph
import utils

def add_clusters_to_graph(sub_graphs, clusters_per_node_per_graph):
    for index, clusters_per_node in enumerate(clusters_per_node_per_graph):     
        # remove non-existent nodes from clusters_per_node dictionary
        node_ids = [node for node in sub_graphs[index].nodes()]
        utils.prune_invalid_keys_from_dictionary(node_ids, clusters_per_node)

        # add cluster attribute to dot file
        first_cluster_per_node = {k:v[0] for k,v in clusters_per_node.items()} # gvmap only supports a single cluster per node
        add_node_attribute_to_graph(sub_graphs[index], 'cluster', first_cluster_per_node)

def create_cluster_for_homeless_nodes(graph, clusters_per_node):
    max_cluster = get_max_cluster_value(clusters_per_node)
    homeless_cluster_id = max_cluster + 1
    # Find homeless nodes
    homeless_nodes = []
    for node in graph.nodes():
        if not node in clusters_per_node:
            homeless_nodes.append(node)
    # Create cluster for homeless nodes
    logging.info("Creating homeless cluster %d for nodes [%s]", homeless_cluster_id, ','.join(str(n) for n in homeless_nodes))
    for node in homeless_nodes:
        clusters_per_node[node] = [homeless_cluster_id] # insert cluster for homeless nodes

def get_max_cluster_value(clusters_per_node):
    return max(itertools.chain(*clusters_per_node.values()))

def do_local_to_global_cluster_conversion(clusters_per_node_per_graph):
    logging.info("Performing local to global cluster ids conversion")
    local_to_global_cluster_mapping = {}
    cluster_increment = 0
    for index, clusters_per_node in enumerate(clusters_per_node_per_graph):
        # compute max cluster value
        max_cluster = get_max_cluster_value(clusters_per_node)
        # save cluster increment of current clusters_per_node
        local_to_global_cluster_mapping[index] = cluster_increment
        # increment cluster values in clusters_per_node by cluster_increment
        for node, clusters in clusters_per_node.items():
            clusters_per_node[node] = [cluster + cluster_increment for cluster in clusters] # increment all clusters values by global_cluster_index
        # update increment value
        cluster_increment += max_cluster

    return local_to_global_cluster_mapping

def run_oslom2(output_directory, edges_oslom_filename, oslom2_dir, cluster_seed, infomap_calls):
    """
    Use OSLOM to find clusters in graph
    http://www.oslom.org/
    http://www.oslom.org/code/ReadMe.pdf for documentation on program options
    """

    temp_dir = tempfile.mkdtemp()
    oslom_bin = os.path.join(oslom2_dir, "oslom_undir")
    oslom_log = os.path.join(output_directory, "oslom.log")

    r = 10
    hr = 50
    args = [oslom_bin, "-f", edges_oslom_filename, "-w", "-r", str(r), "-hr", str(hr), "-seed", str(cluster_seed), '-infomap', str(infomap_calls)]
    logging.debug("oslom2 command: %s", ' '.join(args))
    with open(oslom_log, "a") as logwriter:
        retval = subprocess.call(args, stdout=logwriter, stderr=subprocess.STDOUT)

def run_infomap(output_directory, pajek_file, infomap_dir, cluster_seed):
    infomap_bin = os.path.join(infomap_dir, "Infomap")
    num_trials = 1
    args = [infomap_bin, pajek_file, output_directory, '--seed', str(cluster_seed), ' --num-trials', str(num_trials), '--overlapping']
    logging.debug("infomap command: %s", ' '.join(args))
    log_file = os.path.join(output_directory, "infomap.log")
    with open(log_file, "a") as logwriter:
        retval = subprocess.call(args, stdout=logwriter, stderr=subprocess.STDOUT)