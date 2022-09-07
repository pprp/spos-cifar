import random
import time
from typing import Dict, List

import torch
import torch.nn.functional as F
from mmcv.cnn import get_model_complexity_info
from torch import Tensor

import pplib.utils.utils as utils
from pplib.core.losses import PairwiseRankLoss
from pplib.evaluator.nb201_evaluator import NB201Evaluator
from pplib.models.nasbench201 import OneShotNASBench201Network
from pplib.nas.mutators import OneShotMutator
from pplib.predictor.pruners.measures.zen import compute_zen_score
from pplib.utils.utils import AvgrageMeter, accuracy
from .base import BaseTrainer
from .registry import register_trainer


class SampleStrategyMixin:

    def _forward_pairwise_loss(self, batch_inputs):
        inputs, labels = batch_inputs
        inputs = self._to_device(inputs, self.device)
        labels = self._to_device(labels, self.device)

        # sample the first subnet
        self.rand_subnet = self.mutator.random_subnet
        self.mutator.set_subnet(self.rand_subnet)
        outputs = self.model(inputs)
        loss1 = self._compute_loss(outputs, labels)
        loss1.backward()
        flops1 = self.get_subnet_flops(self.rand_subnet)

        # sample the second subnet
        self.rand_subnet = self.mutator.random_subnet
        self.mutator.set_subnet(self.rand_subnet)
        outputs = self.model(inputs)
        loss2 = self._compute_loss(outputs, labels)
        loss2.backward(retain_graph=True)
        flops2 = self.get_subnet_flops(self.rand_subnet)

        # pairwise rank loss
        # lambda settings:
        #       1. min(2, self.current_epoch/10.)
        #       2. 2 * np.sin(np.pi * 0.8 * self.current_epoch / self.max_epochs)

        loss3 = self._lambda * self.pairwise_rankloss(flops1, flops2, loss1,
                                                      loss2)
        loss3.backward()

        return loss2, outputs

    def _forward_pairwise_loss_with_distill(self, batch_inputs):
        """
        Policy:
            1. use larger flops model as teacher
            2. use lower loss model as teacher
        """
        inputs, labels = batch_inputs
        inputs = self._to_device(inputs, self.device)
        labels = self._to_device(labels, self.device)

        loss_list = []

        # sample the first subnet
        rand_subnet1 = self.mutator.random_subnet
        self.mutator.set_subnet(rand_subnet1)
        outputs, feat1 = self.model.forward_distill(inputs)
        loss1 = self._compute_loss(outputs, labels)
        flops1 = self.get_subnet_flops(rand_subnet1)
        loss_list.append(loss1)

        # sample the second subnet
        rand_subnet2 = self.mutator.random_subnet
        self.mutator.set_subnet(rand_subnet2)
        outputs, feat2 = self.model.forward_distill(inputs)
        loss2 = self._compute_loss(outputs, labels)
        flops2 = self.get_subnet_flops(rand_subnet2)
        loss_list.append(loss2)

        # pairwise rank loss
        # lambda settings:
        #       1. min(2, self.current_epoch/10.)
        #       2. 2 * np.sin(np.pi * 0.8 * self.current_epoch / self.max_epochs)

        loss3 = self._lambda * self.pairwise_rankloss(flops1, flops2, loss1,
                                                      loss2)
        loss_list.append(loss3)

        # distill loss
        if loss2 > loss1:
            loss4 = self.distill_loss(
                feat_s=feat2, feat_t=feat1) * self.lambda_kd
        else:
            loss4 = self.distill_loss(
                feat_s=feat1, feat_t=feat2) * self.lambda_kd
        loss_list.append(loss4)

        loss = sum(loss_list)
        loss.backward()

        return loss, outputs

    def _forward_multi_pairwise_loss(self, batch_inputs):
        num_pairs = 4

        inputs, labels = batch_inputs
        inputs = self._to_device(inputs, self.device)
        labels = self._to_device(labels, self.device)

        # sample the first subnet
        rand_subnet1 = self.mutator.random_subnet
        self.mutator.set_subnet(rand_subnet1)
        outputs = self.model(inputs)
        loss1 = self._compute_loss(outputs, labels)
        flops1 = self.get_subnet_flops(rand_subnet1)

        subnet_list = []
        loss_list = []
        flops_list = []

        for _ in range(num_pairs):
            rand_subnet = self.mutator.random_subnet
            self.mutator.set_subnet(rand_subnet)
            outputs = self.model(inputs)
            loss = self._compute_loss(outputs, labels)
            flops = self.get_subnet_flops(rand_subnet)

            subnet_list.append(rand_subnet)
            loss_list.append(loss)
            flops_list.append(flops)

        rank_loss_list = []

        for i in range(1, num_pairs):
            for j in range(i):
                flops1, flops2 = flops_list[i], flops_list[j]
                loss1, loss2 = loss_list[i], loss_list[j]
                tmp_rank_loss = self.pairwise_rankloss(flops1, flops2, loss1,
                                                       loss2)

                rank_loss_list.append(tmp_rank_loss)

        sum_loss = sum(loss_list) + sum(rank_loss_list)
        sum_loss.backward()

        return sum_loss, outputs


