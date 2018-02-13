#!/usr/bin/env python3

import os
import logging
import subprocess
import networkx as nx

import utils
import graph

'''
Combine single color per node (from gvmap) and multiple clusters per node (from OSLOM2) to get multiple colors per node
'''
def get_colors_per_node(color_per_node, clusters_per_node):
    # get cluster to color mapping
    cluster_to_color = {}
    for node, clusters in clusters_per_node.items():
        first_cluster = clusters[0] # consider only the first cluster as it was the one passed to gvmap for coloring
        if not first_cluster in cluster_to_color:
            if node in color_per_node:
                color = color_per_node[node]
                cluster_to_color[first_cluster] = color

    # get colors per node
    colors_per_node = {}
    for node, clusters in clusters_per_node.items():
        colors = [cluster_to_color[cluster] for cluster in clusters]
        colors_per_node[node] = ','.join([c.strip('"') for c in colors])
    return colors_per_node

def color_nodes_with_gvmap(output_dir, color_scheme, seed, dot_filepath, gvmap_dir):
    output_dot_filename = os.path.join(output_dir, 'gvmap.dot')
    logging.info("Coloring graph %s using gvmap and writing dot file %s", dot_filepath, output_dot_filename)
    gvmap_bin = os.path.join(gvmap_dir, "gvmap")
    scheme = 5 if color_scheme == 'primary-colors' else 1 # 1: pastel, 5: primary colors
    args = [gvmap_bin, '-e', '-w', '-c', str(scheme), '-d', str(seed), dot_filepath] # "-w option is only available with this graphviz fork https://gitlab.com/paulantoineb/graphviz
    logging.debug("gvmap command: %s", ' '.join(args))
    output_file = open(output_dot_filename, "w")
    retval = subprocess.call(
            args, cwd='.',
            stderr=subprocess.STDOUT,
            stdout=output_file)
    output_file.close()

    return output_dot_filename

def get_colors_per_node_global(color_per_node, clusters_per_node_per_graph):
    clusters_per_node = utils.merge_dictionaries(clusters_per_node_per_graph)

    if len(clusters_per_node) == 0:
        return color_per_node # nothing to do if no cluster mapping available

    # get cluster to color mapping
    cluster_to_color = {}
    for node, clusters in clusters_per_node.items():
        first_cluster = clusters[0] # consider only the first cluster as it was the one passed to gvmap for coloring
        if not first_cluster in cluster_to_color:
            if node in color_per_node:
                color = color_per_node[node]
                cluster_to_color[first_cluster] = color

    # get colors per node
    colors_per_node = {}
    for node, clusters in clusters_per_node.items():
        colors = [cluster_to_color[cluster] for cluster in clusters]
        colors_per_node[utils.to_int(node)] = ','.join([c.strip('"') for c in colors])
    return colors_per_node