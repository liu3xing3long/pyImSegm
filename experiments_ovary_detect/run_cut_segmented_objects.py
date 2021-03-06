"""
Cut out images according given object segmentation

SAMPLE run:
>> python run_cut_segmented_objects.py \
    -annot "images/drosophila_ovary_slice/annot_eggs/*.png" \
    -img "images/drosophila_ovary_slice/segm/*.png" \
    -out results/cut_images --padding 20

"""

import os
import sys
import logging
import argparse
import multiprocessing as mproc
from functools import partial

import matplotlib
if os.environ.get('DISPLAY', '') == '':
    logging.warning('No display found. Using non-interactive Agg backend')
matplotlib.use('Agg')

import tqdm
import numpy as np
from PIL import Image
from skimage import measure
from scipy import ndimage

sys.path += [os.path.abspath('.'), os.path.abspath('..')]  # Add path to root
import segmentation.utils.data_io as tl_io

NB_THREADS = max(1, int(mproc.cpu_count() * 0.9))
PATH_IMAGES = tl_io.update_path(os.path.join('images', 'drosophila_ovary_slice'))
PATH_RESULTS = tl_io.update_path('results', absolute=True)
PATHS = {
    'annot': os.path.join(PATH_IMAGES, 'annot_eggs', '*.png'),
    'image': os.path.join(PATH_IMAGES, 'image', '*.jpg'),
    'output': os.path.join(PATH_RESULTS, 'cut_images'),
}


