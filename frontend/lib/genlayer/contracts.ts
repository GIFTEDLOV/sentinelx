export const GOVERNOR_METHODS = {
  contractInfo: "contract_info",
  targetPolicy: "get_target_policy",
  targetIds: "get_target_ids",
  targetProposals: "get_target_proposals",
  activeProposal: "get_active_proposal",
  proposal: "get_proposal",
  proposalStatus: "get_proposal_status",
  releaseHistory: "get_release_history",
  policyFingerprint: "get_policy_fingerprint",
  createProposal: "create_proposal",
  reviewProposal: "review_proposal",
} as const;

export const TARGET_METHODS = {
  applicationName: "get_application_name",
  owner: "get_owner",
  governor: "get_upgrade_governor",
  registered: "is_registered_with_sentinelx",
  protectedValue: "get_protected_value",
  valueNonce: "get_value_nonce",
  installedProposal: "get_installed_proposal_id",
  installedCandidateHash: "get_installed_candidate_hash",
  register: "register_with_sentinelx",
  install: "install_reviewed_upgrade",
} as const;
