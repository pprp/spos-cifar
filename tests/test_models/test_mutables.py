import unittest
from unittest import TestCase

import torch
import torch.nn as nn

from pplib.nas.mutables import OneShotOP


class TestOneShot(TestCase):

    def test_oneshotop(self):

        candidate_ops = nn.ModuleDict()
        candidate_ops.add_module('candidate1', nn.Conv2d(32, 32, 3, 1, 1))

        candidate_ops.add_module('candidate2', nn.Conv2d(32, 32, 5, 1, 2))
        candidate_ops.add_module('candidate3', nn.Conv2d(32, 32, 7, 1, 3))

        osop = OneShotOP(candidate_ops=candidate_ops)

        inputs = torch.randn(4, 32, 32, 32)

        outputs = osop(inputs)
        print(outputs.shape)
        assert outputs is not None


if __name__ == '__main__':
    unittest.main()