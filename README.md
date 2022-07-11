# pplib

single path one shot with CIFAR10


## MAE

- 1. pretrain:

```bash
python tools/mae_pretrain.py
```

- 2. retrain

```bash
python tools/train_classifier.py
```

## SPOS

- Search Space 1: Official ShuffleNet-based Search space.

```python
python tools/train_spos.py
```

- Search Space 2: Macro BenchMark-based Search space.

```python
python tools/train_macro.py
```

## Rank

To evaluate the rank consistency in nas, run:

```python
python tools/eval_rank.py
```


## TODO LIST

- [x] SIMMIM
- [ ] SupMIM
- [x] NASBench201
- [x] SPOS
- [ ] FairNAS
- [x] AngleNAS
- [ ] BNNAS
- [ ] LandmarkReg
- [x] MacroBenchmark
- [x] SAM optimizer
- [ ] KD


## Thanks

- MMRazor: https://github.com/open-mmlab/mmrazor
- SimMIM: https://github.com/microsoft/SimMIM
- NASLib: https://github.com/automl/NASLib


## NASLib

runner: 属于入口，兼容各种用法

- api：(naslib/utils/get_dataset_api) 获取api，得到json的访问
- predictor: 预测器，根据不同type的方法如zen，snip等进行计算，提供查询功能，得到对应分数
    - pruners/measures: 各种评价指标
- search_space: (Graph) networkx中构图功能添加
    - graph 搜索空间定义
    - primitives 基元，即候选操作。
- evaluator: 评估器，主要功能有：
    - 加载数据集 load-dataset
    - 调用预测器predictor进行查询
    - 评估test集合上的结果 single_evaluate
    - 适配搜索空间：adapt_search_space

ss_type:
- nasbench101
- nasbench201
- nasbench301
- transbench101
- transbench101_micro
- transbench101_macro

dataset:
- cifar10
- cifar100
