#!/usr/bin/env python3

import os
import gzip
import glob
import shutil
import re
import tempfile
from colour import Color
import colorsys
import argparse
import itertools
import subprocess
import random
import networkx as nx
import pydot
from collections import defaultdict

DGSGS_JAR = 'dgs-graphstream/dist/dgs-graphstream.jar'

def read_metis(DATA_FILENAME):

    G = nx.Graph()

    # add node weights from METIS file
    with open(DATA_FILENAME, "r") as metis:

        n = 0
        first_line = None
        has_edge_weights = False
        has_node_weights = False
        for i, line in enumerate(metis):
            if line[0] == '%':
                # ignore comments
                continue

            if not first_line:
                # read meta data from first line
                first_line = line.split()
                m_nodes = int(first_line[0])
                m_edges = int(first_line[1])
                if len(first_line) > 2:
                    # FMT has the following meanings:
                    #  0  the graph has no weights (in this case, you can omit FMT)
                    #  1  the graph has edge weights
                    # 10  the graph has node weights
                    # 11  the graph has both edge and node weights
                    file_format = first_line[2]
                    if int(file_format) == 0:
                        pass
                    elif int(file_format) == 1:
                        has_edge_weights = True
                    elif int(file_format) == 10:
                        has_node_weights = True
                    elif int(file_format) == 11:
                        has_edge_weights = True
                        has_node_weights = True
                    else:
                        assert False, "File format not supported"
                continue

            # METIS starts node count from 1, here we start from 0 by
            # subtracting 1 in the edge list and incrementing 'n' after
            # processing the line.
            if line.strip():
                e = line.split()
                if has_edge_weights and has_node_weights:
                    if len(e) > 2:
                        # create weighted edge list:
                        #  [(1, 2, {'weight':'2'}), (1, 3, {'weight':'8'})]
                        edges_split = list(zip(*[iter(e[1:])] * 2))
                        edge_list = [(n, int(v[0]) - 1, {'weight': int(v[1])}) for v in edges_split]

                        G.add_edges_from(edge_list)
                        G.node[n]['weight'] = int(e[0])
                    else:
                        # no edges
                        G.add_nodes_from([n], weight=int(e[0]))

                elif has_edge_weights and not has_node_weights:
                    pass
                elif not has_edge_weights and has_node_weights:
                    pass
                else:
                    edge_list = [(n, int(v) - 1, {'weight':1.0}) for v in e]
                    G.add_edges_from(edge_list)
                    G.node[n]['weight'] = 1.0
            else:
                # blank line indicates no node weight
                G.add_nodes_from([n], weight=1.0)
            n += 1

    # sanity check
    assert (m_nodes == G.number_of_nodes()), "Expected {} nodes, networkx graph contains {} nodes".format(m_nodes, G.number_of_nodes())
    assert (m_edges == G.number_of_edges()), "Expected {} edges, networkx graph contains {} edges".format(m_edges, G.number_of_edges())

    return G
    
def read_dot(network):
    return nx.nx_agraph.read_dot(network)
    
def remove_string_from_file(file, string):
    f = open(file,'r')
    filedata = f.read()
    f.close()
    newdata = filedata.replace(string,"")
    f = open(file,'w')
    f.write(newdata)
    f.close()
        
def read_pajek(network):
    remove_string_from_file(network, "ic ") # remove "ic" attribute from pajek file so that nx.read_pajek reads the node color (it only reads the first 7 attributes and the color is the 8th)
    graph = nx.read_pajek(network)
    return graph

def read_assignments(assignments):
    with open(assignments, 'r') as f:
        # remove \n
        return [int(l.strip()) for l in f.readlines()]

def get_N_HexCol(N=5):
    #HSV_tuples = [(x * 1.0 / N, 0.5, 0.5) for x in range(N)]
    #hex_out = []
    #for rgb in HSV_tuples:
    #    rgb = map(lambda x: int(x * 255), colorsys.hsv_to_rgb(*rgb))
    #    hex_out.append('#%02x%02x%02x' % tuple(rgb))
    #return hex_out

    hex_out = []
    red = Color("red")
    blue = Color("violet")
    for c in red.range_to(blue, N):
        hex_out.append(c.hex)
    return hex_out

def gen_colour_map(partitions_num):

    groups = []
    colour_map = {}
    for p in range(0, partitions_num):
        file_oslom = os.path.join('inputs', 'oslom-p{}-tp.txt'.format(p))
        with open(file_oslom, 'r') as f:
            for line in f.readlines():
                if line[0] == '#':
                    continue
                groups += [line.strip()]

    colours = get_N_HexCol(len(groups))
    for i,cluster in enumerate(groups):
        nodes = cluster.split(' ')
        for n in nodes:
            node = int(n)
            if node in colour_map:
                print('WARNING: Node {} already had a colour.'.format(node))
            colour_map[node] = colours[i]

    return colour_map
    
