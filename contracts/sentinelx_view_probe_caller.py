# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

"""NON_PRODUCTION_DIAGNOSTIC_ONLY: SentinelX target view probe caller."""

from genlayer import Address, gl, u256
from genlayer.py.public_abi import StorageType


@gl.contract_interface
class SentinelXViewProbeTargetInterface:
    class View:
        def get_installed_proposal_id(self) -> u256: ...

        def get_installed_candidate_hash(self) -> str: ...


class SentinelXViewProbeCaller(gl.Contract):
    """Diagnostic caller for typed and generic target-view paths."""

    last_proposal_id: u256
    last_candidate_hash: str

    def __init__(self):
        self.last_proposal_id = 0
        self.last_candidate_hash = ""

    def _typed_probe(self, target: str, state: StorageType | None) -> None:
        target_proxy = SentinelXViewProbeTargetInterface(Address(target))
        if state is None:
            target_view = target_proxy.view()
        else:
            target_view = target_proxy.view(state=state)
        self.last_proposal_id = target_view.get_installed_proposal_id()
        self.last_candidate_hash = target_view.get_installed_candidate_hash()

    def _get_at_probe(self, target: str) -> None:
        target_proxy = gl.get_contract_at(Address(target))
        target_view = target_proxy.view(state=StorageType.LATEST_FINAL)
        self.last_proposal_id = target_view.get_installed_proposal_id()
        self.last_candidate_hash = target_view.get_installed_candidate_hash()

    @gl.public.write
    def probe_default_installed(self, target: str) -> None:
        self._typed_probe(target, None)

    @gl.public.write
    def probe_finalized_installed(self, target: str) -> None:
        self._typed_probe(target, StorageType.LATEST_FINAL)

    @gl.public.write
    def probe_decided_installed(self, target: str) -> None:
        self._typed_probe(target, StorageType.LATEST_NON_FINAL)

    @gl.public.write
    def probe_get_at_finalized_installed(self, target: str) -> None:
        self._get_at_probe(target)

    @gl.public.view
    def get_last_installed(self) -> str:
        return f"{self.last_proposal_id}:{self.last_candidate_hash}"
