import math
from collections import namedtuple
from typing import List, Union

import torch
from torch import Tensor

from pplib.evaluator.base import Evaluator
from pplib.nas.mutators import DiffMutator, OneShotMutator
# from pplib.predictor.pruners.measures.synflow import compute_synflow_per_weight
from pplib.predictor.pruners.measures.zen import compute_zen_score
from pplib.utils.get_dataset_api import get_dataset_api
from pplib.utils.rank_consistency import kendalltau, pearson, spearman

Genotype = namedtuple('Genotype', 'normal normal_concat reduce reduce_concat')


class NB301Evaluator(Evaluator):
    """Evaluate the NB301 Benchmark

    Args:
        trainer (NB301Trainer): _description_
        num_sample (int, optional): _description_. Defaults to None.
        search_space (str, optional): _description_. Defaults to 'nasbench301'.
        dataset (str, optional): _description_. Defaults to 'cifar10'.
        type (str, optional): _description_. Defaults to 'eval_acc1es'.
    """

    def __init__(self,
                 trainer,
                 num_sample: int = None,
                 dataset: str = 'cifar10',
                 type: str = 'eval_acc1es'):
        super().__init__(trainer=trainer, dataset=dataset)
        self.trainer = trainer
        self.num_sample = num_sample
        self.type = type
        self.search_space = 'nasbench301'
        self.dataset = dataset

        if dataset == 'imagenet16':
            self.dataset = 'ImageNet16-120'

        assert type in ['train_losses', 'eval_losses',
                        'train_acc1es', 'eval_acc1es', 'cost_info'], \
            f'Not support type {type}.'
        """
        The key of api is the genotype of nb301
            such as '|avg_pool_3x3~0|+
                     |nor_conv_1x1~0|skip_connect~1|+
                     |nor_conv_1x1~0|skip_connect~1|skip_connect~2|'
        The value of api is also a dict:
                  key: cifar10-valid
                  value: train_losses, eval_losses, train_acc1es
                         eval_acc1es, cost_info
        """
        self.api = self.load_benchmark()
        self.performance_model = self.api[0]
        self.runtime_model = self.api[1]

    def load_benchmark(self):
        """load benchmark to get api controller."""
        api = get_dataset_api(self.search_space, self.dataset)
        return api['nb301_model']

    def generate_genotype(self, subnet_dict: dict,
                          mutator: Union[OneShotMutator, DiffMutator]) -> str:
        """subnet_dict represent the subnet dict of mutator."""
        # Please make sure that the mutator have been called the
        # `prepare_from_supernet` function.
        alias2group_id = mutator.alias2group_id
        mapping = {
            'conv_3x3': 'nor_conv_3x3',
            'skip_connect': 'skip_connect',
            'conv_1x1': 'nor_conv_1x1',
            'avg_pool_3x3': 'avg_pool_3x3',
            'none': 'none',
        }

        genotype = Genotype(
            normal=[],
            normal_concat=[2, 3, 4, 5],
            reduce=[],
            reduce_concat=[2, 3, 4, 5],
        )
        # genotype = ''
        # for i, (k, v) in enumerate(subnet_dict.items()):
        #     # v = 'conv_3x3'
        #     mapped_op_name = mapping[v]
        #     alias_name = list(alias2group_id.keys())[k]
        #     rank = alias_name.split('_')[1][-1]  # 0 or 1 or 2
        #     genotype += '|'
        #     genotype += f'{mapped_op_name}~{rank}'
        #     genotype += '|'
        #     if i in [0, 2]:
        #         genotype += '+'
        # genotype = genotype.replace('||', '|')
        return genotype

    def query_result(self, genotype: str, cost_key: str = 'flops'):
        """query the indictor by genotype."""
        dataset = self.trainer.dataset
        if dataset == 'cifar10':
            dataset = 'cifar10-valid'
        else:
            raise NotImplementedError(f'Not Support dataset type:{dataset}')

        # TODO default datasets is cifar10, support other dataset in the future.
        if self.type in [
                'train_losses', 'eval_losses', 'train_acc1es', 'eval_acc1es'
        ]:
            return self.api[genotype][dataset][self.type][-1]
        elif self.type == 'cost_info':
            # example:
            # cost_info: {'flops': 78.56193, 'params': 0.559386,
            #             'latency': 0.01493, 'train_time': 10.21598}
            assert cost_key is not None
            return self.api[genotype][dataset][self.type][cost_key]
        else:
            raise f'Not supported type: {self.type}.'

    def compute_rank_consistency(self, dataloader,
                                 mutator: OneShotMutator) -> List:
        """compute rank consistency of different types of indicators."""
        true_indicator_list: List[float] = []
        generated_indicator_list: List[float] = []

        self.trainer.logger.info('Begin to compute rank consistency...')
        num_sample = 50 if self.num_sample is None else self.num_sample

        for _ in range(num_sample):
            # sample random subnet by mutator
            random_subnet_dict_ = mutator.random_subnet

            # process for search space shrink and expand
            random_subnet_dict = dict()
            for k, v in random_subnet_dict_.items():
                random_subnet_dict[k] = v.rstrip('_')

            # get true indictor by query nb301 api
            genotype = self.generate_genotype(random_subnet_dict, mutator)
            results = self.query_result(genotype)  # type is eval_acc1es
            true_indicator_list.append(results)

            # get score based on supernet
            results = self.trainer.metric_score(dataloader, random_subnet_dict)
            generated_indicator_list.append(results)

        kt = kendalltau(true_indicator_list, generated_indicator_list)
        ps = pearson(true_indicator_list, generated_indicator_list)
        sp = spearman(true_indicator_list, generated_indicator_list)

        print(
            f"Kendall's tau: {kt}, pearson coeff: {ps}, spearman coeff: {sp}.")

        return kt, ps, sp

    def compute_rank_by_flops(self) -> List:
        """compute rank consistency based on flops."""
        true_indicator_list: List[float] = []
        generated_indicator_list: List[float] = []

        self.trainer.logger.info('Begin to compute rank consistency...')
        num_sample = 50 if self.num_sample is None else self.num_sample

        for _ in range(num_sample):
            # sample random subnet by mutator
            random_subnet_dict = self.trainer.mutator.random_subnet

            # get true indictor by query nb301 api
            genotype = self.generate_genotype(random_subnet_dict,
                                              self.trainer.mutator)
            results = self.query_result(genotype)  # type is eval_acc1es
            true_indicator_list.append(results)

            # get score based on flops
            tmp_type = self.type
            self.type = 'cost_info'
            results = self.query_result(genotype, cost_key='flops')
            generated_indicator_list.append(results)
            self.type = tmp_type

        kt = kendalltau(true_indicator_list, generated_indicator_list)
        ps = pearson(true_indicator_list, generated_indicator_list)
        sp = spearman(true_indicator_list, generated_indicator_list)

        print(
            f"Kendall's tau: {kt}, pearson coeff: {ps}, spearman coeff: {sp}.")

        return kt, ps, sp

    def query_zerometric(self, subnet_cfg: dict) -> float:
        self.trainer.mutator.set_subnet(subnet_cfg)
        zenscore = compute_zen_score(
            self.trainer.model,
            inputs=torch.randn(4, 3, 32, 32).to(self.trainer.device),
            targets=None,
            repeat=5)
        return zenscore

    def compute_rank_by_zerometric(self) -> List:
        """compute rank consistency based on flops."""
        true_indicator_list: List[float] = []
        generated_indicator_list: List[float] = []

        self.trainer.logger.info('Begin to compute rank consistency...')
        num_sample = 50 if self.num_sample is None else self.num_sample

        self.trainer.mutator.prepare_from_supernet(self.trainer.model)

        for _ in range(num_sample):
            # sample random subnet by mutator
            random_subnet_dict = self.trainer.mutator.random_subnet

            # get true indictor by query nb301 api
            genotype = self.generate_genotype(random_subnet_dict,
                                              self.trainer.mutator)
            results = self.query_result(genotype)  # type is eval_acc1es
            true_indicator_list.append(results)

            # get score based on zenscore
            self.trainer.mutator.set_subnet(random_subnet_dict)
            score = compute_zen_score(
                self.trainer.model,
                inputs=torch.randn(4, 3, 32, 32).to(self.trainer.device),
                targets=None,
                repeat=5)

            # ***************************************************** #
            # score_list = compute_synflow_per_weight(
            #     self.trainer.model,
            #     inputs=torch.randn(4, 3, 32, 32).to(self.trainer.device),
            #     targets=None,
            #     mode='other',
            # )
            # result_list = []

            # for score in score_list:
            #     result_list.append(score.sum())
            # score = sum(result_list)

            # ****************************************************** #

            print(f'score: {score:.2f} geno: {genotype} type: {type(score)}')
            if math.isnan(score) or math.isinf(score):
                generated_indicator_list.append(0)
            else:
                if isinstance(score, Tensor):
                    generated_indicator_list.append(
                        score.cpu().detach().numpy())
                else:
                    generated_indicator_list.append(score)

        kt = kendalltau(true_indicator_list, generated_indicator_list)
        ps = pearson(true_indicator_list, generated_indicator_list)
        sp = spearman(true_indicator_list, generated_indicator_list)

        print(
            f"Kendall's tau: {kt}, pearson coeff: {ps}, spearman coeff: {sp}.")

        return kt, ps, sp

    def compute_rank_based_on_nwot(self) -> List:
        """compute rank consistency based on nwot."""
        true_indicator_list: List[float] = []
        generated_indicator_list: List[float] = []

        self.trainer.logger.info('Begin to compute rank consistency...')
        num_sample = 50 if self.num_sample is None else self.num_sample

        self.trainer.mutator.prepare_from_supernet(self.trainer.model)

        for _ in range(num_sample):
            # sample random subnet by mutator
            random_subnet_dict = self.trainer.mutator.random_subnet

            # get true indictor by query nb301 api
            genotype = self.generate_genotype(random_subnet_dict,
                                              self.trainer.mutator)
            results = self.query_result(genotype)  # type is eval_acc1es
            true_indicator_list.append(results)

            # get score based on zenscore
            score = self.trainer.get_subnet_nwot(random_subnet_dict)

            print(f'score: {score:.2f} geno: {genotype} type: {type(score)}')
            if math.isnan(score) or math.isinf(score):
                generated_indicator_list.append(0)
            else:
                if isinstance(score, Tensor):
                    generated_indicator_list.append(
                        score.cpu().detach().numpy())
                else:
                    generated_indicator_list.append(score)

        kt = kendalltau(true_indicator_list, generated_indicator_list)
        ps = pearson(true_indicator_list, generated_indicator_list)
        sp = spearman(true_indicator_list, generated_indicator_list)

        print(
            f"Kendall's tau: {kt}, pearson coeff: {ps}, spearman coeff: {sp}.")

        return kt, ps, sp
