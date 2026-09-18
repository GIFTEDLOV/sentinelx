"""Managed-account Studio-dev transaction bridge for SentinelX V2 profiling.

The GenLayer CLI owns keystore/keychain signing and broadcasting.  This module
never reads or exports a private key.  Python performs the precondition read,
fresh CLI fee quote, durable hash capture, finality reconciliation, child
tracking, and expected-state reads.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RPC = "https://studio-dev.genlayer.com/api"
NETWORK = "studio-dev"
CHAIN_ID = 61997
EXPECTED_DEPLOYER = "0xCb5a845638Cbc1f95D7f8343278685682c3bA13F"
MANAGED_ACCOUNT_NAME = "meritround-v2-studionet"
PROFILE_STATE_NAME = os.environ.get("SENTINELX_PROFILE_STATE", "v2-profile")
LOCAL_STATE = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "SentinelX" / PROFILE_STATE_NAME
JOURNAL_PATH = LOCAL_STATE / "transactions.json"
HASH_RE = re.compile(r"0x[0-9a-fA-F]{64}")
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

# These methods can emit internal messages and therefore must never fall back
# to a generic zero-message quote when concrete estimation fails.
MESSAGE_PRODUCING_METHODS = frozenset({
    "register_with_sentinelx",
    "execute_reviewed_upgrade",
    "install_reviewed_upgrade",
    "confirm_install",
})
_TEMP_CLI_ARGUMENT_FILES: set[Path] = set()


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if hasattr(value, "value"):
        return _safe(value.value)
    return value


def _enum_text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _hash_text(value: Any) -> str:
    text = value.hex() if isinstance(value, bytes) else str(value)
    if not text.startswith("0x"):
        text = "0x" + text
    if not HASH_RE.fullmatch(text):
        raise ValueError("transaction hash is not a 32-byte 0x-prefixed value")
    return text.lower()


def cli_path() -> str:
    found = shutil.which("genlayer.cmd") or shutil.which("genlayer")
    if not found:
        raise RuntimeError("GenLayer CLI 0.40.0-rc.3 was not found")
    return found


def make_client() -> Any:
    from genlayer_py import create_client
    from genlayer_py.chains import studio_devnet

    if studio_devnet.id != CHAIN_ID or studio_devnet.rpc_urls["default"]["http"][0] != RPC:
        raise RuntimeError("installed genlayer-py chain is not Studio-dev 61997")
    return create_client(chain=studio_devnet)


def journal() -> Any:
    from scripts.transaction_journal import TransactionJournal

    LOCAL_STATE.mkdir(parents=True, exist_ok=True)
    return TransactionJournal(JOURNAL_PATH)


def account_preflight(client: Any, address: str, journal_obj: Any) -> dict[str, object]:
    checksum = client.w3.to_checksum_address(address)
    latest = int(client.get_current_nonce(checksum, "latest"))
    pending = int(client.get_transaction_count(checksum, "pending"))
    balance = int(client.get_balance(checksum, "latest"))
    operations = journal_obj.load()["operations"]
    unresolved = [
        str(name) for name, record in operations.items()
        if isinstance(record, dict) and record.get("state") not in (
            "FINALIZED_EXECUTED", "FINALIZED_EXECUTION_FAILED",
            "CLI_COMMAND_FAILED", "BLOCKED_BEFORE_BROADCAST",
        )
    ]
    return {
        "network": NETWORK,
        "rpc": RPC,
        "chain_id": CHAIN_ID,
        "address": checksum,
        "balance_wei": balance,
        "latest_nonce": latest,
        "pending_nonce": pending,
        "unresolved_journal_operations": unresolved,
    }


def _cli_environment() -> dict[str, str]:
    environment = os.environ.copy()
    # Managed keystore signing is the only permitted signer path here.
    environment.pop("SENTINELX_PRIVATE_KEY", None)
    return environment


def ensure_managed_account() -> None:
    """Pin and verify the existing managed account immediately before a write."""
    use = subprocess.run(
        [cli_path(), "account", "use", MANAGED_ACCOUNT_NAME],
        cwd=ROOT,
        env=_cli_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if use.returncode != 0:
        raise RuntimeError("managed account could not be selected")
    show = subprocess.run(
        [cli_path(), "account", "show", "--account", MANAGED_ACCOUNT_NAME, "--rpc", RPC],
        cwd=ROOT,
        env=_cli_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if show.returncode != 0:
        raise RuntimeError("managed account could not be verified")
    address_match = re.search(r"address:\s*['\"]?(0x[0-9a-fA-F]{40})", show.stdout)
    if not address_match or address_match.group(1).lower() != EXPECTED_DEPLOYER.lower():
        raise RuntimeError("managed account public address does not match the expected deployer")


def _argument(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, bytes):
        return "b#" + value.hex()
    if isinstance(value, (list, dict)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def _fee_json_value(value: Any) -> Any:
    """Render estimator integers as quoted JSON numbers for the RC CLI."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return [_fee_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _fee_json_value(item) for key, item in value.items()}
    return value