def format_id(id):
    return re.sub('[^0-9a-zA-Z]+', '_', id) # replace all non-alphanumeric characters by underscore

def write_dgs(output, partition, graph, colour_map, colour_attr):

    filename = os.path.join(output, 'partition_{}.dgs'.format(partition))
    
    with open(filename, 'w') as outf:
        outf.write("DGS004\n")
        outf.write("partition_{} 0 0\n".format(partition))

        i = 0
        st = 1
        nodes_added = []
        edges_added = []
        for n in graph.nodes_iter(data=True):
            node_id = format_id(n[0])
            if colour_map:
                colour = 'black'
                if node_id in colour_map:
                    colour = colour_map[node_id]
            else:
                if colour_attr in n[1]:
                    colour = n[1][colour_attr] # get color(s) from attributes
                else:
                    colour = 'black'

            outf.write("an {} c='{}'\n".format(node_id, colour))
            nodes_added += [node_id]

            for e in graph.edges_iter(data=True):
                edge1_id = format_id(e[0])
                edge2_id = format_id(e[1])
                if edge1_id in nodes_added and edge2_id in nodes_added and (edge1_id, edge2_id) not in edges_added:
                    outf.write("ae {} {} {}\n".format(i, edge1_id, edge2_id))
                    edges_added += [(edge1_id, edge2_id)]
                    i += 1

            outf.write("st {}\n".format(st))
            st += 1

def create_or_clean_output_dir(directory):
    if os.path.exists(directory):
        shutil.rmtree(directory) # delete folder if it exists
    os.makedirs(directory) # create folder
    
def relabel_graph(graph):
    # relabel nodes with id instead of label
    mapping = {n[0]:n[1]['id'] for n in graph.nodes_iter(data=True)}
    return nx.relabel_nodes(graph, mapping)
    
def read_graph_from_file(network, format, using_infomap):
    graph = None
    if format == 'metis':
        graph = read_metis(network)
    elif format == 'dot':
        graph = read_dot(network)
    elif format == 'pajek':
        graph = read_pajek(network) 
        if using_infomap:   
            graph = relabel_graph(graph) # relabel graph with id for infomap as infomap's .tree file use the id to refer to the nodes while OSLOM2 tp file use the label
          
    return graph
    
def get_colour_attribute(format):
    if format == 'metis':
        colour_attr = "" # use colour_map
    elif format == 'dot':
        colour_attr = "fillcolor"
    else:
        colour_attr = "box"
    return colour_attr

def gen_dgs_files(network, format, assignments_f, output, partitions_num, colour_map, using_infomap):
    graph = read_graph_from_file(network, format, using_infomap)
    colour_attr = get_colour_attribute(format)
    assignments = read_assignments(assignments_f)
    
    if partitions_num == 1:
        write_dgs(output, 0, graph, colour_map, colour_attr) # ignore assignments file if single partition (TEMPORARY)
    else:
        for p in range(0, partitions_num):
            nodes = [i for i,x in enumerate(assignments) if x == p]
            Gsub = graph.subgraph(nodes)
            write_dgs(output, p, Gsub, colour_map, colour_attr)

def gen_frames(output, partitions_num, layout, seed, force, a, r, mode):
    for p in range(0, partitions_num):
        dgs = os.path.join(output, 'partition_{}.dgs'.format(p))
        output_dot_filepath = os.path.join(output, 'partition_{}.dot'.format(p))
        out = os.path.join(output, 'frames_partition/p{}_'.format(p))
        args = ['java', '-jar', DGSGS_JAR, '-dgs', dgs, '-out', out, '-layout', layout, '-seed', str(seed), '-force', str(force), '-a', str(a), '-r', str(r), '-mode', mode, '-dotfile', output_dot_filepath]
        retval = subprocess.call(
            args, cwd='.',
            stderr=subprocess.STDOUT)
            
def compute_layout_and_export_dot_file(args):
    gen_dgs_files(args.network, args.format, args.assignments, args.output, args.num_partitions, None, args.tree != None) # generate dgs file from input file
    gen_frames(args.output, args.num_partitions, args.layout, args.seed, args.force, args.a, args.r, 'dot') # compute layout from dgs file and write dot file
    clusters_per_node = add_clusters_to_dot_file(args)
    return clusters_per_node
    
def read_oslom2_tp_file(filepath):
    node_dict = defaultdict(list) # initialize modules per node dictionary
    with open(filepath, 'r') as file:
        line = next(file)
        while line:
            if line.startswith('#'): # module header line
                module_id = int(line.split()[1]) + 1 # 1-based (needed by gvmap) module id
            else: # nodes in the module
                nodes = line.split()
                for node_id in nodes:
                    node_dict[node_id].append(module_id) # add current module to node dictionary
                    
            line = next(file, None)
    
    return node_dict   
    
