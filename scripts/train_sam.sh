#!/bin/bash


PYTHONPATH="$(dirname $0)/..":$PYTHONPATH \

echo "Workingdir: $PWD";
echo "Started at $(date)";
start=`date +%s`


CUDA_VISIBLE_DEVICES=0 python tools/train.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench201Network --trainer_name NB201_SAM_Trainer --log_name sam_nb201_spos_sam_exp4.0 --dataset cifar10 --crit ce --lr 0.025 --type uniform --optim sam



end=`date +%s`
runtime=$((end-start))

echo Runtime: $runtime