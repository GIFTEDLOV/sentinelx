# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

"""NON_PRODUCTION_DIAGNOSTIC_ONLY: finalized cross-contract view probe target."""

from genlayer import Address, gl, u256


class FinalizedViewProbeTarget(gl.Contract):
    """Minimal deterministic target used only to isolate StorageType behavior."""

    owner: Address
    number: u256
    text: str

    def __init__(self, number: u256, text: str):
        self.owner = gl.message.sender_address
        self.number = number
        self.text = text

    @gl.public.view
    def get_number(self) -> u256:
        return self.number

    @gl.public.view
    def get_text(self) -> str:
        return self.text

    @gl.public.view
    def get_owner(self) -> Address:
        return self.owner

    @gl.public.write
    def set_number(self, number: u256) -> None:
        if gl.message.sender_address != self.owner:
            raise gl.vm.UserError("Only the probe target owner may write")
        self.number = number
