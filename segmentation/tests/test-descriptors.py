"""
Unit testing for particular segmentation module

Copyright (C) 2014-2017 Jiri Borovec <jiri.borovec@fel.cvut.cz>
"""

import os
import sys
import time
import logging
import unittest

import numpy as np
from skimage import draw, transform
import matplotlib.pyplot as plt

sys.path.append(os.path.abspath(os.path.join('..', '..')))  # Add path to root
import segmentation.utils.data_samples as d_spl
import segmentation.utils.data_io as tl_io
import segmentation.utils.drawing as tl_visu
import segmentation.descriptors as seg_fts
import segmentation.superpixels as seg_spx

# angular step for Ray features
ANGULAR_STEP = 15
# size of subfigure for visualise the Filter bank
SUBPLOT_SIZE_FILTER_BANK = 3
PATH_OUTPUT = os.path.abspath(tl_io.update_path('output'))
PATH_FIGURES_RAY = os.path.join(PATH_OUTPUT, 'test_ray_features')
# create the folder for visualisations
if not os.path.exists(PATH_FIGURES_RAY):
    os.mkdir(PATH_FIGURES_RAY)


def export_ray_results(seg, center, points, ray_dist_raw, ray_dist, name):
    """ export result from Ray features extractions

    :param ndarray seg: segmentation
    :param (int, int) center: center of the Ray features
    :param [[int, int]] points: list of reconstructed points
    :param [[int]] ray_dist_raw: list of raw Ray distances in regular step
    :param [[int]] ray_dist: list of normalised Ray distances in regular step
    :param str name: name of particular figure
    """
    fig = tl_visu.figure_ray_feature(seg, center, ray_dist_raw=ray_dist_raw,
                                     ray_dist=ray_dist,
                                     points_reconst=points)
    fig.savefig(os.path.join(PATH_FIGURES_RAY, name))
    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
        plt.show()
    plt.close(fig)


