import codecs
import json
import logging
import os
import time

import numpy as np
import torch

from nanonas.datasets import build_dataloader
from nanonas.nas.search_spaces.core.query_metrics import Metric
from nanonas.utils import utils

logger = logging.getLogger(__name__)


class ZeroCostPredictorEvaluator(object):
    """
    Evaluates a predictor.
    """

    def __init__(self, predictor, zc_api=None, config=None, log_results=True):
        self.predictor = predictor
        self.config = config
        self.test_size = config.test_size
        self.dataset = config.dataset
        self.metric = Metric.VAL_ACCURACY
        self.device = torch.device(
            'cuda:0' if torch.cuda.is_available() else 'cpu')
        self.results = [config]

        self.test_data_file = config.test_data_file
        self.log_results_to_json = log_results
        self.zc_api = zc_api

    def adapt_search_space(self,
                           search_space,
                           load_labeled=False,
                           scope=None,
                           dataset_api=None):
        self.search_space = search_space.clone()
        self.scope = scope if scope else search_space.OPTIMIZER_SCOPE
        self.predictor.set_ss_type(self.search_space.get_type())
        self.load_labeled = load_labeled
        self.dataset_api = dataset_api

    def get_full_arch_info(self, arch):
        """
        Given an arch, return the accuracy, train_time,
        and also a dict of extra info if required by the predictor
        """
        info_dict = {}
        accuracy = arch.query(
            metric=self.metric,
            dataset=self.dataset,
            dataset_api=self.dataset_api)
        train_time = arch.query(
            metric=Metric.TRAIN_TIME,
            dataset=self.dataset,
            dataset_api=self.dataset_api)
        return accuracy, train_time, info_dict

    def load_dataset_from_file(self, datapath, size):
        with open(datapath) as f:
            data = json.load(f)

        xdata = []
        ydata = []

        for i, x in enumerate(data):
            if i >= size:
                break

            arch = x['arch']
            acc = x['accuracy']

            xdata.append(arch)
            ydata.append(acc)

        return [xdata, ydata, None, None]

    def load_dataset(self, load_labeled=False, data_size=10):
        """
        There are two ways to load an architecture.
        load_labeled=False: sample a random architecture from the search space.
        This works on NAS benchmarks where we can query any architecture (nasbench201/301)
        load_labeled=True: sample a random architecture from a set of evaluated architectures.
        When we only have data on a subset of the search space (e.g., the set of 5k DARTS
        architectures that have the full training info).

        After we load an architecture, query the final val accuracy.
        If the predictor requires extra info such as partial learning curve info, query that too.
        """
        xdata = []
        ydata = []
        info = []
        train_times = []
        while len(xdata) < data_size:
            if not load_labeled:
                graph = self.search_space.clone()
                graph.sample_random_architecture(dataset_api=self.dataset_api)
            else:
                self.search_space.sample_random_architecture(
                    dataset_api=self.dataset_api, load_labeled=True)

            encoding = self.search_space.get_hash()
            accuracy = self.zc_api[str(encoding)]['val_accuracy']
            # accuracy, train_time, info_dict = self.get_full_arch_info(graph)

            xdata.append(encoding)
            ydata.append(accuracy)
            # info.append(info_dict)
            # train_times.append(train_time)

        return [xdata, ydata, info, train_times]

    def single_evaluate(self, test_data, zc_api):
        """
        Evaluate the predictor.
        """
        xtest, ytest, test_info, _ = test_data
        test_pred = []

        logger.info('Querying the predictor')
        query_time_start = time.time()

        test_loader = build_dataloader(type='val', dataset=self.dataset)
        # _, _, test_loader, _, _ = utils.get_train_val_loaders(self.config)

        # Iterate over the architectures, instantiate a graph with each architecture
        # and then query the predictor for the performance of that
        for arch in xtest:
            pred = zc_api[str(arch)][self.predictor.method_type]['score']

            if float('-inf') == pred:
                pred = -1e9
            elif float('inf') == pred:
                pred = 1e9

            test_pred.append(pred)

        test_pred = np.array(test_pred)
        query_time_end = time.time()

        # If the predictor is an ensemble, take the mean
        if len(test_pred.shape) > 1:
            test_pred = np.mean(test_pred, axis=0)

        logger.info('Compute evaluation metrics')
        results_dict = utils.compute_scores(ytest, test_pred)
        results_dict['query_time'] = (query_time_end -
                                      query_time_start) / len(xtest)

        method_type = self.predictor.method_type
        logger.info('dataset: {}, predictor: {}, kendalltau {}'.format(
            self.dataset, method_type, np.round(results_dict['kendalltau'],
                                                4)))

        # print entire results dict:
        print_string = ''
        for key in results_dict:
            if type(results_dict[key]) not in [str, set, bool]:
                # todo: serialize other types
                print_string += key + ': {}, '.format(
                    np.round(results_dict[key], 4))
        logger.info(print_string)
        self.results.append(results_dict)

    def load_test_data(self):
        if self.test_data_file is not None:
            logger.info('Loading the test set from file')
            test_data = self.load_dataset_from_file(self.test_data_file,
                                                    self.test_size)
        else:
            logger.info('Sampling from search space...')
            test_data = self.load_dataset(
                load_labeled=self.load_labeled, data_size=self.test_size)

        return test_data

    def evaluate(self, zc_api):
        self.predictor.pre_process()
        test_data = self.load_test_data()
        self.single_evaluate(test_data, zc_api)

        if self.log_results_to_json:
            self._log_to_json()

        return self.results

    def _log_to_json(self):
        """log statistics to json file"""
        if not os.path.exists(self.config.save):
            os.makedirs(self.config.save)
        with codecs.open(
                os.path.join(self.config.save, 'scores.json'),
                'w',
                encoding='utf-8') as file:
            for res in self.results:
                for key, value in res.items():
                    if type(value) == np.int32 or type(value) == np.int64:
                        res[key] = int(value)
                    if type(value) == np.float32 or type(value) == np.float64:
                        res[key] = float(value)

            json.dump(self.results, file, separators=(',', ':'))

    def get_arch_as_string(self, arch):
        if self.search_space.get_type() == 'nasbench301':
            str_arch = str(list((list(arch[0]), list(arch[1]))))
        else:
            str_arch = str(arch)
        return str_arch