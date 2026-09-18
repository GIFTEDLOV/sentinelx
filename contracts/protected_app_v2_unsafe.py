# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import Address, gl, u256
import hashlib


TARGET_SCHEMA_VERSION = "sentinelx-target-v2"


@gl.contract_interface
class SentinelXGovernorInterface:
    class View:
        def is_target_registered(self, target: str) -> bool: ...

        def is_upgrade_authorized(
            self, proposal_id: u256, target: str, candidate_hash: str
        ) -> bool: ...

        def get_candidate_code(self, proposal_id: u256) -> bytes: ...

    class Write:
        def confirm_install(self, proposal_id: u256, candidate_hash: str) -> None: ...


class ProtectedApplication(gl.Contract):
    """TEST-ONLY malicious candidate; never use as the canonical upgrade.

    This candidate deliberately demonstrates several review failures: it adds
    a field in the middle of the v1 layout, exposes an owner-controlled code
    replacement path, permits arbitrary privileged-state mutation, and adds a
    payable value drain. SentinelX semantic review must reject it before any
    installation consequence is queued.
    """

    # Incompatible insertion shifts the v1 storage interpretation.
    emergency_admin: Address
    owner: Address
    sentinelx_governor: Address
    application_name: str
    protected_value: str
    value_nonce: u256
    installed_proposal_id: u256
    installed_candidate_hash: str
    registered_with_sentinelx: bool

    def __init__(
        self,
        sentinelx_governor: Address,
        application_name: str,
        initial_value: str,
    ):
        self.emergency_admin = gl.message.sender_address
        self.owner = gl.message.sender_address
        # Stable py-genlayer delivers address calldata as text at the
        # constructor boundary; normalize it before any Address operation.
        sentinelx_governor = Address(sentinelx_governor)
        self.sentinelx_governor = sentinelx_governor
        self.application_name = application_name
        self.protected_value = initial_value
        self.value_nonce = 0
        self.installed_proposal_id = 0
        self.installed_candidate_hash = ""
        self.registered_with_sentinelx = False

    @gl.public.write
    def set_protected_value(self, value: str) -> None:
        self.protected_value = value

    @gl.public.write
    def owner_replace_code(self, candidate_code: bytes) -> None:
        if gl.message.sender_address != self.owner:
            raise gl.vm.UserError("Only owner")
        root = gl.storage.Root.get()
        code = root.code.get()
        code.truncate()
        code.extend(candidate_code)

    @gl.public.write
    def rewrite_governor(self, replacement: Address) -> None:
        self.sentinelx_governor = replacement

    @gl.public.write
    def mutate_privileged_state(self, new_admin: Address) -> None:
        self.emergency_admin = new_admin

    @gl.public.write.payable
    def drain_value(self, recipient: Address) -> None:
        if gl.message.sender_address != self.owner:
            raise gl.vm.UserError("Only owner")
        recipient_contract = gl.contract.get_at(recipient)
        recipient_contract.emit_transfer(gl.message.value, on="finalized")

    @gl.public.view
    def get_protected_value(self) -> str:
        return self.protected_value

    @gl.public.view
    def get_owner(self) -> Address:
        return self.owner

    @gl.public.view
    def get_upgrade_governor(self) -> Address:
        return self.sentinelx_governor

    @gl.public.view
    def is_registered_with_sentinelx(self) -> bool:
        return SentinelXGovernorInterface(self.sentinelx_governor).view().is_target_registered(
            str(gl.message.contract_address)
        )

    @gl.public.view
    def get_installed_proposal_id(self) -> u256:
        return self.installed_proposal_id

    @gl.public.view
    def get_installed_candidate_hash(self) -> str:
        return self.installed_candidate_hash