class TestFeatures(unittest.TestCase):

    def test_features_rgb(self):
        im, seg = d_spl.sample_color_image_rand_segment()
        # Cython
        logging.info('running Cython code...')
        start = time.time()
        f = seg_fts.cython_img2d_color_mean(im, seg)
        logging.info('time elapsed: {}'.format(time.time() - start))
        logging.debug(repr(f))
        # Python / Numba
        # logger.info('running Python code...')
        # start = time.time()
        # f = computeColourMeanRGB(im, seg)
        # logger.info('time elapsed: {}'.format(time.time() - start))
        # logger.debug(repr(f))

    def test_filter_banks(self, ax_size=SUBPLOT_SIZE_FILTER_BANK):
        filters, names = seg_fts.create_filter_bank_lm_2d()
        l_max, w_max = len(filters), max([f.shape[0] for f in filters])
        fig, axarr = plt.subplots(l_max, w_max,
                                  figsize=(w_max * ax_size, l_max * ax_size))
        for i in range(l_max):
            f = filters[i]
            for j in range(f.shape[0]):
                axarr[i, j].set_title(names[i][j])
                axarr[i, j].imshow(f[j, :, :], cmap=plt.cm.gray)
        fig.tight_layout(pad=0.1, w_pad=0.1, h_pad=0.1)
        fig.savefig(os.path.join(PATH_OUTPUT, 'test_filter_banks.png'))
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
            plt.show()
        plt.close(fig)

    def test_ray_features_circle(self):
        seg = np.ones((400, 600), dtype=bool)
        x, y = draw.circle(200, 250, 100, shape=seg.shape)
        seg[x, y] = False

        points = [(200, 250), (150, 200), (250, 200), (250, 300)]
        for i, point in enumerate(points):
            ray_dist_raw = seg_fts.compute_ray_features_segm_2d(
                                    seg, point, angle_step=ANGULAR_STEP)
            ray_dist, shift = seg_fts.shift_ray_features(ray_dist_raw)
            points = seg_fts.reconstruct_ray_features_2d(point, ray_dist, shift)
            export_ray_results(seg, point, points, ray_dist_raw, ray_dist,
                               'circle-%i.png' % i)

    def test_ray_features_ellipse(self):
        seg = np.ones((400, 600), dtype=bool)
        x, y = draw.ellipse(200, 250, 120, 200, rotation=np.deg2rad(30),
                            shape=seg.shape)
        seg[x, y] = False

        points = [(200, 250), (150, 200), (250, 300)]
        for i, point in enumerate(points):
            ray_dist_raw = seg_fts.compute_ray_features_segm_2d(
                                    seg, point, angle_step=ANGULAR_STEP)
            # ray_dist, shift = seg_fts.shift_ray_features(ray_dist_raw)
            points = seg_fts.reconstruct_ray_features_2d(point, ray_dist_raw)
            export_ray_results(seg, point, points, ray_dist_raw, [],
                               'ellipse-%i.png' % i)

    def test_ray_features_circle_down_edge(self):
        seg = np.zeros((400, 600), dtype=bool)
        x, y = draw.circle(200, 250, 150, shape=seg.shape)
        seg[x, y] = True
        points = [(200, 250), (150, 200), (250, 200), (250, 300)]

        for i, point in enumerate(points):
            ray_dist_raw = seg_fts.compute_ray_features_segm_2d(
                        seg, point, angle_step=ANGULAR_STEP, edge='down')
            ray_dist, shift = seg_fts.shift_ray_features(ray_dist_raw)
            points = seg_fts.reconstruct_ray_features_2d(point, ray_dist, shift)
            export_ray_results(seg, point, points, ray_dist_raw, ray_dist,
                               'circle_e-down-A-%i.png' % i)

        x, y = draw.circle(200, 250, 120, shape=seg.shape)
        seg[x, y] = False

        for i, point in enumerate(points):
            ray_dist_raw = seg_fts.compute_ray_features_segm_2d(
                        seg, point, angle_step=ANGULAR_STEP, edge='down')
            ray_dist, shift = seg_fts.shift_ray_features(ray_dist_raw)
            points = seg_fts.reconstruct_ray_features_2d(point, ray_dist, shift)
            export_ray_results(seg, point, points, ray_dist_raw, ray_dist,
                               'circle_e-down-B-%i.png' % i)

    def test_ray_features_polygon(self):
        seg = np.ones((400, 600), dtype=bool)
        x, y = draw.polygon(np.array([50, 170, 300, 250, 150, 150, 50]),
                            np.array([100, 270, 240, 150, 150, 80, 50]),
                            shape=seg.shape)
        seg[x, y] = False

        centres = [(150, 200), (200, 250), (250, 200), (120, 100)]
        for i, point in enumerate(centres):
            ray_dist_raw = seg_fts.compute_ray_features_segm_2d(
                                    seg, point, angle_step=ANGULAR_STEP)
            ray_dist, shift = seg_fts.shift_ray_features(ray_dist_raw)
            points = seg_fts.reconstruct_ray_features_2d(point, ray_dist, shift)
            export_ray_results(seg, point, points, ray_dist_raw, ray_dist,
                               'polygon-%i.png' % i)

    def test_show_image_features_clr2d(self):
        img = d_spl.load_sample_image(d_spl.IMAGE_LENNA)
        img = transform.resize(img, (128, 128))
        slic = seg_spx.segment_slic_img2d(img, sp_size=10,
                                          rltv_compact=0.2)

        features, names = seg_fts.compute_selected_features_color2d(
                                         img, slic, seg_fts.FEATURES_SET_ALL)

        path_dir = os.path.join(PATH_OUTPUT, 'test_image_rgb2d_features')
        if not os.path.exists(path_dir):
            os.mkdir(path_dir)

        for i in range(features.shape[1]):
            fts = features[:, i]
            im_fts = fts[slic]
            plt.imsave(os.path.join(path_dir, names[i] + '.png'), im_fts)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