def _fee_message_allocations(value: list[Any]) -> list[Any]:
    rendered = _fee_json_value(value)
    if not isinstance(rendered, list):
        raise RuntimeError("fee estimate message allocations are malformed")
    for item in rendered:
        if not isinstance(item, dict):
            raise RuntimeError("fee estimate message allocation is malformed")
        message_type = item.get("messageType")
        if message_type in ("1", 1):
            item["messageType"] = "internal"
        elif message_type in ("0", 0):
            item["messageType"] = "external"
    return rendered


def _with_args(command: list[str], args: list[Any]) -> list[str]:
    if not args:
        return command
    return [*command, "--args", *[_argument(value) for value in args]]


def _cli_command(command: list[str]) -> list[str]:
    """Return a managed CLI command, preserving JSON-looking string args.

    CLI 0.40.0-rc.3 parses every JSON-looking ``--args`` token as a map/list,
    which loses the distinction required by a contract argument whose value
    is itself an exact JSON document.  For that narrow case, invoke the same
    installed CLI entrypoint through a process-local Node shim that makes only
    those ``--args`` object tokens fall through to the CLI's string parser.
    The shim never handles accounts, keychains, or signing material.
    """
    original_args = command[1:]
    scan_command = command
    args_file: Path | None = None
    # Windows process creation and the RC CLI's argument parser both reject
    # large b# hex payloads as command-line arguments. Keep the same CLI and
    # managed keystore path, but let the process-local Node shim load the
    # exact argv vector from a short-lived file. The file contains only the
    # user-supplied public calldata; it never contains credentials.
    if sum(len(value) + 1 for value in original_args) > 6_000:
        handle = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".json", delete=False,
        )
        with handle:
            json.dump(original_args, handle, separators=(",", ":"))
        args_file = Path(handle.name)
        _TEMP_CLI_ARGUMENT_FILES.add(args_file)
        command = [command[0], "--sentinelx-args-file", str(args_file)]
    try:
        args_index = scan_command.index("--args")
    except ValueError:
        args_index = -1
    json_object_args: list[str] = []
    for value in scan_command[args_index + 1 :] if args_index >= 0 else []:
        if not value.startswith("{"):
            continue
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            json_object_args.append(value)
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is required for the managed CLI argument bridge")
    package_dist = Path(cli_path()).resolve().parent / "node_modules" / "genlayer" / "dist" / "index.js"
    if not package_dist.is_file():
        raise RuntimeError("installed GenLayer CLI entrypoint was not found")
    forced = json.dumps(json_object_args, separators=(",", ":"))
    module_url = package_dist.as_uri()
    argv_source = (
        f"JSON.parse(fs.readFileSync({json.dumps(str(args_file))}, 'utf8'))"
        if args_file is not None else "process.argv.slice(1)"
    )
    script = (
        "import fs from 'node:fs';"
        "const originalParse = JSON.parse;"
        f"const forced = new Set({forced});"
        "JSON.parse = (value, ...rest) => forced.has(value)"
        " ? (() => { throw new Error('sentinelx-exact-string-arg'); })()"
        " : originalParse(value, ...rest);"
        # Capture the hash at the managed CLI's eth_sendRawTransaction
        # response boundary.  The CLI itself waits for a receipt before it
        # prints its ordinary label, so a later wait error must not lose the
        # already-broadcast hash.  Only the public hash is emitted; request
        # bodies and signing material are never logged.
        "const originalFetch = globalThis.fetch;"
        "globalThis.fetch = async (...args) => {"
        " let rpcMethod = null;"
        " try { const body = args[1]?.body;"
        "   if (typeof body === 'string') rpcMethod = originalParse(body)?.method ?? null;"
        " } catch (_) {}"
        " const response = await originalFetch(...args);"
        " if (rpcMethod === 'eth_sendRawTransaction') {"
        "   try { const value = (await response.clone().json())?.result;"
        "     if (typeof value === 'string' && /^0x[0-9a-fA-F]{64}$/.test(value))"
        "       process.stdout.write('SENTINELX_MANAGED_TRANSACTION_HASH ' + value + '\\n');"
        "   } catch (_) {}"
        " }"
        " return response;"
        "};"
        # `node -e` omits the script path from argv; the CLI expects the
        # ordinary `[node, script, command, ...]` layout.
        f"process.argv = [process.argv[0], 'genlayer', ...{argv_source}];"
        f"await import({json.dumps(module_url)});"
    )
    # When the original argv vector was moved to the temporary file, the
    # short bridge command contains only its private marker.  That marker is
    # not a Node or GenLayer CLI option and must not be passed after `-e`;
    # `argv_source` above already restores the original CLI argv in-process.
    trailing_args = [] if args_file is not None else command[1:]
    return [node, "--input-type=module", "-e", script, *trailing_args]


