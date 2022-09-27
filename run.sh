#!/usr/bin/env sh

NUM_GPUS=1

MKL_NUM_THREADS=4
OMP_NUM_THREADS=1

# srun --partition=mm_model \
#     --job-name=autoformer_reimplement \
#     --gres=gpu:$NUM_GPUS \
#     --ntasks=$NUM_GPUS \
#     --ntasks-per-node=$NUM_GPUS \
#     --cpus-per-task=$NUM_GPUS \
#     --kill-on-bad-exit=1 \
#     --quotatype=auto \
#     --async \
#     python

# NATS MAE
# CUDA_VISIBLE_DEVICES=1 python tools/train.py --config configs/spos/spos_cifar10.py --model_name MAESupernetNATS --trainer_name NATSMAETrainer --log_name nats_mae_spos --work_dir ./work_dir --crit mse --dataset simmim

# CUDA_VISIBLE_DEVICES=1 python tools/train.py --config configs/spos/spos_cifar10.py --model_name MAESupernetNATS --trainer_name NATSMAETrainer --log_name nats_mae_autoslim --work_dir ./work_dir --crit mse --dataset simmim

# CUDA_VISIBLE_DEVICES=2 python tools/train.py --config configs/spos/spos_cifar10.py --model_name MAESupernetNATS --trainer_name NATSMAETrainer --log_name nats_mae_fairnas --work_dir ./work_dir --crit mse --dataset simmim

# CUDA_VISIBLE_DEVICES=3 python tools/train.py --config configs/spos/spos_cifar10.py --model_name MAESupernetNATS --trainer_name NATSMAETrainer --log_name nats_mae_autoslim_cc --work_dir ./work_dir --crit mse --dataset simmim


# NATS
# CUDA_VISIBLE_DEVICES=2 python tools/train.py --config configs/spos/spos_cifar10.py --model_name SupernetNATS --trainer_name NATSTrainer --log_name nats_fairnas_fixevalbug --dataset cifar10 --crit ce --epochs 200

# SPOS
# CUDA_VISIBLE_DEVICES=1 python tools/train.py --config configs/spos/spos_cifar10.py --model_name SearchableShuffleNetV2 --trainer_name SPOSTrainer --log_name spos --dataset cifar10



# SPOS MAE
# CUDA_VISIBLE_DEVICES=1 python tools/train.py --config configs/spos/spos_cifar10.py --model_name SearchableMAE --trainer_name MAETrainer --log_name spos --dataset simmim --crit mse

# MACRO
# fairnas
# CUDA_VISIBLE_DEVICES=3 python tools/train.py --config configs/spos/spos_cifar10.py --model_name MacroBenchmarkSuperNet --trainer_name MacroTrainer --dataset cifar10 --log_name macro_fairnas --work_dir ./work_dir --crit ce

# spos
# CUDA_VISIBLE_DEVICES=4 python tools/train.py --config configs/spos/spos_cifar10.py --model_name MacroBenchmarkSuperNet --trainer_name MacroTrainer --dataset cifar10 --log_name macro_spos --work_dir ./work_dir --crit ce

# spos + pairwise rank loss
# warmup : min(2, self.current_epoch/10.)
# cosine : 2 * np.sin(np.pi * 0.8 * self.current_epoch / self.max_epochs)
# CUDA_VISIBLE_DEVICES=9 python tools/train.py --config configs/spos/spos_cifar10.py --model_name MacroBenchmarkSuperNet --trainer_name MacroTrainer --dataset cifar10 --log_name macro_pairwise_cosine_cc --work_dir ./work_dir --crit ce

# spos + multi_pairwise rank loss
# CUDA_VISIBLE_DEVICES=1 python tools/train.py --config configs/spos/spos_cifar10.py --model_name MacroBenchmarkSuperNet --trainer_name MacroTrainer --dataset cifar10 --log_name macro_multi_pairwise_cosine --work_dir ./work_dir --crit ce


# EVAL MACRO FLOPS
# python tools/eval_rank.py --config configs/spos/spos_cifar10.py --model_name MacroBenchmarkSuperNet --trainer_name MacroTrainer --dataset cifar10 --log_name macro_eval_flops --work_dir ./work_dir --crit ce