def read_infomap_tree_file(filepath, level):
    node_dict = defaultdict(list) # initialize modules per node dictionary
    module_ids = []
    with open(filepath, 'r') as file:
        line = next(file)
        while line:
            if not line.startswith('#'):
                values = line.split()
                module_id = ''.join(values[0].split(":")[0:level]) # concatenated module id at given level (1 to 3). 2:4:3 becomes 2 at level 1, 24 at level 2 and 243 at level 3
                if not module_id in module_ids:
                    module_ids.append(module_id)
                node_id = values[2].strip('"') # node id without quotes
                node_dict[node_id].append(module_ids.index(module_id) + 1) # add current 1-based (needed by gvmap) module id to node dictionary
                    
            line = next(file, None)
    
    return node_dict   

def prune_invalid_keys_from_dictionary(valid_keys, dictionary):   
    to_be_removed = []
    for key, value in dictionary.items():
        if not key in valid_keys:
            to_be_removed.append(key)
    for key in to_be_removed:
        del dictionary[key]
        
def add_node_attribute_to_dot_file(filepath, attribute_name, dictionary):
    # use pydot instead of networkx to edit dot file since networkx "nx.nx_agraph.write_dot" method messed up the formatting and order of dot file
    graph = pydot.graph_from_dot_file(filepath)[0]
    for node in graph.get_nodes():
        name = node.get_name().replace('"', '')
        if name in dictionary:
            value = dictionary[name]
            node.set(attribute_name, value)
    graph.write(filepath)
    
def get_node_attribute_from_dot_file(filepath, attribute_name):
    dictionary = {}
    output_graph = pydot.graph_from_dot_file(filepath)[0]
    for node in output_graph.get_nodes():
        name = node.get_name().strip('"')
        if name != 'graph':
            dictionary[name] = node.get(attribute_name)
    return dictionary
    
def add_clusters_to_dot_file(args):    
    partition = 0 # TEMPORARY
    input_dot_filename = os.path.join(args.output, 'partition_{}.dot'.format(partition))   
    
    clusters_per_node = None
    if args.tp:
        clusters_per_node = read_oslom2_tp_file(args.tp) # get cluster(s) from OSLOM2 tp file
    elif args.tree:
        level = 1
        clusters_per_node = read_infomap_tree_file(args.tree, level) # get cluster(s) from Infomap .tree file
    
    # remove non-existent nodes from clusters_per_node dictionary
    graph = read_dot(input_dot_filename)
    node_ids = [n[0] for n in graph.nodes_iter(data=True)]
    prune_invalid_keys_from_dictionary(node_ids, clusters_per_node)
    
    # add cluster attribute to dot file
    first_cluster_per_node = {k:v[0] for k,v in clusters_per_node.items()} # gvmap only supports a single cluster per node
    add_node_attribute_to_dot_file(input_dot_filename, 'cluster', first_cluster_per_node)
    
    return clusters_per_node

def color_nodes_with_gvmap(args, clusters_per_node, using_infomap):
    partition = 0 # TEMPORARY
    input_dot_filename = os.path.join(args.output, 'partition_{}.dot'.format(partition)) 
    output_dot_filename = os.path.join(args.output, 'partition_{}_out.dot'.format(partition)) 
    args = ['gvmap', '-e', '-w', '-d', str(args.seed), input_dot_filename] # "-w option is only available with this graphviz fork https://gitlab.com/paulantoineb/graphviz
    output_file = open(output_dot_filename, "w")
    retval = subprocess.call(
            args, cwd='.',
            stderr=subprocess.STDOUT,
            stdout=output_file)
    output_file.close()
    
    ### extract node color from gvmap's output and add it to the input graph (gvmap reorders nodes and edges which affects dgs)
    color_per_node = get_node_attribute_from_dot_file(output_dot_filename, 'fillcolor') 
    colors_per_node = get_colors_per_node(color_per_node, clusters_per_node) # combine single color per node (from gvmap) and multiple clusters per node (from OSLOM2) to get multiple colors per node  
    add_node_attribute_to_dot_file(input_dot_filename, 'fillcolor', color_per_node if using_infomap else colors_per_node)

    return input_dot_filename

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