def _cleanup_cli_argument_files() -> None:
    for path in list(_TEMP_CLI_ARGUMENT_FILES):
        path.unlink(missing_ok=True)
        _TEMP_CLI_ARGUMENT_FILES.discard(path)


def _run_cli(
    command: list[str], pattern: re.Pattern[str] | None = None,
    on_hash: Any | None = None,
    on_output: Any | None = None,
) -> tuple[str | None, int]:
    """Run one CLI command and capture/persist the first labeled hash."""
    command = _cli_command(command)
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=_cli_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        found: str | None = None
        assert process.stdout is not None
        for line in process.stdout:
            clean = ANSI_RE.sub("", line)
            if on_output is not None:
                on_output(clean)
            if found is None:
                managed_match = re.search(
                    r"SENTINELX_MANAGED_TRANSACTION_HASH[^0-9a-fA-F]*(0x[0-9a-fA-F]{64})",
                    clean,
                    re.IGNORECASE,
                )
                match = managed_match or (pattern.search(clean) if pattern is not None else None)
                if match:
                    found = _hash_text(match.group(1))
                    if on_hash is not None:
                        on_hash(found)
        return_code = process.wait()
        return found, return_code
    finally:
        _cleanup_cli_argument_files()


def _json_from_cli(command: list[str]) -> dict[str, Any]:
    try:
        process = subprocess.run(
            command,
            cwd=ROOT,
            env=_cli_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError("CLI fee estimation failed: " + process.stdout[-1200:])
        for line in reversed(ANSI_RE.sub("", process.stdout).splitlines()):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
        raise RuntimeError("CLI fee estimation returned no JSON object")
    finally:
        _cleanup_cli_argument_files()


def estimate_deploy() -> dict[str, Any]:
    return _json_from_cli([cli_path(), "estimate-fees", "--rpc", RPC, "--json"])


def _capture_cli_estimate(
    *, client: Any, address: str, args: list[Any], estimate: dict[str, Any],
) -> dict[str, Any]:
    """Turn the official capture simulation recommendation into a quote.

    Capture performs authenticated external retrieval and its Python SDK
    simulation can be unavailable even though the installed CLI can quote the
    exact call.  The CLI recommendation is still a measured lower bound, so
    apply the repository-wide 1.25 headroom and re-quote the resulting
    distribution through the SDK's current-policy estimator.  This remains a
    zero-message quote; it is deliberately not used for message-producing
    methods.
    """
    observed = estimate.get("observed")
    distribution = estimate.get("distribution")
    if not isinstance(observed, dict) or not isinstance(distribution, dict):
        raise RuntimeError("CLI capture estimate is missing distribution or observed accounting")
    recommended = observed.get("recommendedExecutionBudgetPerRound")
    if not isinstance(recommended, (str, int)):
        raise RuntimeError("CLI capture estimate is missing recommended execution budget")
    recommended_budget = int(recommended)
    if recommended_budget <= 0:
        raise RuntimeError("CLI capture estimate recommended execution budget is not positive")
    headroom_budget = (recommended_budget * 125 + 99) // 100
    requote_distribution = dict(distribution)
    requote_distribution["executionBudgetPerRound"] = headroom_budget
    requoted = _safe(client.estimate_transaction_fees(requote_distribution))
    if not isinstance(requoted, dict) or not isinstance(requoted.get("distribution"), dict):
        raise RuntimeError("SDK capture re-quote returned no distribution")
    if int(requoted["distribution"].get("totalMessageFees", 0)) != 0:
        raise RuntimeError("capture fallback unexpectedly allocated message fees")
    return {
        **estimate,
        **requoted,
        "estimation_path": "cli_exact_write_recommended_execution_headroom_1_25",
        "capture_recommended_execution_budget": recommended_budget,
        "capture_headroom_execution_budget": headroom_budget,
    }


def _retryable_studio_error(error: Exception) -> bool:
    message = str(error)
    return (
        "Server busy: all" in message
        or "Rate limit exceeded" in message
        or "Too many requests" in message
    )


def _measured_review_message_allocations(
    *, client: Any, governor: str, proposal_id: int,
) -> list[dict[str, Any]] | None:
    """Build the deterministic install/confirmation tree from a live observation.

    Reuse only the current profile's successful ``register_target``
    allocation, which is the same internal consensus path under the same fee
    policy, and bind two measured nodes: execution -> install and install ->
    confirmation. A profile with no such measured observation fails closed
    rather than inventing fee data.
    """
    operations = journal().load()["operations"]
    measured: dict[str, Any] | None = None
    for record in operations.values():
        if not isinstance(record, dict):
            continue
        if record.get("state") != "FINALIZED_EXECUTED":
            continue
        if record.get("method") != "register_with_sentinelx":
            continue
        estimate = record.get("estimate")
        allocations = estimate.get("messageAllocations") if isinstance(estimate, dict) else None
        if allocations is None and isinstance(estimate, dict):
            allocations = estimate.get("message_allocations")
        if isinstance(allocations, list) and len(allocations) == 1 and isinstance(allocations[0], dict):
            measured = dict(allocations[0])
            break
    if measured is None:
        return None

    proposal = read_json(client, governor, "get_proposal", [proposal_id])
    target = proposal.get("target")
    if not isinstance(target, str) or not target:
        raise RuntimeError("review proposal target is missing while building child allocation")
    from genlayer_py.transactions.fees import (
        MESSAGE_ALLOCATION_ROOT_PARENT_INDEX,
        derive_internal_message_call_key,
    )

    if not measured.get("budget") or not measured.get("feeParams"):
        raise RuntimeError("measured internal child allocation is incomplete")
    measured_budget = int(measured["budget"])
    install = dict(measured)
    install["messageType"] = "internal"
    install["onAcceptance"] = False
    install["recipient"] = target
    install["parentIndex"] = MESSAGE_ALLOCATION_ROOT_PARENT_INDEX
    install["callKey"] = derive_internal_message_call_key("install_reviewed_upgrade")
    # The root node funds its own internal-message primary reserve plus the
    # direct confirmation child emitted by install_reviewed_upgrade. Keep one
    # measured primary reserve as explicit capacity headroom for the review
    # path's consensus-message receipt accounting.
    install["budget"] = measured_budget * 3

    confirm = dict(measured)
    confirm["messageType"] = "internal"
    confirm["onAcceptance"] = False
    confirm["recipient"] = governor
    confirm["parentIndex"] = 0
    confirm["callKey"] = derive_internal_message_call_key("confirm_install")
    return [install, confirm]


def estimate_write(address: str, method: str, args: list[Any]) -> dict[str, Any]:
    # This is read-only and uses only the public signer address to build the
    # Studio simulation context.  The CLI owns all signing/broadcasting.
    from types import SimpleNamespace

    client = make_client()
    try:
        estimate = None
        for attempt in range(8):
            try:
                estimate = _safe(client.estimate_transaction_fees_for_write(
                    address,
                    method,
                    account=SimpleNamespace(address=EXPECTED_DEPLOYER),
                    args=args,
                ))
                break
            except Exception as error:
                if not _retryable_studio_error(error) or attempt == 7:
                    raise
                time.sleep(10 if "Rate limit exceeded" in str(error) or "Too many requests" in str(error) else 5)
        if not isinstance(estimate, dict):
            raise RuntimeError("Studio fee estimator returned no object")
        if method == "capture_evidence":
            return _capture_cli_estimate(
                client=client, address=address, args=args, estimate=estimate,
            )
        if method == "execute_reviewed_upgrade":
            existing_allocations = estimate.get("messageAllocations") or estimate.get("message_allocations")
            # Studio may discover the direct install message while omitting
            # the confirmation grandchild. Only a complete two-node tree is
            # safe to submit; replace partial discovery with the measured
            # install -> confirmation allocation tree below.
            if isinstance(existing_allocations, list) and len(existing_allocations) >= 2:
                return estimate
            if len(args) != 1:
                raise RuntimeError("execute_reviewed_upgrade fee quote requires exactly one proposal ID")
            allocations = _measured_review_message_allocations(
                client=client, governor=address, proposal_id=int(args[0]),
            )
            if not allocations:
                raise RuntimeError("execute_reviewed_upgrade emitted no measured internal child allocation")
            requote_options = dict(estimate["distribution"])
            # A zero returned by the direct estimator means "no discovered
            # child"; remove it so the measured allocation becomes the
            # authoritative total message fee in the re-quote.
            requote_options.pop("totalMessageFees", None)
            root_parent_index = (1 << 256) - 1
            requote_options["totalMessageFees"] = sum(
                int(item["budget"])
                for item in allocations
                if int(item.get("parentIndex", root_parent_index)) == root_parent_index
            )
            requote_options["messageAllocations"] = allocations
            requoted = _safe(client.estimate_transaction_fees(requote_options))
            if not isinstance(requoted, dict) or not requoted.get("messageAllocations"):
                raise RuntimeError("execute_reviewed_upgrade child allocation re-quote was incomplete")
            return {
                **estimate,
                **requoted,
                "estimation_path": "measured_finalized_internal_child_allocation",
            }
        return estimate
    except Exception:
        # Use the installed CLI's exact-call simulation when Python's SDK
        # simulator cannot quote a concrete method. Keep all message-
        # producing methods fail-closed on estimator errors, because a generic
        # quote could omit their child-message allocation tree.
        if method in MESSAGE_PRODUCING_METHODS:
            raise
        command = [
            cli_path(), "estimate-fees", str(address), str(method),
            "--rpc", RPC, "--json", "--args", *[_argument(value) for value in args],
        ]
        estimate = _json_from_cli(_cli_command(command))
        if method == "capture_evidence":
            return _capture_cli_estimate(
                client=client, address=address, args=args, estimate=estimate,
            )
        return estimate


def _fee_options(estimate: dict[str, Any]) -> dict[str, Any]:
    distribution = estimate.get("distribution")
    fee_value = estimate.get("feeValue")
    if not isinstance(distribution, dict) or fee_value is None:
        raise RuntimeError("CLI fee estimate is missing distribution or feeValue")
    options: dict[str, Any] = {
        "distribution": _fee_json_value(distribution),
        "feeValue": str(fee_value),
    }
    # Concrete Studio write estimates can include an internal message path.
    # Preserve it verbatim: omitting this allocation makes the CLI submission
    # fail before a transaction hash is returned for parent/child operations.
    allocations = estimate.get("messageAllocations")
    if allocations is None:
        allocations = estimate.get("message_allocations")
    if allocations:
        if not isinstance(allocations, list):
            raise RuntimeError("fee estimate message allocations are malformed")
        options["messageAllocations"] = _fee_message_allocations(allocations)
    return options


def _is_successful(receipt: dict[str, Any]) -> bool:
    from genlayer_py.transactions import is_successful

    return bool(is_successful(receipt))


def inspect_lifecycle(client: Any, tx_hash: str) -> dict[str, Any]:
    for attempt in range(8):
        try:
            value = client.get_transaction_lifecycle(tx_hash)
            break
        except Exception as error:
            # Lifecycle inspection is a read-only reconciliation step.  The
            # Studio-dev RPC applies the same rolling limit to this endpoint
            # as to gen_call, so wait and retry without ever rebroadcasting.
            message = str(error)
            retryable = (
                "Server busy: all" in message
                or "Rate limit exceeded" in message
                or "Too many requests" in message
            )
            if not retryable or attempt == 7:
                raise
            time.sleep(10 if "Rate limit exceeded" in message or "Too many requests" in message else 5)
    return {
        "stored_status": _enum_text(value.get("stored_status_name")),
        "projected_status": _enum_text(value.get("projected_status_name")),
        "resolution_action": _enum_text(value.get("resolution_action_name")),
        "decision_id": value.get("decision_id"),
        "decision_active": bool(value.get("decision_active")),
        "evaluated_at": value.get("evaluated_at"),
    }


def _execution(receipt: dict[str, Any]) -> str:
    return str(
        receipt.get("tx_execution_result_name")
        or receipt.get("txExecutionResultName")
        or receipt.get("execution_result")
        or receipt.get("executionResult")
        or ""
    )


def _contract_address(receipt: dict[str, Any]) -> str | None:
    # Studio stores the deterministic deployed contract address as the
    # transaction recipient (and in the decoded data), while network-style
    # receipts use contract_address/contractAddress.
    value = (
        receipt.get("contract_address")
        or receipt.get("contractAddress")
        or receipt.get("recipient")
        or receipt.get("to_address")
    )
    return str(value) if value else None


def _persisted_hash(journal_obj: Any, operation: str) -> str | None:
    record = journal_obj.load()["operations"].get(operation)
    if not isinstance(record, dict):
        return None
    value = record.get("tx_hash")
    return _hash_text(value) if value else None


def _reconcile_evm(
    *, client: Any, journal_obj: Any, operation: str, evm_hash: str,
) -> dict[str, Any]:
    try:
        receipt = client.w3.eth.wait_for_transaction_receipt(evm_hash, timeout=600)
    except Exception as error:
        journal_obj.update(operation, state="POLLING_ERROR", polling_error=str(error))
        raise
    safe_receipt = _safe(receipt)
    if int(receipt.get("status", 0)) != 1:
        journal_obj.update(operation, state="FINALIZED_EXECUTION_FAILED", evm_receipt=safe_receipt)
        raise RuntimeError("managed CLI finalization EVM transaction failed")
    return journal_obj.update(operation, state="FINALIZED_EXECUTED", evm_receipt=safe_receipt)


def finalize_once(*, client: Any, journal_obj: Any, parent_operation: str, tx_hash: str) -> str:
    operation = f"{parent_operation}.finalize"
    existing = _persisted_hash(journal_obj, operation)
    if existing:
        _reconcile_evm(client=client, journal_obj=journal_obj, operation=operation, evm_hash=existing)
        return existing
    if operation in journal_obj.load()["operations"]:
        raise RuntimeError(f"finalization operation {operation!r} is reserved without a hash")
    journal_obj.reserve_broadcast(operation, transaction_kind="evm", parent_operation=parent_operation, source_tx_hash=tx_hash)
    pattern = re.compile(r"(?:evmTransactionHash|EVM Transaction Hash|Transaction Hash)[^0-9a-fA-F]*(0x[0-9a-fA-F]{64})", re.IGNORECASE)
    found, return_code = _run_cli(
        [cli_path(), "finalize", tx_hash, "--rpc", RPC, "--wallet", "keystore"],
        pattern,
        on_hash=lambda value: journal_obj.record_submission(
            operation, value, transaction_kind="evm", parent_operation=parent_operation,
        ),
    )
    if found is None:
        journal_obj.update(operation, state="BROADCAST_CALL_RAISED", cli_exit_code=return_code)
        raise RuntimeError("managed CLI finalization returned no EVM hash; do not retry")
    if return_code != 0:
        journal_obj.update(operation, state="CLI_COMMAND_FAILED", cli_exit_code=return_code)
    _reconcile_evm(client=client, journal_obj=journal_obj, operation=operation, evm_hash=found)
    return found


def reconcile_genlayer(
    *, client: Any, journal_obj: Any, operation: str,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    tx_hash = _persisted_hash(journal_obj, operation)
    if tx_hash is None:
        raise RuntimeError(f"operation {operation!r} has no persisted transaction hash")
    try:
        receipt = _safe(client.wait_for_transaction_receipt(tx_hash, wait_until="finalized", full_transaction=True))
        lifecycle = inspect_lifecycle(client, tx_hash)
    except Exception as error:
        journal_obj.update(operation, state="POLLING_ERROR", polling_error=str(error))
        raise
    execution = _execution(receipt)
    if lifecycle["stored_status"] != "Finalized" or execution != "FINISHED_WITH_RETURN" or not _is_successful(receipt):
        journal_obj.update(operation, state="FINALIZED_EXECUTION_FAILED", lifecycle=lifecycle, execution_result=execution, receipt=receipt)
        raise RuntimeError(f"{operation} did not reach Finalized + FINISHED_WITH_RETURN")
    children = [_hash_text(value) for value in client.get_triggered_transaction_ids(tx_hash)]
    journal_obj.update(
        operation,
        state="FINALIZED_EXECUTED",
        lifecycle=lifecycle,
        execution_result=execution,
        receipt=receipt,
        triggered_transaction_ids=children,
    )
    return receipt, lifecycle, children


def _reconcile_decided(client: Any, tx_hash: str) -> dict[str, Any]:
    receipt = _safe(client.wait_for_transaction_receipt(tx_hash, wait_until="decided", full_transaction=True))
    lifecycle = inspect_lifecycle(client, tx_hash)
    return {"receipt": receipt, "lifecycle": lifecycle}


def submit(
    *, client: Any, journal_obj: Any, operation: str, kind: str,
    method: str | None = None, address: str | None = None,
    args: list[Any] | None = None, source: Path | None = None,
    fee_metadata: dict[str, object] | None = None,
) -> dict[str, Any]:
    """Estimate, reserve, CLI-broadcast once, persist hash immediately, finalize, and reconcile."""
    existing = _persisted_hash(journal_obj, operation)
    if existing:
        decided = _reconcile_decided(client, existing)
        if decided["lifecycle"]["stored_status"] == "Accepted" and decided["lifecycle"]["resolution_action"] == "Finalize":
            finalize_once(client=client, journal_obj=journal_obj, parent_operation=operation, tx_hash=existing)
        receipt, lifecycle, children = reconcile_genlayer(client=client, journal_obj=journal_obj, operation=operation)
        return {
            "tx_hash": existing,
            "receipt": receipt,
            "lifecycle": lifecycle,
            "children": children,
            "decision": decided,
            "reused": True,
        }
    if operation in journal_obj.load()["operations"]:
        raise RuntimeError(f"operation {operation!r} is reserved without a hash; manual reconciliation required")
    preflight = account_preflight(client, EXPECTED_DEPLOYER, journal_obj)
    if int(str(preflight["latest_nonce"])) != int(str(preflight["pending_nonce"])):
        raise RuntimeError("latest and pending nonce differ; unknown pending activity blocks writes")
    if preflight["unresolved_journal_operations"]:
        raise RuntimeError("unresolved local transaction journal blocks writes")
    values = args or []
    estimate = estimate_deploy() if source is not None else estimate_write(str(address), str(method), values)
    fee_options = _fee_options(estimate)
    # The CLI has no write/deploy --account option in this RC.  Pin the
    # existing managed account at the last safe point before invoking it.
    ensure_managed_account()
    metadata: dict[str, object] = {
        "network": NETWORK,
        "rpc": RPC,
        "chain_id": CHAIN_ID,
        "fee_observation_kind": kind,
        "method": method,
        "address": address,
        "estimate": _safe(estimate),
        "fee_options": _safe(fee_options),
        **(fee_metadata or {}),
    }
    journal_obj.reserve_broadcast(operation, **metadata)
    command: list[str]
    if source is not None:
        command = [
            cli_path(), "deploy", "--contract", str(source), "--rpc", RPC,
            "--fees", json.dumps(fee_options, separators=(",", ":")),
            "--wallet", "keystore",
        ]
        command = _with_args(command, values)
    else:
        command = [
            cli_path(), "write", str(address), str(method), "--rpc", RPC,
            "--fees", json.dumps(fee_options, separators=(",", ":")),
            "--wallet", "keystore",
        ]
        command = _with_args(command, values)
    # The RC CLI may render the label through a spinner, which can insert
    # carriage returns/ANSI control sequences between the label and value.
    # Only a labeled deployment/write hash is trusted; arbitrary 32-byte values
    # in fee reports, call keys, or error details are never transaction IDs.
    pattern = re.compile(r"(?:Deployment|Write)\s+Transaction\s+Hash[^0-9a-fA-F]*(0x[0-9a-fA-F]{64})", re.IGNORECASE)
    cli_output: list[str] = []
    found, return_code = _run_cli(
        command,
        pattern,
        on_hash=lambda value: journal_obj.record_submission(operation, value),
        on_output=lambda line: cli_output.append(line[-1000:]),
    )
    if found is None:
        journal_obj.update(
            operation,
            state="BROADCAST_CALL_RAISED",
            cli_exit_code=return_code,
            cli_output_tail="".join(cli_output)[-4000:],
        )
        raise RuntimeError(f"CLI {kind} broadcast returned no transaction hash; do not retry")
    if return_code != 0:
        journal_obj.update(operation, state="CLI_COMMAND_FAILED", cli_exit_code=return_code)
    decided = _reconcile_decided(client, found)
    if decided["lifecycle"]["stored_status"] == "Accepted" and decided["lifecycle"]["resolution_action"] == "Finalize":
        finalize_once(client=client, journal_obj=journal_obj, parent_operation=operation, tx_hash=found)
    receipt, lifecycle, children = reconcile_genlayer(client=client, journal_obj=journal_obj, operation=operation)
    return {
        "tx_hash": found,
        "receipt": receipt,
        "lifecycle": lifecycle,
        "children": children,
        "decision": decided,
        "reused": False,
    }


def finalize_if_needed(*, client: Any, journal_obj: Any, operation: str, tx_hash: str) -> dict[str, Any]:
    decided = _reconcile_decided(client, tx_hash)
    lifecycle = decided["lifecycle"]
    if lifecycle["stored_status"] == "Accepted" and lifecycle["resolution_action"] == "Finalize":
        evm_hash = finalize_once(client=client, journal_obj=journal_obj, parent_operation=operation, tx_hash=tx_hash)
        return {**decided, "evm_finalize_hash": evm_hash}
    return decided


def read(client: Any, address: str, method: str, args: list[Any] | None = None) -> Any:
    from genlayer_py.types.transactions import TransactionHashVariant

    for attempt in range(8):
        try:
            return _safe(
                client.read_contract(
                    client.w3.to_checksum_address(address), method, args=args or [],
                    # Studio's gen_call requires a sender address for read context;
                    # no signing capability or secret is attached to this object.
                    account=SimpleNamespace(address=EXPECTED_DEPLOYER),
                    transaction_hash_variant=TransactionHashVariant.LATEST_FINAL,
                )
            )
        except Exception as error:
            # Studio-dev can temporarily reject all gen_call execution slots
            # while consensus workers drain, and its public RPC can return a
            # rolling request-window limit during a dense readback sequence.
            # Reads are safe to retry; writes deliberately remain
            # single-broadcast in submit().
            message = str(error)
            retryable = (
                "Server busy: all" in message
                or "Rate limit exceeded" in message
                or "Too many requests" in message
            )
            if not retryable or attempt == 7:
                raise
            time.sleep(10 if "Rate limit exceeded" in message or "Too many requests" in message else 5)


def read_json(client: Any, address: str, method: str, args: list[Any] | None = None) -> dict[str, Any]:
    value = read(client, address, method, args)
    if not isinstance(value, str):
        raise RuntimeError(f"{method} did not return JSON text")
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{method} did not return a JSON object")
    return parsed


def track_children(*, client: Any, journal_obj: Any, parent_operation: str, children: list[str], depth: int = 5) -> list[str]:
    if depth <= 0:
        return []
    all_children: list[str] = []
    for index, child_hash in enumerate(children):
        child_operation = f"{parent_operation}.child.{index}"
        existing = _persisted_hash(journal_obj, child_operation)
        if existing is None:
            journal_obj.reserve_broadcast(child_operation, parent_operation=parent_operation)
            journal_obj.record_submission(child_operation, child_hash, parent_operation=parent_operation)
        _, _, grandchildren = reconcile_genlayer(client=client, journal_obj=journal_obj, operation=child_operation)
        all_children.append(child_hash)
        all_children.extend(track_children(client=client, journal_obj=journal_obj, parent_operation=child_operation, children=grandchildren, depth=depth - 1))
    return all_children


def source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