def arg_parse_params(dict_paths=PATHS):
    """
    SEE: https://docs.python.org/3/library/argparse.html
    :return: {str: str}, int
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-annot', '--path_annot', type=str, required=False,
                        help='annotations',
                        default=dict_paths['annot'])
    parser.add_argument('-imgs', '--path_image', type=str, required=False,
                        help='path to directory & name pattern for images',
                        default=dict_paths['image'])
    parser.add_argument('-out', '--path_out', type=str, required=False,
                        help='path to the output directory',
                        default=dict_paths['output'])
    parser.add_argument('--padding', type=int, required=False,
                        help='crop padding [px]', default=25)
    parser.add_argument('--mask', type=int, required=False,
                        help='mask by the segmentation', default=1)
    parser.add_argument('-bg', '--background', type=int, required=False,
                        help='using background color', default=None, nargs='+')
    parser.add_argument('--nb_jobs', type=int, required=False, default=NB_THREADS,
                        help='number of processes in parallel')
    args = parser.parse_args()
    logging.info('ARG PARAMETERS: \n %s', repr(args))
    dict_paths = {
        'annot': tl_io.update_path(args.path_annot),
        'image': tl_io.update_path(args.path_image),
        'output': tl_io.update_path(args.path_out),
    }
    for k in dict_paths:
        if dict_paths[k] == '' or k == 'output':
            continue
        p = os.path.dirname(dict_paths[k]) \
            if '*' in dict_paths[k] else dict_paths[k]
        assert os.path.exists(p), 'missing (%s) "%s"' % (k, p)
    return dict_paths, args


def export_cut_objects(df_row, path_out, padding, use_mask=True, bg_color=None):
    """ cut and expert objects in image according given segmentation

    :param df_row:
    :param str path_out: path for exporting image
    :param int padding: set padding around segmented object
    """
    annot, _ = tl_io.load_image_2d(df_row['path_1'])
    img, name = tl_io.load_image_2d(df_row['path_2'])
    assert annot.shape[:2] == img.shape[:2], \
        'image sizes not match %s vs %s' % (repr(annot.shape), repr(img.shape))

    uq_objects = np.unique(annot)
    if len(uq_objects) == 1:
        return

    for idx in uq_objects[1:]:
        img_new = cut_object(img, annot == idx, padding, use_mask, bg_color)
        path_img = os.path.join(path_out, '%s_%i.png' % (name, idx))
        logging.debug('saving image "%s"', path_img)
        Image.fromarray(img_new).save(path_img)


def add_padding(img_size, padding, min_row, min_col, max_row, max_col):
    """ add some padding but still be inside image

    :param (int, int) img_size:
    :param int padding: set padding around segmented object
    :param int min_row: setting top left corner of bounding box
    :param int min_col: setting top left corner of bounding box
    :param int max_row: setting bottom right corner of bounding box
    :param int max_col: setting bottom right corner of bounding box
    :return: int, int, int, int
    """
    min_row = max(0, min_row - padding)
    min_col = max(0, min_col - padding)
    max_row = min(img_size[0], max_row + padding)
    max_col = min(img_size[1], max_col + padding)
    return min_row, min_col, max_row, max_col


def cut_object(img, mask, padding, use_mask=False, bg_color=None):
    """ cut an object fro image according binary object segmentation

    :param ndarray img:
    :param ndarray mask:
    :param int padding: set padding around segmented object
    :return:
    """
    assert mask.shape[:2] == img.shape[:2]

    prop = measure.regionprops(mask.astype(int))[0]
    bg_pixels = np.hstack([mask[0, :], mask[:, 0], mask[-1, :], mask[:, -1]])
    bg_mask = np.argmax(np.bincount(bg_pixels))

    if bg_color is None:
        if img.ndim == 2:
            bg_pixels = np.hstack([img[0, :], img[:, 0],
                                   img[-1, :], img[:, -1]])
            bg_color = np.argmax(np.bincount(bg_pixels))
        else:
            bg_pixels = np.vstack([img[0, :, ...], img[:, 0, ...],
                                   img[-1, :, ...], img[:, -1, ...]])
            bg_color = np.median(bg_pixels, axis=0)
    bg_color = bg_color.astype(img.dtype)

    rotate = np.rad2deg(prop.orientation)
    shift = prop.centroid - (np.array(mask.shape) / 2.)
    shift = np.append(shift, np.zeros(img.ndim - mask.ndim))

    mask = ndimage.interpolation.shift(mask, -shift[:mask.ndim], order=0)
    mask = ndimage.rotate(mask, -rotate, order=0, mode='constant',
                          cval=np.nan)

    img_cut = ndimage.interpolation.shift(img, -shift[:img.ndim], order=0)
    img_cut = ndimage.rotate(img_cut, -rotate, order=0, mode='constant',
                             cval=np.nan)
    img_cut[np.isnan(mask), ...] = bg_color
    mask[np.isnan(mask)] = bg_mask

    prop = measure.regionprops(mask.astype(int))[0]
    min_row, min_col, max_row, max_col = add_padding(img_cut.shape, padding,
                                                     *prop.bbox)
    img_cut = img_cut[min_row:max_row, min_col:max_col, ...]

    if use_mask:
        use_mask = mask[min_row:max_row, min_col:max_col, ...]
        img_cut[~use_mask, ...] = bg_color

    return img_cut


def main(dict_paths, padding=0, use_mask=False, bg_color=None,
         nb_jobs=NB_THREADS):
    """ the main executable

    :param dict_paths:
    :param int padding:
    :param int nb_jobs:
    """
    logging.info('running...')
    if not os.path.isdir(dict_paths['output']):
        assert os.path.isdir(os.path.dirname(dict_paths['output']))
        logging.debug('creating dir: %s', dict_paths['output'])
        os.mkdir(dict_paths['output'])

    list_dirs = [dict_paths['annot'], dict_paths['image']]
    df_paths = tl_io.find_files_match_names_across_dirs(list_dirs)

    logging.info('start cutting images')
    tqdm_bar = tqdm.tqdm(total=len(df_paths))
    wrapper_cutting = partial(export_cut_objects, path_out=dict_paths['output'],
                              padding=padding, use_mask=use_mask, bg_color=bg_color)
    mproc_pool = mproc.Pool(nb_jobs)
    for _ in mproc_pool.imap_unordered(wrapper_cutting,
                                       (row for idx, row in df_paths.iterrows())):
        tqdm_bar.update()
    mproc_pool.close()
    mproc_pool.join()

    logging.info('DONE')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    dict_paths, args = arg_parse_params()
    main(dict_paths, args.padding, args.mask, args.background, args.nb_jobs)
