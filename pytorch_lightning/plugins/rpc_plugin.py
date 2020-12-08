# Copyright The PyTorch Lightning team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os

import torch
from pytorch_lightning.core.lightning import LightningModule

from pytorch_lightning.plugins.ddp_plugin import DDPPlugin
from pytorch_lightning.utilities import RPC_AVAILABLE

if RPC_AVAILABLE:
    from torch.distributed import rpc


class RPCPlugin(DDPPlugin):
    """
    Backbone for RPC Plugins built on top of DDP.
    RPC introduces different communication behaviour than DDP. Unlike DDP, processes potentially are not
    required to run the same code as the main process.
    This leads to edge cases where logic needs to be re-defined. This class contains special cases
    that need to be addressed when using RPC communication when building custom RPC Plugins.
    """

    def __init__(self, **kwargs):
        self.rpc_initialized = False
        super().__init__(**kwargs)

    def init_rpc_connection(self,
                            global_rank: int,
                            world_size: int) -> None:
        os.environ['MASTER_PORT'] = os.getenv('RPC_MASTER_PORT', '15000')
        rpc.init_rpc(f"worker{global_rank}", rank=global_rank, world_size=world_size)
        self.rpc_initialized = True

    def rpc_save_model(self,
                       save_model_fn,
                       last_filepath,
                       trainer,
                       pl_module) -> None:
        """
        Override to save model to disk.
        This is required as the main process will be required to handle aggregating model states from RPC processes.
        Args:
            save_model_fn: The saving function to save final model.
            last_filepath: The filepath to save the model to.
            trainer: The trainer object.
            pl_module: The LightningModule.
        """
        raise NotImplementedError

    def on_main_rpc_connection(self, trainer) -> None:
        """
        Called when main rpc connection has been established.
        Args:
            trainer: The trainer object.
        """
        raise NotImplementedError

    def on_exit_rpc_process(self, trainer) -> None:
        """
        Called to exit RPC process that is being managed by main process.
        Args:
            trainer: The trainer object.
        """
        self.exit_rpc_process()

    def exit_rpc_process(self):
        if self.rpc_initialized:
            torch.distributed.rpc.shutdown()
            self.rpc_initialized = False

    def worker_optimizer_step(self,
                              model: LightningModule,
                              opt_idx: int,
                              *args,
                              **kwargs) -> None:
        """
        Called when optimizer step is run on the main process. Used to signal any RPC workers to run optimizer step.
        Args:
            model: The LightningModule.
            opt_idx: The idx of the optimizer to carry out step on.
        """
        raise NotImplementedError

    @property
    def is_main_rpc_process(self) -> bool:
        """
        Override to add logic to determine current process is main RPC process.
        """
        raise NotImplementedError

    def barrier(self) -> None:
        """
        Override to define distributed sync communication. This needs to be handled differently due to
        the RPC connection managing certain processes at the same time.
        """
        raise NotImplementedError