const { expect } = require("chai");
const { ethers } = require("hardhat");

const Kind = { Wildfire: 0, Conflict: 1 };
const Status = { Pending: 0n, Verified: 1n, Disputed: 2n, Superseded: 3n };
const h = (s) => ethers.sha256(ethers.toUtf8Bytes(s));

function input(overrides = {}) {
  return {
    kind: Kind.Wildfire,
    region: "TEST-REGION",
    periodStart: 1627430400n,
    periodEnd: 1628294399n,
    tco2eLow: 100n,
    tco2eCentral: 200n,
    tco2eHigh: 400n,
    reportHash: h("report-1"),
    dataHash: h("data-1"),
    methodVersion: "uncounted-frp/0.1.0",
    reportURI: "reports/test.json",
    ...overrides,
  };
}

describe("EmissionsLedger", function () {
  let ledger, admin, publisher, v1, v2, outsider;

  beforeEach(async () => {
    [admin, publisher, v1, v2, outsider] = await ethers.getSigners();
    ledger = await ethers.deployContract("EmissionsLedger", [admin.address]);
    await ledger.grantRole(await ledger.PUBLISHER_ROLE(), publisher.address);
    await ledger.grantRole(await ledger.VERIFIER_ROLE(), v1.address);
    await ledger.grantRole(await ledger.VERIFIER_ROLE(), v2.address);
    await ledger.grantRole(await ledger.VERIFIER_ROLE(), publisher.address); // to test self-verification
  });

  it("publishes a record and stores every field", async () => {
    await expect(ledger.connect(publisher).publish(input()))
      .to.emit(ledger, "RecordPublished");
    const r = await ledger.getRecord(1);
    expect(r.region).to.equal("TEST-REGION");
    expect(r.tco2eCentral).to.equal(200n);
    expect(r.publisher).to.equal(publisher.address);
    expect(await ledger.status(1)).to.equal(Status.Pending);
  });

  it("only publishers can publish", async () => {
    await expect(ledger.connect(outsider).publish(input()))
      .to.be.revertedWithCustomError(ledger, "AccessControlUnauthorizedAccount");
  });

  it("rejects invalid ranges, periods and empty hashes", async () => {
    await expect(ledger.connect(publisher).publish(input({ tco2eLow: 300n })))
      .to.be.revertedWithCustomError(ledger, "InvalidRange");
    await expect(ledger.connect(publisher).publish(input({ periodEnd: 1n })))
      .to.be.revertedWithCustomError(ledger, "InvalidPeriod");
    await expect(ledger.connect(publisher).publish(input({ dataHash: ethers.ZeroHash })))
      .to.be.revertedWithCustomError(ledger, "EmptyHash");
  });

  describe("double counting protection", () => {
    it("blocks a second active record for the same subject", async () => {
      await ledger.connect(publisher).publish(input());
      await expect(ledger.connect(publisher).publish(input({ reportHash: h("r2"), dataHash: h("d2") })))
        .to.be.revertedWithCustomError(ledger, "DuplicateSubject").withArgs(1n);
    });

    it("blocks the same satellite data backing two records", async () => {
      await ledger.connect(publisher).publish(input());
      await expect(ledger.connect(publisher).publish(input({ region: "OTHER", reportHash: h("r2") })))
        .to.be.revertedWithCustomError(ledger, "DataAlreadyCounted").withArgs(1n);
    });

    it("blocks reusing a report hash", async () => {
      await ledger.connect(publisher).publish(input());
      await expect(ledger.connect(publisher).publish(input({ region: "OTHER", dataHash: h("d2") })))
        .to.be.revertedWithCustomError(ledger, "ReportHashUsed");
    });
  });

  describe("revisions (append only)", () => {
    it("supersedes the old record instead of editing it", async () => {
      await ledger.connect(publisher).publish(input());
      await expect(ledger.connect(publisher).revise(1, input({ reportHash: h("report-1b"), tco2eCentral: 250n })))
        .to.emit(ledger, "RecordRevised").withArgs(1n, 2n);
      expect(await ledger.status(1)).to.equal(Status.Superseded);
      const oldRec = await ledger.getRecord(1);
      expect(oldRec.tco2eCentral).to.equal(200n); // history preserved
      expect(oldRec.supersededBy).to.equal(2n);
      expect((await ledger.getRecord(2)).supersedes).to.equal(1n);
    });

    it("refuses to revise into a different subject", async () => {
      await ledger.connect(publisher).publish(input());
      await expect(ledger.connect(publisher).revise(1, input({ region: "OTHER", reportHash: h("x") })))
        .to.be.revertedWithCustomError(ledger, "SubjectMismatch");
    });

    it("refuses to revise a superseded record", async () => {
      await ledger.connect(publisher).publish(input());
      await ledger.connect(publisher).revise(1, input({ reportHash: h("r2") }));
      await expect(ledger.connect(publisher).revise(1, input({ reportHash: h("r3") })))
        .to.be.revertedWithCustomError(ledger, "RecordNotActive");
    });
  });

  describe("independent verification", () => {
    beforeEach(async () => {
      await ledger.connect(publisher).publish(input());
    });

    it("becomes Verified once the quorum reproduces the exact hash", async () => {
      await ledger.connect(v1).attest(1, h("report-1"));
      expect(await ledger.status(1)).to.equal(Status.Pending);
      await ledger.connect(v2).attest(1, h("report-1"));
      expect(await ledger.status(1)).to.equal(Status.Verified);
    });

    it("rejects an attestation whose reproduced hash differs", async () => {
      await expect(ledger.connect(v1).attest(1, h("tampered")))
        .to.be.revertedWithCustomError(ledger, "HashMismatch");
    });

    it("publishers cannot verify their own record", async () => {
      await expect(ledger.connect(publisher).attest(1, h("report-1")))
        .to.be.revertedWithCustomError(ledger, "SelfVerification");
    });

    it("each verifier votes once", async () => {
      await ledger.connect(v1).attest(1, h("report-1"));
      await expect(ledger.connect(v1).attest(1, h("report-1")))
        .to.be.revertedWithCustomError(ledger, "AlreadyVoted");
      await expect(ledger.connect(v1).dispute(1, h("evidence"), "changed my mind"))
        .to.be.revertedWithCustomError(ledger, "AlreadyVoted");
    });

    it("a dispute marks the record Disputed and stores the evidence hash", async () => {
      await ledger.connect(v1).attest(1, h("report-1"));
      await ledger.connect(v2).dispute(1, h("evidence"), "could not reproduce");
      expect(await ledger.status(1)).to.equal(Status.Disputed);
      expect(await ledger.disputeEvidence(1, v2.address)).to.equal(h("evidence"));
    });

    it("outsiders cannot attest", async () => {
      await expect(ledger.connect(outsider).attest(1, h("report-1")))
        .to.be.revertedWithCustomError(ledger, "AccessControlUnauthorizedAccount");
    });

    it("admin can change the quorum", async () => {
      await ledger.setQuorum(1);
      await ledger.connect(v1).attest(1, h("report-1"));
      expect(await ledger.status(1)).to.equal(Status.Verified);
      await expect(ledger.setQuorum(0)).to.be.revertedWithCustomError(ledger, "InvalidQuorum");
    });
  });
});
