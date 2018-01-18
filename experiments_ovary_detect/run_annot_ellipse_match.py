"""
Attempt to detect egg centers in the segmented images from annotated data.
The output is list of potential center candidates

SAMPLE run:
>> python run_center_evaluation.py -list none \
    -segs "images/drosophila_ovary_slice/segm/*.png" \
    -imgs "images/drosophila_ovary_slice/image/*.jpg" \
    -centers "results/detect-centers-predict_ovary/centers/*.csv" \
    -out results/detect-centers-predict_ovary

Copyright (C) 2016-2017 Jiri Borovec <jiri.borovec@fel.cvut.cz>
"""

import os
import sys
import glob
import time
import logging
import argparse
import traceback
import gc
import multiprocessing as mproc
from functools import partial

import tqdm
import pandas as pd
import numpy as np
from PIL import Image
from scipy import ndimage

import matplotlib

sys.path += [os.path.abspath('.'), os.path.abspath('..')]  # Add path to root
import segmentation.utils.data_io as tl_io
import segmentation.utils.experiments as tl_expt
import segmentation.utils.drawing as tl_visu
import segmentation.annotation as seg_annot
import segmentation.ellipse_fitting as ell_fit

NAME_CSV_RESULTS = 'info_ovary_images_ellipses.csv'
COLUMNS_POSITION_REC = ['ant_x', 'ant_y', 'post_x', 'post_y', 'lat_x', 'lat_y']
SLICE_NAME_GROUPING = 'stack_path'
OVERLAP_THRESHOLD = 0.4

NB_THREADS = max(1, int(mproc.cpu_count() * 0.8))
PATH_IMAGES = tl_io.update_path(os.path.join('images', 'drosophila_ovary_slice'))
PATH_RESULTS = tl_io.update_path('results', absolute=True)

PARAMS = {
    'path_images': os.path.join(PATH_IMAGES, 'image', '*.jpg'),
    'path_ellipses': os.path.join(PATH_IMAGES, 'ellipse_fitting', '*.csv'),
    'path_infofile': os.path.join(PATH_IMAGES, 'info_ovary_images.txt'),
    'path_output': os.path.join(PATH_RESULTS),
}


def arg_parse_params(params=PARAMS):
    """
    SEE: https://docs.python.org/3/library/argparse.html
    :return: {str: str}, int
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-imgs', '--path_images', type=str, required=False,
                        help='path to directory & name pattern for images',
                        default=params['path_images'])
    parser.add_argument('-ells', '--path_ellipses', type=str, required=False,
                        help='path to directory & name pattern for ellipses',
                        default=params['path_ellipses'])
    parser.add_argument('-info', '--path_infofile', type=str, required=False,
                        help='path to the global information file',
                        default=params['path_infofile'])
    parser.add_argument('-out', '--path_output', type=str, required=False,
                        help='path to the output directory',
                        default=params['path_output'])
    parser.add_argument('--nb_jobs', type=int, required=False, default=NB_THREADS,
                        help='number of processes in parallel')
    arg_params = vars(parser.parse_args())
    params.update(arg_params)
    for k in (k for k in params if 'path' in k):
        params[k] = tl_io.update_path(params[k], absolute=True)
    logging.info('ARG PARAMETERS: \n %s', repr(params))
    return params


def select_optimal_ellipse(idx_row, path_dir_csv, overlap_thr=OVERLAP_THRESHOLD):
    idx, row = idx_row
    dict_row = dict(row)
    path_csv = os.path.join(path_dir_csv, row['image_name'] + '.csv')
    df_ellipses = pd.DataFrame().from_csv(path_csv)

    pos = row[tl_visu.COLUMNS_POSITION_EGG_ANNOT]
    max_size = 2 * max(pos) + min(pos)

    pos_ant = [[row['ant_x'], row['ant_y']]]
    pos_lat = [[row['lat_x'], row['lat_y']]]
    pos_post = [[row['post_x'], row['post_y']]]
    mask_ref = tl_visu.draw_eggs_rectangle((max_size, max_size),
                                           pos_ant, pos_lat, pos_post)[0]

    list_jaccard = []
    for idx, ell_row in df_ellipses.iterrows():
        mask_ell = ell_fit.add_overlap_ellipse(np.zeros(mask_ref.shape),
                                               ell_row.values.tolist(), 1)
        union = np.sum(np.logical_and(mask_ref, mask_ell))
        intersect = np.sum(np.logical_or(mask_ref, mask_ell))
        list_jaccard.append(union / float(intersect))

    # if no match with annotation
    if max(list_jaccard) < overlap_thr:
        dict_row['ellipse_Jaccard'] = max(list_jaccard)
        return dict_row

    idx_best = np.argmax(list_jaccard)
    ell_best = dict(df_ellipses.iloc[idx_best])

    # optional swap main axis and rotate by 90 deg
    if ell_best['b'] > ell_best['a']:
        ell_best['a'], ell_best['b'] = ell_best['b'], ell_best['a']
        ell_best['theta'] += np.deg2rad(90)

    ell_best['Jaccard'] = max(list_jaccard)
    # add to each name ellipse prefix
    dict_row.update({'ellipse_' + n: ell_best[n] for n in ell_best})

    return dict_row


def main(params):
    """ PIPELINE for new detections

    :param {str: str} paths:
    :param int nb_jobs:
    """
    logging.info('running...')

    # tl_expt.set_experiment_logger(params['path_expt'])
    # tl_expt.create_subfolders(params['path_expt'], LIST_SUBDIRS)
    logging.info(tl_expt.string_dict(params, desc='PARAMETERS'))

    df_info = pd.DataFrame().from_csv(params['path_infofile'], sep='\t')
    list_name_csv = [os.path.splitext(os.path.basename(p))[0]
                     for p in glob.glob(params['path_ellipses'])]
    logging.info('loaded item in table %i and found in dir %i'
                 % (len(df_info), len(list_name_csv)))

    df_info['image_name'] = [os.path.splitext(p)[0]
                             for p in df_info['image_path']]
    df_info = df_info[df_info['image_name'].isin(list_name_csv)]
    logging.info('filtered %i item in table' % len(df_info))

    # perform on new images
    list_evals = []
    path_dir_csv = os.path.dirname(params['path_ellipses'])
    tqdm_bar = tqdm.tqdm(total=len(df_info))
    if params['nb_jobs'] > 1:
        wrapper_match = partial(select_optimal_ellipse,
                                path_dir_csv=path_dir_csv)
        mproc_pool = mproc.Pool(params['nb_jobs'])
        for dict_row in mproc_pool.imap_unordered(wrapper_match,
                                                   df_info.iterrows()):
            list_evals.append(dict_row)
            tqdm_bar.update()
        mproc_pool.close()
        mproc_pool.join()
    else:
        for idx_row in df_info.iterrows():
            dict_row = select_optimal_ellipse(idx_row, path_dir_csv)
            list_evals.append(dict_row)
            tqdm_bar.update()

    df_ellipses = pd.DataFrame(list_evals)
    df_ellipses.to_csv(os.path.join(params['path_output'], NAME_CSV_RESULTS))

    logging.info('DONE')


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    params = arg_parse_params(PARAMS)
    main(params)
