# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

"""NON_PRODUCTION_DIAGNOSTIC_ONLY: typed cross-contract view probe caller."""

from genlayer import Address, gl, u256
from genlayer.py.public_abi import StorageType


@gl.contract_interface
class FinalizedViewProbeTargetInterface:
    class View:
        def get_number(self) -> u256: ...


class FinalizedViewProbeCaller(gl.Contract):
    """Each public write performs exactly one typed target view."""

    last_number: u256

    def __init__(self):
        self.last_number = 0

    def _probe(self, target: str, state: StorageType | None) -> None:
        target_proxy = FinalizedViewProbeTargetInterface(Address(target))
        if state is None:
            self.last_number = target_proxy.view().get_number()
        else:
            self.last_number = target_proxy.view(state=state).get_number()

    @gl.public.write
    def probe_default(self, target: str) -> None:
        self._probe(target, None)

    @gl.public.write
    def probe_latest_finalized(self, target: str) -> None:
        self._probe(target, StorageType.LATEST_FINAL)

    @gl.public.write
    def probe_latest_decided(self, target: str) -> None:
        self._probe(target, StorageType.LATEST_NON_FINAL)

    @gl.public.view
    def get_last_number(self) -> u256:
        return self.last_number
