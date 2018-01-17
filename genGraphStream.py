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
import networkx as nx

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

def write_dgs(output, partition, graph, colour_map):

    filename = os.path.join(output, 'partition_{}.dgs'.format(partition))

    with open(filename, 'w') as outf:
        outf.write("DGS004\n")
        outf.write("partition_{} 0 0\n".format(partition))

        i = 0
        st = 1
        nodes_added = []
        edges_added = []
        for n in graph.nodes_iter(data=True):
            colour = 'black'
            if n[0] in colour_map:
                colour = colour_map[n[0]]

            outf.write("an {} c='{}'\n".format(n[0], colour))
            nodes_added += [n[0]]

            for e in graph.edges_iter(data=True):
                if e[0] in nodes_added and e[1] in nodes_added and (e[0], e[1]) not in edges_added:
                    outf.write("ae {} {} {}\n".format(i, e[0], e[1]))
                    edges_added += [(e[0], e[1])]
                    i += 1

            outf.write("st {}\n".format(st))
            st += 1

def create_output_dir(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def gen_dgs_files(network, assignments_f, output, partitions_num, colour_map):
    G = read_metis(network)
    assignments = read_assignments(assignments_f)
    create_output_dir(output)

    for p in range(0, partitions_num):
        nodes = [i for i,x in enumerate(assignments) if x == p]
        Gsub = G.subgraph(nodes)

        write_dgs(output, p, Gsub, colour_map)

def gen_frames(output, partitions_num):

    for p in range(0, partitions_num):
        dgs = os.path.join(output, 'partition_{}.dgs'.format(p))
        out = os.path.join(output, 'frames_partition/p{}_'.format(p))
        args = ['java', '-jar', DGSGS_JAR, '-dgs', dgs, '-out', out]
        retval = subprocess.call(
            args, cwd='.',
            stderr=subprocess.STDOUT)

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

    f = 0
    assignments = read_assignments(assignments_f)
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
                        help='Network file in METIS format')
    parser.add_argument('assignments',
                        help='Partition assignsments list')
    parser.add_argument('output',
                        help='Output directory')
    parser.add_argument('--num-partitions', '-n', type=int, default=4, metavar='N',
                        help='Number of partitions')

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

    if args.dgs or all_args:
        print("Generating colour map...")
        colour_map = gen_colour_map(args.num_partitions)
        print("Generating GraphStream DGS files...")
        gen_dgs_files(args.network, args.assignments, args.output, args.num_partitions, colour_map)
        print("Done")

    if args.frames or all_args:
        print("Using GraphStream to generate frames...")
        gen_frames(args.output, args.num_partitions)
        print("Done.")

    if args.join or all_args:
        print("Join frame tiles to video frames...")
        join_images(args.output, args.assignments, args.num_partitions)
        print("Done.")


