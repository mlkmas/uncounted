// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @title Uncounted: an append-only ledger for emissions nobody reports
/// @notice Stores satellite-based emission estimates for wildfires and conflicts.
///         Records are never edited: a correction is a new record that supersedes
///         the old one, so the full history stays public.
///         Anti double counting:
///           1. Only one active record per subject (kind + region + period).
///           2. The same raw satellite data snapshot cannot back two active records.
///           3. A report hash can be recorded only once.
///         Trust: independent verifiers re-run the open pipeline on the same data and
///         attest that they reproduced the exact report hash. Publishers cannot
///         verify their own records.
contract EmissionsLedger is AccessControl {
    bytes32 public constant PUBLISHER_ROLE = keccak256("PUBLISHER_ROLE");
    bytes32 public constant VERIFIER_ROLE = keccak256("VERIFIER_ROLE");

    enum Kind { Wildfire, Conflict, Other }
    enum Status { Pending, Verified, Disputed, Superseded }

    struct RecordInput {
        Kind kind;
        string region;          // human readable, e.g. "TR-07 Manavgat"
        uint64 periodStart;     // unix seconds (UTC)
        uint64 periodEnd;       // unix seconds (UTC), inclusive end of period
        uint64 tco2eLow;        // 5th percentile, tonnes CO2e
        uint64 tco2eCentral;    // median, tonnes CO2e
        uint64 tco2eHigh;       // 95th percentile, tonnes CO2e
        bytes32 reportHash;     // sha256 of the canonical JSON report
        bytes32 dataHash;       // sha256 of the raw satellite data snapshot
        string methodVersion;   // e.g. "uncounted-frp/0.1.0"
        string reportURI;       // where the full report and data can be fetched
    }

    struct Record {
        Kind kind;
        string region;
        uint64 periodStart;
        uint64 periodEnd;
        uint64 tco2eLow;
        uint64 tco2eCentral;
        uint64 tco2eHigh;
        bytes32 reportHash;
        bytes32 dataHash;
        string methodVersion;
        string reportURI;
        address publisher;
        uint64 publishedAt;
        uint256 supersedes;     // 0 if this is an original record
        uint256 supersededBy;   // 0 while active
        uint32 attestations;
        uint32 disputes;
    }

    uint256 public recordCount;
    uint32 public quorum = 2;

    mapping(uint256 => Record) private _records;
    mapping(bytes32 => uint256) public activeBySubject;   // subjectKey => record id
    mapping(bytes32 => uint256) public activeByDataHash;  // dataHash => record id
    mapping(bytes32 => bool) public reportHashUsed;
    mapping(uint256 => mapping(address => bool)) public hasVoted;
    mapping(uint256 => mapping(address => bytes32)) public disputeEvidence;

    event RecordPublished(uint256 indexed id, Kind kind, string region, uint64 tco2eCentral, bytes32 reportHash, address indexed publisher);
    event RecordRevised(uint256 indexed oldId, uint256 indexed newId);
    event RecordAttested(uint256 indexed id, address indexed verifier, uint32 attestations);
    event RecordDisputed(uint256 indexed id, address indexed verifier, bytes32 evidenceHash, string reason);
    event QuorumChanged(uint32 quorum);

    error InvalidPeriod();
    error InvalidRange();
    error EmptyHash();
    error DuplicateSubject(uint256 existingId);
    error DataAlreadyCounted(uint256 existingId);
    error ReportHashUsed();
    error UnknownRecord(uint256 id);
    error RecordNotActive(uint256 id);
    error SubjectMismatch();
    error SelfVerification();
    error AlreadyVoted();
    error HashMismatch(bytes32 expected, bytes32 reproduced);
    error InvalidQuorum();

    constructor(address admin) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
    }

    // ------------------------------------------------------------------ writes

    function publish(RecordInput calldata input) external onlyRole(PUBLISHER_ROLE) returns (uint256 id) {
        bytes32 subject = subjectKey(input.kind, input.region, input.periodStart, input.periodEnd);
        if (activeBySubject[subject] != 0) revert DuplicateSubject(activeBySubject[subject]);
        if (activeByDataHash[input.dataHash] != 0) revert DataAlreadyCounted(activeByDataHash[input.dataHash]);
        id = _store(input, 0);
        activeBySubject[subject] = id;
        activeByDataHash[input.dataHash] = id;
    }

    /// @notice Correct an estimate. The old record stays on chain, marked Superseded.
    function revise(uint256 oldId, RecordInput calldata input) external onlyRole(PUBLISHER_ROLE) returns (uint256 id) {
        Record storage old = _get(oldId);
        if (old.supersededBy != 0) revert RecordNotActive(oldId);
        bytes32 subject = subjectKey(input.kind, input.region, input.periodStart, input.periodEnd);
        if (subject != subjectKey(old.kind, old.region, old.periodStart, old.periodEnd)) revert SubjectMismatch();
        uint256 dataOwner = activeByDataHash[input.dataHash];
        if (dataOwner != 0 && dataOwner != oldId) revert DataAlreadyCounted(dataOwner);

        id = _store(input, oldId);
        old.supersededBy = id;
        delete activeByDataHash[old.dataHash];
        activeBySubject[subject] = id;
        activeByDataHash[input.dataHash] = id;
        emit RecordRevised(oldId, id);
    }

    /// @notice A verifier re-ran the pipeline on the published data and got this hash.
    function attest(uint256 id, bytes32 reproducedHash) external onlyRole(VERIFIER_ROLE) {
        Record storage r = _vote(id);
        if (reproducedHash != r.reportHash) revert HashMismatch(r.reportHash, reproducedHash);
        r.attestations += 1;
        emit RecordAttested(id, msg.sender, r.attestations);
    }

    /// @notice A verifier could not reproduce the record or has contrary evidence.
    function dispute(uint256 id, bytes32 evidenceHash, string calldata reason) external onlyRole(VERIFIER_ROLE) {
        if (evidenceHash == bytes32(0)) revert EmptyHash();
        Record storage r = _vote(id);
        r.disputes += 1;
        disputeEvidence[id][msg.sender] = evidenceHash;
        emit RecordDisputed(id, msg.sender, evidenceHash, reason);
    }

    function setQuorum(uint32 q) external onlyRole(DEFAULT_ADMIN_ROLE) {
        if (q == 0) revert InvalidQuorum();
        quorum = q;
        emit QuorumChanged(q);
    }

    // ------------------------------------------------------------------- reads

    function getRecord(uint256 id) external view returns (Record memory) {
        return _get(id);
    }

    function status(uint256 id) public view returns (Status) {
        Record storage r = _get(id);
        if (r.supersededBy != 0) return Status.Superseded;
        if (r.disputes > 0) return Status.Disputed;
        if (r.attestations >= quorum) return Status.Verified;
        return Status.Pending;
    }

    function subjectKey(Kind kind, string memory region, uint64 periodStart, uint64 periodEnd) public pure returns (bytes32) {
        return keccak256(abi.encode(kind, region, periodStart, periodEnd));
    }

    // ---------------------------------------------------------------- internal

    function _store(RecordInput calldata input, uint256 supersedes) private returns (uint256 id) {
        if (input.periodEnd < input.periodStart) revert InvalidPeriod();
        if (!(input.tco2eLow <= input.tco2eCentral && input.tco2eCentral <= input.tco2eHigh)) revert InvalidRange();
        if (input.reportHash == bytes32(0) || input.dataHash == bytes32(0)) revert EmptyHash();
        if (reportHashUsed[input.reportHash]) revert ReportHashUsed();
        reportHashUsed[input.reportHash] = true;

        id = ++recordCount;
        Record storage r = _records[id];
        r.kind = input.kind;
        r.region = input.region;
        r.periodStart = input.periodStart;
        r.periodEnd = input.periodEnd;
        r.tco2eLow = input.tco2eLow;
        r.tco2eCentral = input.tco2eCentral;
        r.tco2eHigh = input.tco2eHigh;
        r.reportHash = input.reportHash;
        r.dataHash = input.dataHash;
        r.methodVersion = input.methodVersion;
        r.reportURI = input.reportURI;
        r.publisher = msg.sender;
        r.publishedAt = uint64(block.timestamp);
        r.supersedes = supersedes;
        emit RecordPublished(id, input.kind, input.region, input.tco2eCentral, input.reportHash, msg.sender);
    }

    function _vote(uint256 id) private returns (Record storage r) {
        r = _get(id);
        if (r.supersededBy != 0) revert RecordNotActive(id);
        if (r.publisher == msg.sender) revert SelfVerification();
        if (hasVoted[id][msg.sender]) revert AlreadyVoted();
        hasVoted[id][msg.sender] = true;
    }

    function _get(uint256 id) private view returns (Record storage r) {
        if (id == 0 || id > recordCount) revert UnknownRecord(id);
        r = _records[id];
    }
}
