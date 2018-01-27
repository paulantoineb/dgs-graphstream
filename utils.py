#!/usr/bin/env python3

import os
import shutil
import logging
import random

def to_int(value):
    try:
        return int(value)
    except:
        return value

def merge_dictionaries(dictionaries):
    merged_dict = {}
    for d in dictionaries:
        for k, v in d.items():
            merged_dict[k] = v
    return merged_dict
    
def prune_invalid_keys_from_dictionary(valid_keys, dictionary):   
    to_be_removed = []
    for key, value in dictionary.items():
        if not key in valid_keys:
            to_be_removed.append(key)
    for key in to_be_removed:
        del dictionary[key]
        
def create_or_clean_output_dir(directory):
    logging.info("Cleaning output directory %s", os.path.abspath(directory))
    if os.path.exists(directory):
        shutil.rmtree(directory) # delete folder if it exists
    os.makedirs(directory) # create folder
    
def get_random_seed():
    return random.randint(1, 10**6)