# NB201
# CUDA_VISIBLE_DEVICES=1 python tools/train.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench201Network --trainer_name NB201Trainer --log_name nb201_spos_higher_lr --dataset cifar10 --crit ce --lr 0.05

# CUDA_VISIBLE_DEVICES=1 python tools/train.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench201Network --trainer_name NB201Trainer --log_name nb201_spos_w_sc --dataset cifar10 --crit ce --lr 0.025


# Test NB201 Darts algorithm
# CUDA_VISIBLE_DEVICES=0 python tools/train_darts.py --config configs/spos/spos_cifar10.py --model_name DiffNASBench201Network --trainer_name Darts_Trainer --log_name test_nb201_darts_test_exp0.0 --dataset cifar10 --crit ce --lr 0.025 --epochs 50

# Test NB201 with Different sampling Strategy
# CUDA_VISIBLE_DEVICES=2 python tools/train.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench201Network --trainer_name NB201_Balance_Trainer --log_name graduate_nb201_spos_uniformsampling_exp3.0 --dataset cifar10 --crit ce --lr 0.025

# # 第五章 实验2.1 macro benchmark + hamming type
# CUDA_VISIBLE_DEVICES=1 python tools/train.py --config configs/spos/spos_cifar10.py --model_name MacroBenchmarkSuperNet --trainer_name MacroTrainer --log_name graduate_macro_pairwise_hammingtype_exp2.1 --dataset cifar10 --crit ce --lr 0.025

# 第五章 实验2.2 macro benchmark + adaptive hamming type
# CUDA_VISIBLE_DEVICES=1 python tools/train.py --config configs/spos/spos_cifar10.py --model_name MacroBenchmarkSuperNet --trainer_name MacroTrainer --log_name graduate_macro_pairwise_adaptivetype_exp2.2 --dataset cifar10 --crit ce --lr 0.025

# shrink trainer

# CUDA_VISIBLE_DEVICES=1 python tools/train.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench201Network --trainer_name NB201ShrinkTrainer --log_name test_shrink_trainer --dataset cifar10 --crit ce --lr 0.025 --type random

# test nb301 trainer
# python tools/train.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench301Network --trainer_name NB301Trainer --log_name test_nb301_trainer --dataset cifar10 --crit ce --lr 0.025 --type random

# TODO expand/shrink with balanced sample by flops [baseline]
CUDA_VISIBLE_DEVICES=0 python tools/train_shrinker.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench201Network --trainer_name NB201ShrinkTrainer  --dataset cifar10 --crit ce --lr 0.025 --type flops  --log_name sspace-shrink-expand_nb201_balanced-sampling_baseline --expand_times 0 --shrink_times 0

####################################only expand##########################################

# TODO expand with balanced sample by flops [expand-2-times]
CUDA_VISIBLE_DEVICES=0 python tools/train_shrinker.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench201Network --trainer_name NB201ShrinkTrainer  --dataset cifar10 --crit ce --lr 0.025 --type flops  --log_name sspace-shrink-expand_nb201_balanced-sampling_expand-2-times --expand_times 2 --shrink_times 0

# TODO expand with balanced sample by flops [expand-4-times]
CUDA_VISIBLE_DEVICES=0 python tools/train_shrinker.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench201Network --trainer_name NB201ShrinkTrainer  --dataset cifar10 --crit ce --lr 0.025 --type flops  --log_name sspace-shrink-expand_nb201_balanced-sampling_expand-4-times --expand_times 4 --shrink_times 0

# TODO expand with balanced sample by flops [expand-8-times]
CUDA_VISIBLE_DEVICES=0 python tools/train_shrinker.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench201Network --trainer_name NB201ShrinkTrainer  --dataset cifar10 --crit ce --lr 0.025 --type flops  --log_name sspace-shrink-expand_nb201_balanced-sampling_expand-8-times --expand_times 8 --shrink_times 0

# TODO expand with balanced sample by flops [expand-16-times]
CUDA_VISIBLE_DEVICES=0 python tools/train_shrinker.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench201Network --trainer_name NB201ShrinkTrainer  --dataset cifar10 --crit ce --lr 0.025 --type flops  --log_name sspace-shrink-expand_nb201_balanced-sampling_expand-16-times --expand_times 16 --shrink_times 0

