# Copyright (c) OpenMMLab. All rights reserved.
from abc import abstractmethod
from functools import partial
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor

from .base_mutable import CHOICE_TYPE, CHOSEN_TYPE, BaseMutable

PartialType = Callable[[Any, Optional[nn.Parameter]], Any]


class DiffMutable(BaseMutable[CHOICE_TYPE, CHOSEN_TYPE]):
    """Base class for differentiable mutables.

    Args:
        module_kwargs (dict[str, dict], optional): Module initialization named
            arguments. Defaults to None.
        alias (str, optional): alias of the `MUTABLE`.
        init_cfg (dict, optional): initialization configuration dict for
            ``BaseModule``. OpenMMLab has implement 5 initializer including
            `Constant`, `Xavier`, `Normal`, `Uniform`, `Kaiming`,
            and `Pretrained`.

    Note:
        :meth:`forward_all` is called when calculating FLOPs.
    """

    def __init__(
        self,
        module_kwargs: Optional[Dict[str, Dict]] = None,
        alias: Optional[str] = None,
        init_cfg: Optional[Dict] = None,
    ) -> None:
        super().__init__(
            module_kwargs=module_kwargs, alias=alias, init_cfg=init_cfg)

    def forward(self,
                x: Any,
                arch_param: Optional[nn.Parameter] = None) -> Any:
        """Calls either :func:`forward_fixed` or :func:`forward_choice`
        depending on whether :func:`is_fixed` is ``True``.

        To reduce the coupling between `Mutable` and `Mutator`, the
        `arch_param` is generated by the `Mutator` and is passed to the
        forward function as an argument.

        Note:
            :meth:`forward_fixed` is called when in `fixed` mode.
            :meth:`forward_arch_param` is called when in `unfixed` mode.

        Args:
            x (Any): input data for forward computation.
            arch_param (nn.Parameter, optional): the architecture parameters
                for ``DiffMutable``.
        """
        if self.is_fixed:
            return self.forward_fixed(x)
        else:
            return self.forward_arch_param(x, arch_param=arch_param)

    def build_arch_param(self) -> nn.Parameter:
        """Build learnable architecture parameters."""
        return nn.Parameter(torch.randn(self.num_choices) * 1e-3)

    def compute_arch_probs(self, arch_param: Any) -> Tensor:
        """compute chosen probs according to architecture params."""
        return F.softmax(arch_param, dim=-1)

    @abstractmethod
    def forward_fixed(self, x: Any) -> Any:
        """Forward when the mutable is fixed.

        All subclasses must implement this method.
        """

    @abstractmethod
    def forward_all(self, x: Any) -> Any:
        """Forward all choices."""

    @abstractmethod
    def forward_arch_param(self,
                           x: Any,
                           arch_param: Optional[nn.Parameter] = None) -> Any:
        """Forward when the mutable is not fixed.

        All subclasses must implement this method.
        """

    def set_forward_args(self, arch_param: nn.Parameter) -> None:
        """Interface for modifying the arch_param using partial."""
        forward_with_default_args: PartialType = partial(
            self.forward, arch_param=arch_param)
        setattr(self, 'forward', forward_with_default_args)