def join_images(output, assignments_f, partitions_num):
    frames = {}
    frames_max = 0
    for p in range(0, partitions_num):
        path_glob = os.path.join(output, 'frames_partition', 'p{}_*.png'.format(p))
        frames[p] = sorted(glob.glob(path_glob))
        total = len(frames[p])
        if frames_max < total:
            frames_max = total

    path_joined = os.path.join(output, 'frames_joined')
    if not os.path.exists(path_joined):
        os.makedirs(path_joined)

    pframe = [-1] * partitions_num
    #tiles = [frames[f][0] for f in frames]
    tiles = ['frame_blank.png'] * partitions_num

    if partitions_num == 1:
        assignments = [0] * frames_max # ignore assignments file if single partition (TEMPORARY)
    else:
        assignments = read_assignments(assignments_f)
    
    f = 0
    for a in assignments:
        if a == -1: # XXX remove > 3
            continue

        try:
            pframe[a] += 1
            tiles[a] = frames[a][pframe[a]]

            args = ['/usr/bin/montage']
            args += tiles
            args += ['-geometry', '+0+0', '-border', '6', os.path.join(path_joined, 'frame_{0:06d}.png'.format(f))]
            retval = subprocess.call(
                args, cwd='.',
                stderr=subprocess.STDOUT)

            f += 1

        except IndexError:
            print('Missing frame p{}_{}'.format(a, pframe[a]))


    #    nodes = [i for i,x in enumerate(assignments) if x == p]

    #for f in range(0, frames_max):
    #    tiles = []
    #    for p in range(0, 4):
    #        if len(frames[p]) > f:
    #            tiles += [frames[p][f]]
    #        else:
    #            # use last frame
    #            tiles += [frames[p][len(frames[p])-1]]

    #    #args = ['/usr/bin/convert']
    #    #args += tiles
    #    #args += ['-append', os.path.join(path_joined, 'frame_{0:06d}.png'.format(f))]

    #    args = ['/usr/bin/montage']
    #    args += tiles
    #    args += ['-geometry', '+0+0', '-border', '6', os.path.join(path_joined, 'frame_{0:06d}.png'.format(f))]
    #    retval = subprocess.call(
    #        args, cwd='.',
    #        stderr=subprocess.STDOUT)




if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=
        '''Create animation of network parition assignments. First processes
        network file and assignments into DGS file format, then uses
        GraphStream to animate each frame, finally frames are stitched together.'''
    )
    parser.add_argument('network',
                        help='Input network file')
    parser.add_argument('assignments',
                        help='Partition assignments list')
    parser.add_argument('output',
                        help='Output directory')
    parser.add_argument('--tp',
                        help='OSLOM2 tp file')
    parser.add_argument('--tree',
                        help='Infomap .tree file')
    parser.add_argument('--format', choices=['metis', 'dot', 'pajek'], default='metis', help='Format of the input network')
    parser.add_argument('--num-partitions', '-n', type=int, default=4, metavar='N',
                        help='Number of partitions')
    parser.add_argument('--layout', '-l', choices=['springbox','linlog'], default='springbox',
                        help='Graph layout')
    parser.add_argument('--seed', '-s', type=int, default=random.randint(1, 10**6), metavar='S',
                        help='Seed for graph layout')
    parser.add_argument('--force', '-f', type=float, default=3.0, metavar='F',
                        help='Force for linlog graph layout')
    parser.add_argument('-a', type=float, default=0, metavar='A',
                        help='Attraction factor for linlog graph layout')
    parser.add_argument('-r', type=float, default=-1.2, metavar='R',
                        help='Repulsion factor for linlog graph layout')
    parser.add_argument('--dgs', action='store_true', default=False,
                        help='Generate GraphStream DGS file')
    parser.add_argument('--frames', action='store_true', default=False,
                        help='Convert GraphStream DGS file to frames')
    parser.add_argument('--join', action='store_true', default=False,
                        help='Tile frames in a montage')

    args = parser.parse_args()

    all_args = False
    if not args.dgs and not args.frames and not args.join:
        all_args = True
        
    create_or_clean_output_dir(args.output)
    using_infomap = args.tree != None
        
    if args.format != "metis": # compute layout with Graphstream and color nodes with gvmap
        clusters_per_node = compute_layout_and_export_dot_file(args)
        output_dot_filename = color_nodes_with_gvmap(args, clusters_per_node, using_infomap)   
        args.network = output_dot_filename
        args.format = "dot"

    if args.dgs or all_args:
        if args.format == "metis":
            print("Generating colour map...")
            colour_map = gen_colour_map(args.num_partitions)
        else:
            print("Using colours from input file")
            colour_map = None
        print("Generating GraphStream DGS files...")
        gen_dgs_files(args.network, args.format, args.assignments, args.output, args.num_partitions, colour_map, using_infomap)
        print("Done")

    if args.frames or all_args:
        print("Using GraphStream to generate frames...")
        gen_frames(args.output, args.num_partitions, args.layout, args.seed, args.force, args.a, args.r, 'images')
        print("Done.")

    if args.join or all_args:
        print("Join frame tiles to video frames...")
        join_images(args.output, args.assignments, args.num_partitions)
        print("Done.")


