#!/usr/bin/env python3

import os
import gzip
import glob
import shutil
import tempfile
from colour import Color
import colorsys
import argparse
import itertools
import subprocess
import random
import networkx as nx
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
    return nx.read_pajek(network)

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
            if colour_map:
                colour = 'black'
                if n[0] in colour_map:
                    colour = colour_map[n[0]]
            else:
                colour = n[1][colour_attr] # get color from attributes

            outf.write("an {} c='{}'\n".format(n[0], colour))
            nodes_added += [n[0]]

            for e in graph.edges_iter(data=True):
                if e[0] in nodes_added and e[1] in nodes_added and (e[0], e[1]) not in edges_added:
                    outf.write("ae {} {} {}\n".format(i, e[0], e[1]))
                    edges_added += [(e[0], e[1])]
                    i += 1

            outf.write("st {}\n".format(st))
            st += 1

def create_or_clean_output_dir(directory):
    if os.path.exists(directory):
        shutil.rmtree(directory) # delete folder if it exists
    os.makedirs(directory) # create folder
    
def read_graph_from_file(network, format):
    if format == 'metis':
        graph = read_metis(network)
    elif format == 'dot':
        graph = read_dot(network)
    else:
        graph = read_pajek(network)
    return graph
    
def get_colour_attribute(format):
    if format == 'metis':
        colour_attr = "" # use colour_map
    elif format == 'dot':
        colour_attr = "fillcolor"
    else:
        colour_attr = "box"
    return colour_attr

def gen_dgs_files(network, format, assignments_f, output, partitions_num, colour_map):
    graph = read_graph_from_file(network, format)
    colour_attr = get_colour_attribute(format)
    assignments = read_assignments(assignments_f)
    
    if partitions_num == 1:
        write_dgs(output, 0, graph, colour_map, colour_attr) # ignore assignments file if single partition (TEMPORARY)
    else:
        for p in range(0, partitions_num):
            nodes = [i for i,x in enumerate(assignments) if x == p]
            Gsub = graph.subgraph(nodes)
            write_dgs(output, p, Gsub, colour_map, colour_attr)

def gen_frames(output, partitions_num, layout, seed, mode):
    for p in range(0, partitions_num):
        dgs = os.path.join(output, 'partition_{}.dgs'.format(p))
        out = os.path.join(output, 'frames_partition/p{}_'.format(p))
        args = ['java', '-jar', DGSGS_JAR, '-dgs', dgs, '-out', out, '-layout', layout, '-seed', str(seed), '-mode', mode]
        retval = subprocess.call(
            args, cwd='.',
            stderr=subprocess.STDOUT)
            
def compute_layout_and_export_dot_file(args):
    gen_dgs_files(args.network, args.format, args.assignments, args.output, args.num_partitions, None) # generate dgs file from input file
    gen_frames(args.output, args.num_partitions, args.layout, args.seed, 'dot') # compute layout from dgs file and write dot file
    add_clusters_to_dot_file(args)
    
def read_oslom2_tp_file(filepath):
    node_dict = defaultdict(list) # initialize modules per node dictionary
    with open(filepath, 'r') as file:
        line = next(file)
        while line:
            if line.startswith('#'): # module header line
                module = line.split()[1] # module id
            else: # nodes in the module
                nodes = line.split()
                for node in nodes:
                    node_dict[node].append(module) # add current module to node dictionary
                    
            line = next(file, None)
            
    return node_dict
    
def add_clusters_to_dot_file(args):
    partition = 0 # TEMPORARY
    input_dot_filename = os.path.join(args.output, 'partition_{}.dot'.format(partition)) 
    clusters_per_node = read_oslom2_tp_file(args.tp) # get cluster(s) for each node
    graph = read_dot(input_dot_filename) # read dot file
    first_cluster_per_node = {k:v[0] for k,v in clusters_per_node.items()}
    nx.set_node_attributes(graph, 'cluster', first_cluster_per_node)
    #print(graph.nodes(data=True))
    nx.nx_agraph.write_dot(graph, input_dot_filename) # write dot file

def color_nodes_with_gvmap(args):
    partition = 0 # TEMPORARY
    input_dot_filename = os.path.join(args.output, 'partition_{}.dot'.format(partition)) 
    output_dot_filename = os.path.join(args.output, 'partition_{}_out.dot'.format(partition)) 
    args = ['gvmap', '-e', '-w', input_dot_filename]
    output_file = open(output_dot_filename, "w")
    retval = subprocess.call(
            args, cwd='.',
            stderr=subprocess.STDOUT,
            stdout=output_file)
    output_file.close()
    return output_dot_filename

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
    parser.add_argument('--format', choices=['metis', 'dot', 'pajek'], default='metis', help='Format of the input network')
    parser.add_argument('--num-partitions', '-n', type=int, default=4, metavar='N',
                        help='Number of partitions')
    parser.add_argument('--layout', '-l', choices=['springbox','linlog'], default='springbox',
                        help='Graph layout')
    parser.add_argument('--seed', '-s', type=int, default=random.randint(1, 10**6), metavar='S',
                        help='Seed for graph layout')
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
        
    if args.format != "metis": # compute layout with Graphstream and color nodes with gvmap
        compute_layout_and_export_dot_file(args)
        output_dot_filename = color_nodes_with_gvmap(args)
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
        gen_dgs_files(args.network, args.format, args.assignments, args.output, args.num_partitions, colour_map)
        print("Done")

    if args.frames or all_args:
        print("Using GraphStream to generate frames...")
        gen_frames(args.output, args.num_partitions, args.layout, args.seed, 'images')
        print("Done.")

    if args.join or all_args:
        print("Join frame tiles to video frames...")
        join_images(args.output, args.assignments, args.num_partitions)
        print("Done.")