class DiffOP(DiffMutable[str, str]):
    """A type of ``MUTABLES`` for differentiable architecture search, such as
    DARTS. Search the best module by learnable parameters `arch_param`.

    Args:
        candidate_ops (nn.ModuleDict): the configs for the candidate
            operations.
        module_kwargs (dict[str, dict], optional): Module initialization named
            arguments. Defaults to None.
        alias (str, optional): alias of the `MUTABLE`.
        init_cfg (dict, optional): initialization configuration dict for
            ``BaseModule``. OpenMMLab has implement 5 initializer including
            `Constant`, `Xavier`, `Normal`, `Uniform`, `Kaiming`,
            and `Pretrained`.
    """

    def __init__(
        self,
        candidate_ops: nn.ModuleDict,
        module_kwargs: Optional[Dict[str, Dict]] = None,
        alias: Optional[str] = None,
        init_cfg: Optional[Dict] = None,
    ) -> None:
        super().__init__(
            module_kwargs=module_kwargs, alias=alias, init_cfg=init_cfg)
        assert len(candidate_ops) >= 1, (
            f'Number of candidate op must greater than or equal to 1, '
            f'but got: {len(candidate_ops)}')

        self._is_fixed = False
        self._candidate_ops = self._build_ops(candidate_ops)

    @staticmethod
    def _build_ops(candidate_ops: nn.ModuleDict) -> nn.ModuleDict:
        """Build candidate operations based on candidate_ops configures.

        Args:
            candidate_ops (dict[str, dict]): the configs for the candidate
                operations.
            module_kwargs (dict[str, dict], optional): Module initialization
                named arguments.

        Returns:
            ModuleDict (dict[str, Any], optional):  the key of ``ops`` is
                the name of each choice in configs and the value of ``ops``
                is the corresponding candidate operation.
        """
        if isinstance(candidate_ops, nn.ModuleDict):
            return candidate_ops
        else:
            raise NotImplementedError

    def forward_fixed(self, x: Any) -> Tensor:
        """Forward when the mutable is in `fixed` mode.

        Args:
            x (Any): x could be a Torch.tensor or a tuple of
                Torch.tensor, containing input data for forward computation.

        Returns:
            Tensor: the result of forward the fixed operation.
        """
        return sum(self._candidate_ops[choice](x) for choice in self._chosen)

    def forward_arch_param(self,
                           x: Any,
                           arch_param: Optional[nn.Parameter] = None
                           ) -> Tensor:
        """Forward with architecture parameters.

        Args:
            x (Any): x could be a Torch.tensor or a tuple of
                Torch.tensor, containing input data for forward computation.
            arch_param (str, optional): architecture parameters for
                `DiffMutable`


        Returns:
            Tensor: the result of forward with ``arch_param``.
        """
        if arch_param is None:
            return self.forward_all(x)
        else:
            # compute the probs of choice
            probs = self.compute_arch_probs(arch_param=arch_param)

            # forward based on probs
            outputs = list()
            for prob, module in zip(probs, self._candidate_ops.values()):
                if prob > 0.0:
                    outputs.append(prob * module(x))

            return sum(outputs)

    def forward_all(self, x: Any) -> Tensor:
        """Forward all choices. Used to calculate FLOPs.

        Args:
            x (Any): x could be a Torch.tensor or a tuple of
                Torch.tensor, containing input data for forward computation.

        Returns:
            Tensor: the result of forward all of the ``choice`` operation.
        """
        outputs = list()
        for op in self._candidate_ops.values():
            outputs.append(op(x))
        return sum(outputs)

    def fix_chosen(self, chosen: Union[List[str], str]) -> None:
        """Fix mutable with `choice`. This operation would convert `unfixed`
        mode to `fixed` mode. The :attr:`is_fixed` will be set to True and only
        the selected operations can be retained.

        Args:
            chosen (str): the chosen key in ``MUTABLE``.
                Defaults to None.
        """
        if self.is_fixed:
            raise AttributeError(
                'The mode of current MUTABLE is `fixed`. '
                'Please do not call `fix_chosen` function again.')

        for c in self.choices:
            if c != chosen:
                self._candidate_ops.pop(c)

        self._chosen = chosen
        self.is_fixed = True

    @property
    def choices(self) -> List[str]:
        """list: all choices."""
        return list(self._candidate_ops.keys())

    def sample_choice(self, arch_param):
        """Sample choice based on arch_parameters."""
        arch_param = F.softmax(arch_param, dim=-1)
        return self.choices[torch.argmax(arch_param).item()]


