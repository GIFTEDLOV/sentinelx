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
        def register_target(
            self,
            target: str,
            owner: str,
            project_name: str,
            release_constitution: str,
            source_authority: str,
            ci_authority: str,
            security_attestation_mode: str,
            security_authority: str,
            source_prefix: str,
            ci_prefix: str,
            security_prefix: str,
            current_version: str,
            current_source_url: str,
            current_code_hash: str,
            max_evidence_age_seconds: int,
            proposal_ttl_seconds: int,
            execution_timeout_seconds: int,
        ) -> None: ...

        def confirm_install(self, proposal_id: u256, candidate_hash: str) -> None: ...


class ProtectedApplication(gl.Contract):
    """Safe v2 candidate with an append-only storage extension.

    The first eight fields exactly preserve protected_app_v1.py. The final
    `release_note` field is appended and starts empty on an existing v1 state.
    All owner rights and the SentinelX-only upgrade path remain unchanged.
    """

    owner: Address
    sentinelx_governor: Address
    application_name: str
    protected_value: str
    value_nonce: u256
    installed_proposal_id: u256
    installed_candidate_hash: str
    registered_with_sentinelx: bool
    release_note: str

    def __init__(
        self,
        sentinelx_governor: Address,
        application_name: str,
        initial_value: str,
    ):
        # Existing state is retained during a code-only upgrade. These
        # assignments are constructor documentation for fresh deployments.
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
        self.release_note = ""

    def _only_owner(self) -> None:
        if gl.message.sender_address != self.owner:
            raise gl.vm.UserError("Only the protected application owner may call this method")

    @gl.public.write
    def set_protected_value(self, value: str) -> None:
        self._only_owner()
        self.protected_value = value
        self.value_nonce = self.value_nonce + 1

    @gl.public.view
    def get_protected_value(self) -> str:
        return self.protected_value

    @gl.public.view
    def get_value_nonce(self) -> u256:
        return self.value_nonce

    @gl.public.view
    def get_application_name(self) -> str:
        return self.application_name

    @gl.public.view
    def get_release_note(self) -> str:
        return self.release_note

    @gl.public.view
    def get_release_note_length(self) -> int:
        return len(self.release_note)

    @gl.public.write
    def set_release_note(self, note: str) -> None:
        self._only_owner()
        self.release_note = note

    @gl.public.view
    def get_owner(self) -> Address:
        return self.owner

    @gl.public.view
    def get_upgrade_governor(self) -> Address:
        return self.sentinelx_governor

    @gl.public.view
    def get_installed_proposal_id(self) -> u256:
        return self.installed_proposal_id

    @gl.public.view
    def get_installed_candidate_hash(self) -> str:
        return self.installed_candidate_hash

    @gl.public.view
    def is_registered_with_sentinelx(self) -> bool:
        return SentinelXGovernorInterface(self.sentinelx_governor).view().is_target_registered(
            str(gl.message.contract_address)
        )

    @gl.public.write
    def register_with_sentinelx(
        self,
        project_name: str,
        release_constitution: str,
        source_authority: str,
        ci_authority: str,
        security_attestation_mode: str,
        security_authority: str,
        source_prefix: str,
        ci_prefix: str,
        security_prefix: str,
        current_version: str,
        current_source_url: str,
        current_code_hash: str,
        max_evidence_age_seconds: int,
        proposal_ttl_seconds: int,
        execution_timeout_seconds: int,
    ) -> None:
        self._only_owner()
        if SentinelXGovernorInterface(self.sentinelx_governor).view().is_target_registered(
            str(gl.message.contract_address)
        ):
            raise gl.vm.UserError("Policy registration is already finalized")
        SentinelXGovernorInterface(self.sentinelx_governor).emit(on="finalized").register_target(
            str(gl.message.contract_address),
            str(self.owner),
            project_name,
            release_constitution,
            source_authority,
            ci_authority,
            security_attestation_mode,
            security_authority,
            source_prefix,
            ci_prefix,
            security_prefix,
            current_version,
            current_source_url,
            current_code_hash,
            max_evidence_age_seconds,
            proposal_ttl_seconds,
            execution_timeout_seconds,
        )

    @gl.public.write
    def install_reviewed_upgrade(self, proposal_id: u256, candidate_hash: str) -> None:
        if gl.message.sender_address != self.sentinelx_governor:
            raise gl.vm.UserError("Only SentinelX may install an upgrade")
        normalized_hash = candidate_hash.lower()
        governor = SentinelXGovernorInterface(self.sentinelx_governor)
        if not governor.view().is_upgrade_authorized(
            proposal_id,
            str(gl.message.contract_address),
            normalized_hash,
        ):
            raise gl.vm.UserError("Live SentinelX authorization is absent or expired")
        if self.installed_proposal_id == proposal_id:
            raise gl.vm.UserError("Proposal was already installed")
        candidate_code = governor.view().get_candidate_code(proposal_id)
        actual_hash = hashlib.sha256(candidate_code).hexdigest()
        if actual_hash != normalized_hash:
            raise gl.vm.UserError("Candidate bytes do not match candidate hash")
        self.installed_proposal_id = proposal_id
        self.installed_candidate_hash = actual_hash
        root = gl.storage.Root.get()
        code = root.code.get()
        code.truncate()
        code.extend(candidate_code)
        governor.emit(on="finalized").confirm_install(proposal_id, actual_hash)
