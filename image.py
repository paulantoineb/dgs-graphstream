#!/usr/bin/env python3

import os
import logging
import subprocess
import math
import glob
import fpdf
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF
from svgutils.compose import *
from PIL import Image

def create_png_tiles(tiles, border_size, columns, output_png_file):
    args = ['/usr/bin/montage']
    args += tiles
    args += ['-tile', '{}x'.format(columns) , '-geometry', '+0+0', '-border', str(border_size), output_png_file]
    logging.debug("montage command: %s", ' '.join(args))
    retval = subprocess.call(
        args, cwd='.',
        stderr=subprocess.STDOUT)

def create_svg_tiles(svg_tiles, output_svg_file, width, height, border_size, columns):
    rows = math.ceil(len(svg_tiles) / columns) # number of rows

    # Add tiles
    svg_objects = []
    for index, tile in enumerate(svg_tiles):
        if tile:
            # 0-based row and column
            row = math.floor(index / columns)
            col = index % columns
            # width and height offsets
            width_offset = col * width
            height_offset = row * height
            # add tile with offsets
            svg_objects.append(SVG(tile).move(width_offset, height_offset))

    # Add grid lines
    total_width = width * columns
    total_height = height * rows
    for col in range(0, columns + 1):
        svg_objects.append(Line([(width * col, 0), (width * col, total_height)], width=border_size, color='silver')) # vertical line
    for row in range(0, rows + 1):
        svg_objects.append(Line([(0, height * row), (total_width, height * row)], width=border_size, color='silver')) # horizontal line

    # Create combined svg file from tiles
    Figure(total_width, total_height,
       *svg_objects
       ).save(output_svg_file)

def combine_images_into_tiles(output, partitions, border_size, width, height, fps):
    logging.info("Combining images into tiles")
    partitions_count = len(partitions)

    # get all frames
    frames = {}
    for p in range(0, partitions_count):
        path_glob = os.path.join(output, 'frames_partition', 'p{}_*_new.png'.format(p))
        frames[p] = sorted(glob.glob(path_glob))

    max_frame_count_per_partition = max([len(frames[p]) for p in frames]) # max number of frames per partition
    extra_blank_frame_count = math.ceil(0.5 * fps) # number of extra blank frames to insert at the start
    frame_count = max_frame_count_per_partition + extra_blank_frame_count

    # create output folder
    path_joined = os.path.join(output, 'frames_joined')
    if not os.path.exists(path_joined):
        os.makedirs(path_joined)

    # compute number of rows and columns
    columns = math.ceil(math.sqrt(partitions_count))

    # create blank frame png
    blank_frame_path = os.path.join(output, 'frame_blank.png')
    blank_frame = Image.new('RGB', (width, height), (255, 255, 255)) # create white frame
    blank_frame.save(blank_frame_path, "PNG")

    # insert white frames at the start to get the same number of frames per partition and start with a few blank frames
    for p in range(0, partitions_count):
        frames[p] = [blank_frame_path] * (frame_count - len(frames[p])) + frames[p]

    frame_files_png = []
    frame_files_svg = []
    f = 0
    for _ in xrange(frame_count):
        try:
            # get all tiles for current frame (one tile per partition)
            tiles = [frames[p][f] for p in range(0, partitions_count)]

            # create png tiles
            png_frame_file = os.path.join(path_joined, 'frame_{0:06d}.png'.format(f))
            frame_files_png.append(png_frame_file)
            create_png_tiles(tiles, border_size, columns, png_frame_file)

            # create svg tiles
            svg_frame_file = os.path.join(path_joined, 'frame_{0:06d}.svg'.format(f))
            frame_files_svg.append(svg_frame_file)
            svg_tiles = [os.path.splitext(tile)[0]+'.svg' for tile in tiles] # replace .png by .svg
            svg_tiles = [svg_tile if os.path.isfile(svg_tile) else '' for svg_tile in svg_tiles ] # replace missing files by blank frames
            create_svg_tiles(svg_tiles, svg_frame_file, width, height, border_size, columns)

            f += 1

        except IndexError:
            print('Missing frame p{}_{}'.format(p, f))

    return frame_files_png, frame_files_svg

def write_png_to_pdf(png_file, output_dir):
    pdf_file = os.path.join(output_dir, os.path.splitext(os.path.basename(png_file))[0]+'_png.pdf')
    pdf = fpdf.FPDF('L', 'mm', 'A4')
    pdf.add_page()
    pdf.image(png_file, w=277) # 277mm width to center image (default margin = 10mm)
    pdf.output(pdf_file, "F")

def write_svg_to_pdf(svg_file, output_dir):
    pdf_file = os.path.join(output_dir, os.path.splitext(os.path.basename(svg_file))[0]+'.pdf')
    drawing = svg2rlg(svg_file)
    renderPDF.drawToFile(drawing, pdf_file)

def create_pdfs_from_tiles(output_dir, frame_files_svg, pdf_percentage):
    pdf_dir = os.path.join(output_dir, 'pdf')
    if not os.path.exists(pdf_dir):
        os.makedirs(pdf_dir)
    # filter frames to be converted to pdfs
    step = int(pdf_percentage / 100.0 * len(frame_files_svg))
    logging.info("Exporting every %d frames (every %d%%) as pdf", step, pdf_percentage)
    filtered_frame_files = list(reversed(frame_files_svg))[0::step]
    for frame_file in filtered_frame_files:
        write_png_to_pdf(os.path.splitext(frame_file)[0]+'.png', pdf_dir) # TEMPORARY (for validation)
        write_svg_to_pdf(frame_file, pdf_dir)