import torch.nn as nn
from torch import Tensor

from pplib.models.spos.spos_modules import ShuffleModule, ShuffleXModule
from pplib.nas.mutables import OneShotOP


class SearchableShuffleNetV2(nn.Module):

    def __init__(self, classes=10) -> None:
        super().__init__()

        self.arch_settings = [
            # channel, num_blocks, stride
            [64, 4, 1],
            [160, 4, 2],
            [320, 8, 2],
            [640, 4, 1],
        ]
        self.in_channels = 16
        self.last_channel = 640

        self.first_conv = nn.Sequential(
            nn.Conv2d(
                3,
                self.in_channels,
                kernel_size=3,
                stride=1,
                padding=1,
                bias=False), nn.BatchNorm2d(self.in_channels, affine=False),
            nn.ReLU6(inplace=True))

        self.layers = nn.ModuleList()
        for channel, num_blocks, stride in self.arch_settings:
            layer = self._make_layer(channel, num_blocks, stride)
            self.layers.append(layer)

        self.last_conv = nn.Sequential(
            nn.Conv2d(
                self.in_channels, self.last_channel, 1, 1, 0, bias=False),
            nn.BatchNorm2d(self.last_channel, affine=False),
            nn.ReLU6(inplace=True))

        self.gap = nn.AdaptiveAvgPool2d(1)
        self.dropout = nn.Dropout(0.1)
        self.classifier = nn.Linear(self.last_channel, classes, bias=False)

    def _make_layer(self, out_channels: int, num_blocks: int,
                    stride: int) -> nn.Sequential:
        layers = []
        for i in range(num_blocks):
            if i == 0 and stride == 2:
                inp, outp, stride = self.in_channels, out_channels, 2
            else:
                inp, outp, stride = self.in_channels // 2, out_channels, 1
            stride = 2 if stride == 2 and i == 0 else 1
            print(self.in_channels // 2, out_channels)
            candidate_ops = nn.ModuleDict({
                'shuffle_3x3':
                ShuffleModule(inp, outp, kernel=3, stride=stride),
                'shuffle_5x5':
                ShuffleModule(inp, outp, kernel=5, stride=stride),
                'shuffle_7x7':
                ShuffleModule(inp, outp, kernel=7, stride=stride),
                'shuffle_xception':
                ShuffleXModule(inp, outp, stride=stride),
            })
            layers.append(OneShotOP(candidate_ops=candidate_ops))
            self.in_channels = out_channels
        return nn.Sequential(*layers)

    def forward(self, x: Tensor):
        x = self.first_conv(x)
        for i, layer in enumerate(self.layers):
            x = layer(x)
        x = self.last_conv(x)
        x = self.gap(x)
        x = x.view(-1, self.last_channel)
        x = self.classifier(x)
        return x