@register_trainer
class NB201_Balance_Trainer(BaseTrainer, SampleStrategyMixin):
    """Trainer for NB201 with Balanced Sampler

    1. eval experiments. max subnet, mid subet, min subnet

    Args:
        model (nn.Module): _description_
        dataloader (Dict): _description_
        optimizer (_type_): _description_
        criterion (_type_): _description_
        scheduler (_type_): _description_
        epochs (int): _description_
        searching (bool, optional): _description_. Defaults to True.
        num_choices (int, optional): _description_. Defaults to 4.
        num_layers (int, optional): _description_. Defaults to 20.
        device (torch.device, optional): _description_. Defaults to None.
    """

    def __init__(
        self,
        model: OneShotNASBench201Network,
        mutator: OneShotMutator,
        optimizer=None,
        criterion=None,
        scheduler=None,
        device: torch.device = torch.device('cuda'),
        log_name='nasbench201',
        searching: bool = True,
    ):
        super().__init__(
            model=model,
            mutator=mutator,
            criterion=criterion,
            optimizer=optimizer,
            scheduler=scheduler,
            device=device,
            log_name=log_name,
            searching=searching,
        )

        # init flops
        self._init_flops()

        if self.mutator is None:
            # Note: use alias to build search group
            self.mutator = OneShotMutator(with_alias=True)
            self.mutator.prepare_from_supernet(model)

        # evaluate the rank consistency
        # self.evaluator = self._build_evaluator(num_sample=50)

        # pairwise rank loss
        self.pairwise_rankloss = PairwiseRankLoss()

        # record current rand_subnet
        self.rand_subnet = None

        # Forward Specific Subnet flag
        #  => is_specific is True: cooperate with SH
        #  => is_specific is False: normal mode
        self.is_specific = False

        self.max_subnet = {
            0: 'conv_3x3',
            1: 'conv_3x3',
            2: 'conv_3x3',
            3: 'conv_3x3',
            4: 'conv_3x3',
            5: 'conv_3x3'
        }
        self.mid_subnet = {
            0: 'conv_3x3',
            1: 'conv_3x3',
            2: 'conv_1x1',
            3: 'conv_1x1',
            4: 'conv_1x1',
            5: 'conv_1x1'
        }
        self.min_subnet = {
            0: 'conv_3x3',
            1: 'conv_3x3',
            2: 'skip_connect',
            3: 'skip_connect',
            4: 'skip_connect',
            5: 'skip_connect'
        }

    def _build_evaluator(self, num_sample=50):
        return NB201Evaluator(self, num_sample)

    def policy_sampler(self,
                       policy: str = 'balanced',
                       n_samples: int = 3) -> Dict:
        assert policy in ['zenscore', 'flops', 'params']
        n_subnets = [self.mutator.random_subnet for _ in range(n_samples)]

        def minmaxscaler(n_list: Tensor) -> Tensor:
            min_n = torch.min(n_list)
            max_n = torch.max(n_list)
            return (n_list - min_n) / max_n - min_n

        if policy == 'flops':
            n_flops = torch.tensor(
                [self.get_subnet_flops(i) for i in n_subnets])
            res = minmaxscaler(n_flops)
            res = F.softmax(res, dim=0)
            # Find the max
            max_idx = res.argmax()
            # Get corresponding subnet
            subnet = n_subnets[max_idx]

        elif policy == 'params':
            n_params = [self.get_subnet_params(i) for i in n_subnets]
            res = minmaxscaler(n_params)
            res = F.softmax(res, dim=0)
            # Find the max
            max_idx = res.argmax()
            subnet = n_subnets[max_idx]

        elif policy == 'zenscore':
            n_zenscore = [self.get_subnet_zenscore(i) for i in n_subnets]
            res = minmaxscaler(n_zenscore)
            res = F.softmax(res, dim=0)
            # Find the max
            max_idx = res.argmax()
            subnet = n_subnets[max_idx]

        return subnet

    def _generate_fair_lists(self) -> List[Dict]:
        search_group = self.mutator.search_group
        fair_lists = []

        choices_dict = dict()
        num_choices = -1
        for group_id, modules in search_group.items():
            choices = modules[0].choices
            choices_dict[group_id] = random.sample(choices, len(choices))
            num_choices = len(choices)

        for i in range(num_choices):
            current_dict = dict()
            for k, v in choices_dict.items():
                current_dict[k] = v[i]
            fair_lists.append(current_dict)
        return fair_lists

    def _train(self, loader):
        self.model.train()

        train_loss = 0.0
        top1_tacc = AvgrageMeter()
        top5_tacc = AvgrageMeter()

        self.mutator.set_subnet(self.min_subnet)

        for step, batch_inputs in enumerate(loader):
            # get image and labels
            inputs, labels = batch_inputs
            inputs = self._to_device(inputs, self.device)
            labels = self._to_device(labels, self.device)

            # remove gradient from previous passes
            self.optimizer.zero_grad()

            # FairNAS
            # loss, outputs = self._forward_fairnas(batch_inputs)

            # Single Path One Shot
            loss, outputs = self.forward(batch_inputs, mode='loss')
            loss.backward()

            # SPOS with pairwise rankloss
            # loss, outputs = self._forward_pairwise_loss(batch_inputs)

            # spos with pairwise rankloss + cc distill
            # loss, outputs = self._forward_pairwise_loss_with_distill(
            #     batch_inputs)

            # spos with multi-pair rank loss
            # loss, outputs = self._forward_multi_pairwise_loss(batch_inputs)

            # clear grad
            for p in self.model.parameters():
                if p.grad is not None and p.grad.sum() == 0:
                    p.grad = None

            # parameters update
            self.optimizer.step()

            # compute accuracy
            n = inputs.size(0)
            top1, top5 = accuracy(outputs, labels, topk=(1, 5))
            top1_tacc.update(top1.item(), n)
            top5_tacc.update(top5.item(), n)

            # accumulate loss
            train_loss += loss.item()

            # print every 20 iter
            if step % self.print_freq == 0:
                self.logger.info(
                    f'Step: {step:03} Train loss: {loss.item():.4f} Top1 acc: {top1_tacc.avg:.3f} Top5 acc: {top5_tacc.avg:.3f}'
                )
                self.writer.add_scalar(
                    'STEP_LOSS/train_step_loss',
                    loss.item(),
                    global_step=step + self.current_epoch * len(loader),
                )
                self.writer.add_scalar(
                    'TRAIN_ACC/top1_train_acc',
                    top1_tacc.avg,
                    global_step=step + self.current_epoch * len(loader),
                )
                self.writer.add_scalar(
                    'TRAIN_ACC/top5_train_acc',
                    top5_tacc.avg,
                    global_step=step + self.current_epoch * len(loader),
                )

        return train_loss / (step + 1), top1_tacc.avg, top5_tacc.avg

    def _forward(self, batch_inputs):
        """Network forward step. Low Level API"""
        inputs, labels = batch_inputs
        inputs = self._to_device(inputs, self.device)
        labels = self._to_device(labels, self.device)

        if self.is_specific:
            return self.model(inputs)

        # forward pass
        # if self.searching:
        #     self.rand_subnet = self.mutator.random_subnet
        #     self.mutator.set_subnet(self.rand_subnet)
        return self.model(inputs)

    def _predict(self, batch_inputs, subnet_dict: Dict = None):
        """Network forward step. Low Level API"""
        inputs, labels = batch_inputs
        inputs = self._to_device(inputs, self.device)
        labels = self._to_device(labels, self.device)

        if self.is_specific:
            return self.model(inputs), labels

        # forward pass
        # if subnet_dict is None:
        #     self.rand_subnet = self.mutator.random_subnet
        #     self.mutator.set_subnet(self.rand_subnet)
        # else:
        #     self.mutator.set_subnet(subnet_dict)
        return self.model(inputs), labels

    def _validate(self, loader):
        # self.model.eval()

        val_loss = 0.0
        top1_vacc = AvgrageMeter()
        top5_vacc = AvgrageMeter()

        with torch.no_grad():
            for step, batch_inputs in enumerate(loader):
                # move to device
                outputs, labels = self.forward(batch_inputs, mode='predict')

                # compute loss
                loss = self._compute_loss(outputs, labels)

                # compute accuracy
                n = labels.size(0)
                top1, top5 = accuracy(outputs, labels, topk=(1, 5))
                top1_vacc.update(top1.item(), n)
                top5_vacc.update(top5.item(), n)

                # accumulate loss
                val_loss += loss.item()

                # print every 20 iter
                if step % self.print_freq == 0:
                    self.writer.add_scalar(
                        'STEP_LOSS/valid_step_loss',
                        loss.item(),
                        global_step=step + self.current_epoch * len(loader),
                    )
                    self.writer.add_scalar(
                        'VAL_ACC/top1_val_acc',
                        top1_vacc.avg,
                        global_step=step + self.current_epoch * len(loader),
                    )
                    self.writer.add_scalar(
                        'VAL_ACC/top5_val_acc',
                        top5_vacc.avg,
                        global_step=step + self.current_epoch * len(loader),
                    )
            self.logger.info(
                f'Val loss: {val_loss / (step + 1)} Top1 acc: {top1_vacc.avg}'
                f' Top5 acc: {top5_vacc.avg}')
        return val_loss / (step + 1), top1_vacc.avg, top5_vacc.avg

    def fit(self, train_loader, val_loader, epochs):
        """Fits. High Level API
        Fit the model using the given loaders for the given number
        of epochs.
        """
        # track total training time
        total_start_time = time.time()

        # record max epoch
        self.max_epochs = epochs

        # ---- train process ----
        for epoch in range(epochs):
            self.current_epoch = epoch
            # track epoch time
            epoch_start_time = time.time()

            # train
            tr_loss, top1_tacc, top5_tacc = self._train(train_loader)

            # validate
            val_loss, top1_vacc, top5_vacc = self._validate(val_loader)

            # save ckpt
            if epoch % 10 == 0:
                utils.save_checkpoint(
                    {'state_dict': self.model.state_dict()},
                    self.log_name,
                    epoch + 1,
                    tag=f'{self.log_name}_nb201',
                )

            self.train_loss_.append(tr_loss)
            self.val_loss_.append(val_loss)

            epoch_time = time.time() - epoch_start_time

            self.logger.info(
                f'Epoch: {epoch + 1}/{epochs} Time: {epoch_time} Train loss: {tr_loss} Val loss: {val_loss}'  # noqa: E501
            )

            # if epoch % 5 == 0:
            #     assert self.evaluator is not None
            #     kt, ps, sp = self.evaluator.compute_rank_consistency(
            #         val_loader, self.mutator)
            #     self.writer.add_scalar(
            #         'RANK/kendall_tau', kt, global_step=self.current_epoch)
            #     self.writer.add_scalar(
            #         'RANK/pearson', ps, global_step=self.current_epoch)
            #     self.writer.add_scalar(
            #         'RANK/spearman', sp, global_step=self.current_epoch)

            self.writer.add_scalar(
                'EPOCH_LOSS/train_epoch_loss',
                tr_loss,
                global_step=self.current_epoch)
            self.writer.add_scalar(
                'EPOCH_LOSS/valid_epoch_loss',
                val_loss,
                global_step=self.current_epoch)

            self.scheduler.step()

        total_time = time.time() - total_start_time

        # final message
        self.logger.info(
            f"""End of training. Total time: {round(total_time, 5)} seconds""")

    def metric_score(self, loader, subnet_dict: Dict = None):
        # self.model.eval()

        val_loss = 0.0
        top1_vacc = AvgrageMeter()
        top5_vacc = AvgrageMeter()

        with torch.no_grad():
            for step, batch_inputs in enumerate(loader):
                # move to device
                outputs, labels = self._predict(
                    batch_inputs, subnet_dict=subnet_dict)

                # compute loss
                loss = self._compute_loss(outputs, labels)

                # compute accuracy
                n = labels.size(0)
                top1, top5 = accuracy(outputs, labels, topk=(1, 5))
                top1_vacc.update(top1.item(), n)
                top5_vacc.update(top5.item(), n)

                # accumulate loss
                val_loss += loss.item()

                # print every 50 iter
                if step % 50 == 0:
                    self.writer.add_scalar(
                        'STEP_LOSS/valid_step_loss',
                        loss.item(),
                        global_step=step + self.current_epoch * len(loader),
                    )
                    self.writer.add_scalar(
                        'VAL_ACC/top1_val_acc',
                        top1_vacc.avg,
                        global_step=step + self.current_epoch * len(loader),
                    )
                    self.writer.add_scalar(
                        'VAL_ACC/top5_val_acc',
                        top5_vacc.avg,
                        global_step=step + self.current_epoch * len(loader),
                    )
            # self.logger.info(
            #     f'Val loss: {loss.item()}'
            #     f'Top1 acc: {top1_vacc.avg} Top5 acc: {top5_vacc.avg}')

        return top1_vacc.avg

    def _init_flops(self):
        """generate flops."""
        self.model.eval()
        # Note 1: after this process, each module in self.model
        #       would have the __flops__ attribute.
        # Note 2: this function should be called before
        #       mutator.prepare_from_supernet()
        flops, params = get_model_complexity_info(self.model, self.input_shape)
        self.model.train()
        return flops, params

    def get_subnet_params(self, subnet_dict) -> float:
        """Calculate current subnet params based on mmcv."""
        subnet_params = 0
        for k, v in self.mutator.search_group.items():
            current_choice = subnet_dict[k]
            choice_params = 0
            for _, module in v[0]._candidate_ops[current_choice].named_modules(
            ):
                params = getattr(module, '__params__', 0)
                if params > 0:
                    choice_params += params
            subnet_params += choice_params
        return subnet_params

    def get_subnet_flops(self, subnet_dict) -> float:
        """Calculate current subnet flops based on config."""
        subnet_flops = 0
        for k, v in self.mutator.search_group.items():
            current_choice = subnet_dict[k]
            choice_flops = 0
            for _, module in v[0]._candidate_ops[current_choice].named_modules(
            ):
                flops = getattr(module, '__flops__', 0)
                if flops > 0:
                    choice_flops += flops
            # print(f'k: {k} choice: {current_choice} flops: {choice_flops}')
            subnet_flops += choice_flops
        return subnet_flops

    def get_subnet_zenscore(self, subnet_dict) -> float:
        """Calculate zenscore based on subnet dict."""
        import copy
        m = copy.deepcopy(self.model)
        o = OneShotMutator(with_alias=True)
        o.prepare_from_supernet(m)
        o.set_subnet(subnet_dict)

        # for cifar10,cifar100,imagenet16
        score = compute_zen_score(
            net=m, inputs=torch.randn(4, 3, 32, 32), targets=None, repeat=5)
        del m
        del o
        return score

    def get_subnet_error(self,
                         subnet_dict: Dict,
                         train_loader=None,
                         val_loader=None) -> float:
        """Calculate the subnet of validation error.
        Including:
        1. BN calibration
        2. Start test
        """
        # Process dataloader
        assert train_loader is not None
        assert val_loader is not None

        # Info about dataloader
        train_iter = iter(train_loader)
        val_iter = iter(val_loader)
        max_train_iters = 200
        max_test_iters = 40

        self.mutator.set_subnet(subnet_dict)

        # Clear bn statics
        for m in self.model.modules():
            if isinstance(m, torch.nn.BatchNorm2d):
                m.running_mean = torch.zeros_like(m.running_mean)
                m.running_var = torch.ones_like(m.running_var)

        # BN Calibration
        self.model.train()
        for _ in range(max_train_iters):
            data, target = next(train_iter)
            data, target = data.to(self.device), target.to(self.device)
            output = self.model(data)
            del data, target, output

        # Start test
        top1_vacc = AvgrageMeter()
        top5_vacc = AvgrageMeter()

        for _ in range(max_test_iters):
            data, target = next(val_iter)
            data, target = data.to(self.device), target.to(self.device)
            output = self.model(data)
            n = target.size(0)
            top1, top5 = accuracy(output, target, topk=(1, 5))
            top1_vacc.update(top1.item(), n)
            top5_vacc.update(top5.item(), n)

        return 100 - top1_vacc.avg

    def _forward_fairnas(self, batch_inputs):
        """FairNAS Rules."""
        inputs, labels = batch_inputs
        inputs = self._to_device(inputs, self.device)
        labels = self._to_device(labels, self.device)
        fair_dicts = self._generate_fair_lists()

        loss_list = []

        for i in range(len(fair_dicts)):
            self.rand_subnet = fair_dicts[i]
            self.mutator.set_subnet(self.rand_subnet)
            outputs = self.model(inputs)
            loss = self._compute_loss(outputs, labels)
            loss_list.append(loss)

        sum_loss = sum(loss_list)
        sum_loss.backward()
        return sum_loss, outputs