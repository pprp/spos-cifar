import torch
import torch.nn as nn

from piconas.datasets.predictor.nb201_dataset import Nb201DatasetPINAT
from piconas.predictor.pinat.BN.bayesian import BayesianLayer


class BayesianNetwork(nn.Module):

    def __init__(self, layer_sizes=[294, 160, 64, 1]):
        super(BayesianNetwork, self).__init__()
        self.layers = nn.ModuleList([
            BayesianLayer(layer_sizes[i], layer_sizes[i + 1])
            for i in range(len(layer_sizes) - 1)
        ])

    def forward(self, x):
        if isinstance(x, dict):
            x = x['zcp_layerwise']
        for i, layer in enumerate(self.layers):
            x = layer(x)
            if i < len(self.layers) - 1:
                x = torch.relu(x)
        return x


if __name__ == '__main__':
    model = BayesianNetwork()

    test_set = Nb201DatasetPINAT(
        split='all', data_type='test', data_set='cifar10')

    loader = torch.utils.data.DataLoader(
        test_set, batch_size=32, shuffle=False, num_workers=0, drop_last=False)

    for batch in loader:
        input = batch
        score = model(input)
        print(score)
