import argparse
import os
import time

import torch

import pplib.utils.utils as utils
from pplib.core import build_criterion, build_optimizer, build_scheduler
from pplib.datasets.build import build_dataloader
from pplib.models import build_model
from pplib.trainer import build_trainer
from pplib.utils import set_random_seed
from pplib.utils.config import Config


def get_args():
    parser = argparse.ArgumentParser('train macro benchmark')
    parser.add_argument(
        '--config',
        type=str,
        default='configs/spos/spos_cifar10.py',
        required=False,
        help='user settings config',
    )
    parser.add_argument(
        '--work_dir', type=str, default='./work_dir', help='experiment name')
    parser.add_argument(
        '--data_dir',
        type=str,
        default='./data/cifar',
        help='path to the dataset')

    parser.add_argument(
        '--seed', type=int, default=20, help='seed of experiments')

    parser.add_argument(
        '--model_name',
        type=str,
        default='OneShotNASBench201Network',
        help='name of model')
    parser.add_argument(
        '--trainer_name',
        type=str,
        default='NB201Trainer',
        help='name of trainer')
    parser.add_argument(
        '--log_name',
        type=str,
        default='NB201Trainer',
        help='name of this experiments',
    )

    # ******************************* settings *******************************#

    parser.add_argument(
        '--crit', type=str, default='ce', help='decide the criterion')
    parser.add_argument(
        '--optims', type=str, default='sgd', help='decide the optimizer')
    parser.add_argument(
        '--sched', type=str, default='cosine', help='decide the scheduler')
    parser.add_argument(
        '--p_lambda', type=float, default=1, help='decide the scheduler')

    parser.add_argument(
        '--classes', type=int, default=10, help='dataset classes')
    parser.add_argument('--layers', type=int, default=20, help='batch size')
    parser.add_argument(
        '--num_choices', type=int, default=4, help='number choices per layer')
    parser.add_argument(
        '--batch_size', type=int, default=256, help='batch size')
    parser.add_argument('--epochs', type=int, default=200, help='batch size')
    parser.add_argument(
        '--lr', type=float, default=0.025, help='initial learning rate')
    parser.add_argument('--momentum', type=float, default=0.9, help='momentum')
    parser.add_argument(
        '--weight-decay', type=float, default=5e-4, help='weight decay')
    parser.add_argument(
        '--val_interval',
        type=int,
        default=5,
        help='validate and save frequency')
    parser.add_argument(
        '--random_search',
        type=int,
        default=1000,
        help='validate and save frequency')
    # ******************************* dataset *******************************#
    parser.add_argument(
        '--dataset', type=str, default='cifar10', help='path to the dataset')
    parser.add_argument('--cutout', action='store_true', help='use cutout')
    parser.add_argument(
        '--cutout_length', type=int, default=16, help='cutout length')
    parser.add_argument(
        '--auto_aug',
        action='store_true',
        default=False,
        help='use auto augmentation')
    parser.add_argument(
        '--resize', action='store_true', default=False, help='use resize')
    # ******************************* extra options *******************************#
    parser.add_argument(
        '--type',
        type=str,
        default='flops',
        help='can be used in the ablation study')
    parser.add_argument(
        '--shrink_times', type=int, default=3, help='shrink times')
    parser.add_argument(
        '--expand_times', type=int, default=6, help='expand times')
    parser.add_argument(
        '--every_n_epochs',
        type=int,
        default=5,
        help='shrink or expand every n times')

    return parser.parse_args()


def main():
    args = get_args()

    # merge argparse and config file
    if args.config is not None:
        cfg = Config.fromfile(args.config)
        cfg.merge_from_dict(vars(args))
    else:
        cfg = Config(args)

    # set envirs
    set_random_seed(cfg.seed, deterministic=True)

    print(cfg)

    # dump config files
    cfg.work_dir = os.path.join(cfg.work_dir, cfg.trainer_name)
    if not os.path.exists(cfg.work_dir):
        os.makedirs(cfg.work_dir)
    current_exp_name = f'{cfg.model_name}-{cfg.trainer_name}-{cfg.log_name}.yaml'
    cfg.dump(os.path.join(cfg.work_dir, current_exp_name))

    if torch.cuda.is_available():
        print('Train on GPU!')
        device = torch.device('cuda')
    else:
        device = torch.device('cpu')

    train_dataloader = build_dataloader(
        type='train', dataset=cfg.dataset, config=cfg)

    val_dataloader = build_dataloader(
        type='val', dataset=cfg.dataset, config=cfg)

    if cfg.dataset == 'cifar10':
        num_classes = 10
    elif cfg.dataset == 'cifar100':
        num_classes = 100
    elif cfg.dataset == 'imagenet16':
        num_classes = 120
    else:
        raise NotImplementedError(
            f'Not Support Type of datasets: {cfg.dataset}.')

    model = build_model(cfg.model_name, num_classes=num_classes)

    criterion = build_criterion(cfg.crit).to(device)
    optimizer = build_optimizer(model, cfg)
    scheduler = build_scheduler(cfg, optimizer)

    model = model.to(device)

    trainer = build_trainer(
        cfg.trainer_name,
        model=model,
        mutator=None,
        optimizer=optimizer,
        criterion=criterion,
        scheduler=scheduler,
        searching=True,
        device=device,
        log_name=cfg.log_name,
        # kwargs
        type=cfg.type,
        shrink_times=cfg.shrink_times,
        expand_times=cfg.expand_times,
        every_n_times=cfg.every_n_epochs,
    )

    start = time.time()

    trainer.fit(train_dataloader, val_dataloader, cfg.epochs)

    utils.time_record(start)


if __name__ == '__main__':
    main()