""" Evaluates a ZeroCost predictor for a search space and dataset/task"""

import logging

from pplib.evaluator.zc_evaluator import ZeroCostPredictorEvaluator
from pplib.predictor import ZeroCost
from pplib.nas.search_spaces import get_search_space
from pplib.utils.logging import get_logger
from pplib.utils import (get_dataset_api, get_zc_benchmark_api)
from pplib.utils.utils import get_config_from_args, set_seed, log_args

# Get the configs from naslib/configs/predictor_config.yaml and the command line arguments
# The configs include the zero-cost method to use, the search space and dataset/task to use,
# amongst others.
config = get_config_from_args()
set_seed(config.seed)
logger = get_logger('zc', log_file=f'{config.save}/log.log')
logger.setLevel(logging.INFO)
log_args(config)

# Get the benchmark API for this search space and dataset
dataset_api = None  # get_dataset_api(config.search_space, config.dataset)
zc_api = get_zc_benchmark_api(config.search_space, config.dataset)

# Initialize the search space and predictor
# Method type can be "fisher", "grasp", "grad_norm", "jacov", "snip", "synflow", "flops", "params", "nwot", "zen", "plain", "l2_norm" or "epe_nas"
predictor = ZeroCost(method_type=config.predictor)
search_space = get_search_space(
    name=config.search_space, dataset=config.dataset)
search_space.instantiate_model = False
search_space.labeled_archs = [eval(arch) for arch in zc_api.keys()]

# Initialize the ZeroCostPredictorEvaluator class
predictor_evaluator = ZeroCostPredictorEvaluator(
    predictor, config=config, zc_api=zc_api)
predictor_evaluator.adapt_search_space(
    search_space, dataset_api=dataset_api, load_labeled=True)

# Evaluate the predictor
predictor_evaluator.evaluate(zc_api)

logger.info('Correlation experiment complete.')