class DynaDiffOP(DiffOP):
    """A type of ``MUTABLES`` for differentiable architecture search, such as
    DARTS. Dynamically fix some of mutable during searching.

    Args:
        candidate_ops (nn.ModuleDict): the configs for the candidate
            operations.
        module_kwargs (dict[str, dict], optional): Module initialization named
            arguments. Defaults to None.
        alias (str, optional): alias of the `MUTABLE`.
        dyna_thresh (int, optional): dynamically fix mutable during searching.
        init_cfg (dict, optional): initialization configuration dict for
            ``BaseModule``. OpenMMLab has implement 5 initializer including
            `Constant`, `Xavier`, `Normal`, `Uniform`, `Kaiming`,
            and `Pretrained`.
    """

    def __init__(
        self,
        candidate_ops: nn.ModuleDict,
        module_kwargs: Optional[Dict[str, Dict]] = None,
        alias: Optional[str] = None,
        dyna_thresh: int = 0.3,
        init_cfg: Optional[Dict] = None,
    ) -> None:
        super().__init__(
            candidate_ops=candidate_ops,
            module_kwargs=module_kwargs,
            alias=alias,
            init_cfg=init_cfg)

        assert len(candidate_ops) >= 1, (
            f'Number of candidate op must greater than or equal to 1, '
            f'but got: {len(candidate_ops)}')

        self.dyna_thresh = dyna_thresh

    def forward_arch_param(self,
                           x: Any,
                           arch_param: Optional[nn.Parameter] = None
                           ) -> Tensor:
        """Forward with architecture parameters.

        Args:
            x (Any): x could be a Torch.tensor or a tuple of
                Torch.tensor, containing input data for forward computation.
            arch_param (str, optional): architecture parameters for
                `DiffMutable`

        Returns:
            Tensor: the result of forward with ``arch_param``.
        """
        if arch_param is None:
            return self.forward_all(x)
        else:
            # compute the probs of choice
            probs = self.compute_arch_probs(arch_param=arch_param)

            if not self.is_fixed:
                # if not fixed, judge whether to fix.
                sorted_param = torch.topk(probs, 2)
                index = (
                    sorted_param[0][0] - sorted_param[0][1] >=
                    self.dyna_thresh)
                if index:
                    self.fix_chosen(self.choices[index])
            else:
                # if fixed, query the fix operation.
                index = self.choices.index(self._chosen[0])
                probs.data.zero_()
                probs.data[index].fill_(1.0)

            # forward based on probs
            outputs = list()
            for prob, module in zip(probs, self._candidate_ops.values()):
                if prob > 0.0:
                    outputs.append(prob * module(x))

            return sum(outputs)


class DiffChoiceRoute(DiffMutable[str, List[str]]):
    """A type of ``MUTABLES`` for Neural Architecture Search, which can select
    inputs from different edges in a differentiable or non-differentiable way.
    It is commonly used in DARTS.

    Args:
        edges (nn.ModuleDict): the key of `edges` is the name of different
            edges. The value of `edges` can be :class:`nn.Module` or
            :class:`DiffMutable`.
        with_arch_param (bool): whether forward with arch_param. When set to
            `True`, a differentiable way is adopted. When set to `False`,
            a non-differentiable way is adopted.
        init_cfg (dict, optional): initialization configuration dict for
            ``BaseModule``. OpenMMLab has implement 6 initializers including
            `Constant`, `Xavier`, `Normal`, `Uniform`, `Kaiming`,
            and `Pretrained`.

    Examples:
        >>> import torch
        >>> import torch.nn as nn
        >>> edges_dict=nn.ModuleDict()
        >>> edges_dict.add_module('first_edge', nn.Conv2d(32, 32, 3, 1, 1))
        >>> edges_dict.add_module('second_edge', nn.Conv2d(32, 32, 5, 1, 2))
        >>> edges_dict.add_module('third_edge', nn.MaxPool2d(3, 1, 1))
        >>> edges_dict.add_module('fourth_edge', nn.MaxPool2d(5, 1, 2))
        >>> edges_dict.add_module('fifth_edge', nn.MaxPool2d(7, 1, 3))
        >>> diff_choice_route_cfg = dict(
        ...     type="DiffChoiceRoute",
        ...     edges=edges_dict,
        ...     with_arch_param=True,
        ... )
        >>> arch_param
        Parameter containing:
        tensor([-6.1426e-04,  2.3596e-04,  1.4427e-03,  7.1668e-05,
            -8.9739e-04], requires_grad=True)
        >>> x = [torch.randn(4, 32, 64, 64) for _ in range(5)]
        >>> output=diffchoiceroute.forward_arch_param(x, arch_param)
        >>> output.shape
        torch.Size([4, 32, 64, 64])
    """

    def __init__(
        self,
        edges: nn.ModuleDict,
        with_arch_param: bool = False,
        init_cfg: Optional[Dict] = None,
    ) -> None:
        super().__init__(init_cfg=init_cfg)
        assert len(edges) >= 1, (
            f'Number of edges must greater than or equal to 1, '
            f'but got: {len(edges)}')

        self._with_arch_param = with_arch_param
        self._is_fixed = False
        self._edges: nn.ModuleDict = edges

    def forward_fixed(self, inputs: Union[List, Tuple]) -> Tensor:
        """Forward when the mutable is in `fixed` mode.

        Args:
            inputs (Union[List[Any], Tuple[Any]]): inputs could be a list or
                a tuple of Torch.tensor, containing input data for
                forward computation.

        Returns:
            Tensor: the result of forward the fixed operation.
        """
        assert (self._chosen is not None
                ), 'Please call fix_chosen before calling `forward_fixed`.'

        outputs = list()
        for choice, x in zip(self._unfixed_choices, inputs):
            if choice in self._chosen:
                outputs.append(self._edges[choice](x))
        return sum(outputs)

    def forward_arch_param(self,
                           x: Union[List[Any], Tuple[Any]],
                           arch_param: nn.Parameter = None) -> Tensor:
        """Forward with architecture parameters.

        Args:
            x (list[Any] | tuple[Any]]): x could be a list or a tuple
                of Torch.tensor, containing input data for forward selection.
            arch_param (nn.Parameter): architecture parameters for
                for ``DiffMutable``.

        Returns:
            Tensor: the result of forward with ``arch_param``.
        """
        assert len(x) == len(self._edges), (
            f'Length of `edges` {len(self._edges)} should be same as '
            f'the length of inputs {len(x)}.')

        if self._with_arch_param:
            probs = self.compute_arch_probs(arch_param=arch_param)

            outputs = list()
            for prob, module, input in zip(probs, self._edges.values(), x):
                if prob > 0:
                    # prob may equal to 0 in gumbel softmax.
                    outputs.append(prob * module(input))

            return sum(outputs)
        else:
            return self.forward_all(x)

    def forward_all(self, x: Any) -> Tensor:
        """Forward all choices.

        Args:
            x (Any): x could be a Torch.tensor or a tuple of
                Torch.tensor, containing input data for forward computation.

        Returns:
            Tensor: the result of forward all of the ``choice`` operation.
        """
        assert len(x) == len(self._edges), (
            f'Lenght of edges {len(self._edges)} should be same as '
            f'the length of inputs {len(x)}.')

        outputs = list()
        for op, input in zip(self._edges.values(), x):
            outputs.append(op(input))

        return sum(outputs)

    def fix_chosen(self, chosen: List[str]) -> None:
        """Fix mutable with `choice`. This operation would convert to `fixed`
        mode. The :attr:`is_fixed` will be set to True and only the selected
        operations can be retained.

        Args:
            chosen (list(str)): the chosen key in ``MUTABLE``.
        """
        self._unfixed_choices = self.choices

        if self.is_fixed:
            raise AttributeError(
                'The mode of current MUTABLE is `fixed`. '
                'Please do not call `fix_chosen` function again.')

        for c in self.choices:
            if c not in chosen:
                self._edges.pop(c)

        self._chosen = chosen
        self.is_fixed = True

    @property
    def choices(self) -> List[CHOSEN_TYPE]:
        """list: all choices."""
        return list(self._edges.keys())