###################################only shrink############################################

# TODO shrink with balanced sample by flops [shrink-2-times]
CUDA_VISIBLE_DEVICES=1 python tools/train_shrinker.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench201Network --trainer_name NB201ShrinkTrainer  --dataset cifar10 --crit ce --lr 0.025 --type flops  --log_name sspace-shrink-expand_nb201_balanced-sampling_shrink-2-times --expand_times 0 --shrink_times 2

# TODO shrink with balanced sample by flops [shrink-4-times]
CUDA_VISIBLE_DEVICES=1 python tools/train_shrinker.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench201Network --trainer_name NB201ShrinkTrainer  --dataset cifar10 --crit ce --lr 0.025 --type flops  --log_name sspace-shrink-expand_nb201_balanced-sampling_shrink-4-times --expand_times 0 --shrink_times 4

# TODO shrink with balanced sample by flops [shrink-8-times]
CUDA_VISIBLE_DEVICES=2 python tools/train_shrinker.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench201Network --trainer_name NB201ShrinkTrainer  --dataset cifar10 --crit ce --lr 0.025 --type flops  --log_name sspace-shrink-expand_nb201_balanced-sampling_shrink-8-times --expand_times 0 --shrink_times 8

# TODO shrink with balanced sample by flops [shrink-16-times]
CUDA_VISIBLE_DEVICES=2 python tools/train_shrinker.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench201Network --trainer_name NB201ShrinkTrainer  --dataset cifar10 --crit ce --lr 0.025 --type flops  --log_name sspace-shrink-expand_nb201_balanced-sampling_shrink-16-times --expand_times 0 --shrink_times 16

##################################shrink and expand########################################

# TODO shrink and expand with balanced sample by flops [s4-e4]
CUDA_VISIBLE_DEVICES=0 python tools/train_shrinker.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench201Network --trainer_name NB201ShrinkTrainer  --dataset cifar10 --crit ce --lr 0.025 --type flops  --log_name sspace-shrink-expand_nb201_balanced-sampling_s4-e4 --expand_times 4 --shrink_times 4

# TODO shrink and expand with balanced sample by flops [s4-e8]
CUDA_VISIBLE_DEVICES=0 python tools/train_shrinker.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench201Network --trainer_name NB201ShrinkTrainer  --dataset cifar10 --crit ce --lr 0.025 --type flops  --log_name sspace-shrink-expand_nb201_balanced-sampling_s8-e4 --expand_times 8 --shrink_times 4

# TODO shrink and expand with balanced sample by flops [s8-e4]
CUDA_VISIBLE_DEVICES=0 python tools/train_shrinker.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench201Network --trainer_name NB201ShrinkTrainer  --dataset cifar10 --crit ce --lr 0.025 --type flops  --log_name sspace-shrink-expand_nb201_balanced-sampling_s4-e8 --expand_times 4 --shrink_times 8

# TODO shrink and expand with balanced sample by flops [s8-e8]
CUDA_VISIBLE_DEVICES=0 python tools/train_shrinker.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench201Network --trainer_name NB201ShrinkTrainer  --dataset cifar10 --crit ce --lr 0.025 --type flops  --log_name sspace-shrink-expand_nb201_balanced-sampling_s8-e8 --expand_times 8 --shrink_times 8


##################################### rank difference #########################################
python tools/train_shrinker.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench201Network --trainer_name NB201ShrinkTrainer  --dataset cifar10 --crit ce --lr 0.025 --type flops  --log_name sspace-shrink-expand_nb201_balanced-sampling_sn-en --expand_times 8 --shrink_times 8


#################### ANYALSE with spos ##############################
CUDA_VISIBLE_DEVICES=0 python tools/train_shrinker.py --config configs/spos/spos_cifar10.py --model_name OneShotNASBench201Network --trainer_name NB201ShrinkTrainer  --dataset cifar10 --crit ce --lr 0.05 --type uniform  --log_name anaylse_nb201_spos_exp1.0 --expand_times 0 --shrink_times 0 --batch_size 512 --epochs 1000 --sched plateau
