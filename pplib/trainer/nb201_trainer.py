from typing import Dict

import torch

from pplib.models.nasbench201 import OneShotNASBench201Network
from pplib.nas.mutators import OneShotMutator
from pplib.utils.utils import AvgrageMeter, accuracy
from .base import BaseTrainer


class NB201Trainer(BaseTrainer):
    """Trainer for Macro Benchmark.

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
        log_name='macro',
        searching: bool = True,
    ):
        super().__init__(model, mutator, criterion, optimizer, scheduler,
                         device, log_name, searching)

    def _forward(self, batch_inputs):
        """Network forward step. Low Level API"""
        inputs, labels = batch_inputs
        inputs = self._to_device(inputs, self.device)
        labels = self._to_device(labels, self.device)

        # forward pass
        if self.searching is True:
            rand_subnet = self.mutator.random_subnet
            self.mutator.set_subnet(rand_subnet)
        return self.model(inputs)

    def _predict(self, batch_inputs, subnet_dict: Dict = None):
        """Network forward step. Low Level API"""
        inputs, labels = batch_inputs
        inputs = self._to_device(inputs, self.device)
        labels = self._to_device(labels, self.device)
        # forward pass
        if self.searching:
            rand_subnet = self.mutator.random_subnet
            self.mutator.set_subnet(rand_subnet)
        else:
            self.mutator.set_subnet(subnet_dict)
        return self.model(inputs)

    def metric_score(self, loader, subnet_dict: Dict = None):
        self.model.eval()

        val_loss = 0.0
        top1_vacc = AvgrageMeter()
        top5_vacc = AvgrageMeter()

        with torch.no_grad():
            for step, batch_inputs in enumerate(loader):
                inputs, labels = batch_inputs
                inputs = self._to_device(inputs, self.device)
                labels = self._to_device(labels, self.device)

                # move to device
                outputs = self._predict(batch_inputs, subnet_dict=subnet_dict)

                # compute loss
                loss = self._compute_loss(outputs, labels)

                # compute accuracy
                n = inputs.size(0)
                top1, top5 = accuracy(outputs, labels, topk=(1, 5))
                top1_vacc.update(top1.item(), n)
                top5_vacc.update(top5.item(), n)

                # accumulate loss
                val_loss += loss.item()

                # print every 20 iter
                if step % 20 == 0:
                    self.logger.info(
                        f'Step: {step} \t Val loss: {loss.item()} Top1 acc: {top1_vacc.avg} Top5 acc: {top5_vacc.avg}'
                    )
                    self.writer.add_scalar(
                        'val_step_loss',
                        loss.item(),
                        global_step=step + self.current_epoch * len(loader))
                    self.writer.add_scalar(
                        'top1_val_acc',
                        top1_vacc.avg,
                        global_step=step + self.current_epoch * len(loader))
                    self.writer.add_scalar(
                        'top5_val_acc',
                        top5_vacc.avg,
                        global_step=step + self.current_epoch * len(loader))

        return val_loss / (step + 1), top1_vacc.avg, top5_vacc.avg