class GumbelChoiceRoute(DiffChoiceRoute):
    """A type of ``MUTABLES`` for Neural Architecture Search using Gumbel-Max
    trick, which can select inputs from different edges in a differentiable or
    non-differentiable way. It is commonly used in DARTS.

    Args:
        edges (nn.ModuleDict): the key of `edges` is the name of different
            edges. The value of `edges` can be :class:`nn.Module` or
            :class:`DiffMutable`.
        tau (float): non-negative scalar temperature in gumbel softmax.
        hard (bool): if `True`, the returned samples will be discretized as
            one-hot vectors, but will be differentiated as if it is the soft
            sample in autograd. Defaults to `True`.
        with_arch_param (bool): whether forward with arch_param. When set to
            `True`, a differentiable way is adopted. When set to `False`,
            a non-differentiable way is adopted.
        init_cfg (dict, optional): initialization configuration dict for
            ``BaseModule``. OpenMMLab has implement 6 initializers including
            `Constant`, `Xavier`, `Normal`, `Uniform`, `Kaiming`,
            and `Pretrained`.
    """

    def __init__(
        self,
        edges: nn.ModuleDict,
        tau: float = 1.0,
        hard: bool = True,
        with_arch_param: bool = False,
        init_cfg: Optional[Dict] = None,
    ) -> None:
        super().__init__(
            edges=edges, with_arch_param=with_arch_param, init_cfg=init_cfg)
        self.tau = tau
        self.hard = hard

    def compute_arch_probs(self, arch_param: nn.Parameter) -> Tensor:
        """Compute chosen probs by Gumbel-Max trick."""
        return F.gumbel_softmax(
            arch_param, tau=self.tau, hard=self.hard, dim=-1)

    def set_temperature(self, tau: float) -> None:
        """Set temperature of gumbel softmax."""
        self.tau = tau
