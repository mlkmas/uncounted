// Hardhat tasks that connect the Python pipeline to the EmissionsLedger contract.
//
//   npx hardhat deploy-ledger                    --network localhost
//   npx hardhat publish-report --report reports/manavgat-2021.json [--revise]
//   npx hardhat attest --id 1 --verification reports/reproduced/manavgat-2021.verification.json --signer 2
//   npx hardhat dispute --id 1 --evidence notes.txt --reason "could not reproduce" --signer 3
//   npx hardhat list-records
//
// On localhost the default accounts play the roles: 0 admin, 1 publisher, 2 and 3 verifiers.
// On a public testnet, pass --signer to pick which configured key acts.

const { task, types } = require("hardhat/config");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const ROOT = path.resolve(__dirname, "..");
const STATUS = ["Pending", "Verified", "Disputed", "Superseded"];
const KIND = ["Wildfire", "Conflict", "Other"];
const ROLE_SIGNER = { publisher: 1, verifier: 2 };

function sha256File(p) {
  return "0x" + crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex");
}

function deploymentPath(network) {
  return path.join(ROOT, "deployments", `${network}.json`);
}

async function loadLedger(hre) {
  const file = deploymentPath(hre.network.name);
  if (!fs.existsSync(file)) throw new Error(`No deployment for ${hre.network.name}. Run deploy-ledger first.`);
  const d = JSON.parse(fs.readFileSync(file, "utf8"));
  return hre.ethers.getContractAt("EmissionsLedger", d.address);
}

async function signerFor(hre, role, explicit) {
  const signers = await hre.ethers.getSigners();
  const local = ["hardhat", "localhost"].includes(hre.network.name);
  const idx = explicit ?? (local ? ROLE_SIGNER[role] : 0);
  if (!signers[idx]) throw new Error(`No signer at index ${idx}`);
  return signers[idx];
}

task("deploy-ledger", "Deploy EmissionsLedger and assign roles")
  .addOptionalParam("quorum", "Verifier attestations needed", 2, types.int)
  .setAction(async ({ quorum }, hre) => {
    await hre.run("compile");
    const signers = await hre.ethers.getSigners();
    const admin = signers[0];
    const ledger = await hre.ethers.deployContract("EmissionsLedger", [admin.address]);
    await ledger.waitForDeployment();
    const address = await ledger.getAddress();

    const local = ["hardhat", "localhost"].includes(hre.network.name);
    const publishers = local ? [signers[1].address] : (process.env.PUBLISHER_ADDRESSES || admin.address).split(",");
    const verifiers = local ? [signers[2].address, signers[3].address]
                            : (process.env.VERIFIER_ADDRESSES || "").split(",").filter(Boolean);
    for (const a of publishers) await (await ledger.grantRole(await ledger.PUBLISHER_ROLE(), a.trim())).wait();
    for (const a of verifiers) await (await ledger.grantRole(await ledger.VERIFIER_ROLE(), a.trim())).wait();
    if (quorum !== 2) await (await ledger.setQuorum(quorum)).wait();

    const artifact = await hre.artifacts.readArtifact("EmissionsLedger");
    const net = await hre.ethers.provider.getNetwork();
    const deployment = {
      network: hre.network.name,
      chainId: Number(net.chainId),
      address,
      rpcUrl: local ? "http://127.0.0.1:8545" : (process.env.PUBLIC_RPC_URL || ""),
      explorer: process.env.EXPLORER_URL || "",
      deployedAt: new Date().toISOString(),
      publishers, verifiers, quorum,
      abi: artifact.abi,
    };
    fs.mkdirSync(path.join(ROOT, "deployments"), { recursive: true });
    fs.writeFileSync(deploymentPath(hre.network.name), JSON.stringify(deployment, null, 2));
    fs.writeFileSync(path.join(ROOT, "web", "deployment.json"), JSON.stringify(deployment, null, 2));
    console.log(`EmissionsLedger deployed at ${address} on ${hre.network.name}`);
    console.log(`Publishers: ${publishers.join(", ")}\nVerifiers:  ${verifiers.join(", ") || "(none yet)"}`);
  });

task("publish-report", "Publish a pipeline report to the ledger")
  .addParam("report", "Path to reports/<case>.json")
  .addFlag("revise", "Supersede the active record for the same subject")
  .addOptionalParam("signer", "Signer index", undefined, types.int)
  .setAction(async (args, hre) => {
    const reportPath = path.resolve(ROOT, args.report);
    const chainFile = reportPath.replace(/\.json$/, ".chain.json");
    const input = JSON.parse(fs.readFileSync(chainFile, "utf8"));
    const actual = sha256File(reportPath);
    if (actual !== input.reportHash) throw new Error(`Report file changed since estimate: ${actual} != ${input.reportHash}`);

    const ledger = await loadLedger(hre);
    const signer = await signerFor(hre, "publisher", args.signer);
    const c = ledger.connect(signer);
    const subject = await ledger.subjectKey(input.kind, input.region, input.periodStart, input.periodEnd);
    const active = await ledger.activeBySubject(subject);

    let tx;
    if (active !== 0n) {
      if (!args.revise) throw new Error(`Record ${active} is already active for this subject. Use --revise to supersede it.`);
      tx = await c.revise(active, input);
    } else {
      tx = await c.publish(input);
    }
    const receipt = await tx.wait();
    const ev = receipt.logs.map((l) => { try { return ledger.interface.parseLog(l); } catch { return null; } })
      .find((e) => e && e.name === "RecordPublished");
    const id = Number(ev.args.id);
    const meta = { network: hre.network.name, recordId: id, tx: receipt.hash, block: receipt.blockNumber,
                   reportHash: input.reportHash, revised: active !== 0n ? Number(active) : null };
    fs.writeFileSync(reportPath.replace(/\.json$/, `.onchain.${hre.network.name}.json`), JSON.stringify(meta, null, 2));
    console.log(`Record #${id} ${active !== 0n ? `(supersedes #${active}) ` : ""}published. tx ${receipt.hash}`);
    console.log(`tCO2e ${input.tco2eLow} .. ${input.tco2eCentral} .. ${input.tco2eHigh}`);
  });

task("attest", "As a verifier, attest a record you reproduced with `uncounted verify`")
  .addParam("id", "Record id", undefined, types.int)
  .addParam("verification", "reports/reproduced/<case>.verification.json written by `uncounted verify`")
  .addOptionalParam("signer", "Signer index", undefined, types.int)
  .setAction(async (args, hre) => {
    const ledger = await loadLedger(hre);
    const signer = await signerFor(hre, "verifier", args.signer);
    const v = JSON.parse(fs.readFileSync(path.resolve(ROOT, args.verification), "utf8"));
    if (!["bit_exact", "within_tolerance"].includes(v.verdict)) {
      console.log(`Verification verdict is "${v.verdict}". Not attesting; consider a dispute instead.`);
      process.exitCode = 1;
      return;
    }
    const rec = await ledger.getRecord(args.id);
    const local = sha256File(path.resolve(ROOT, v.report));
    if (local !== v.published_hash || rec.reportHash !== v.published_hash) {
      console.log(`Hash mismatch: on chain ${rec.reportHash}, verified file ${v.published_hash}, file now ${local}.`);
      process.exitCode = 1;
      return;
    }
    await (await ledger.connect(signer).attest(args.id, v.published_hash)).wait();
    console.log(`Attested record #${args.id} (${v.verdict.replace("_", " ")}) as ${signer.address}. ` +
      `Status: ${STATUS[Number(await ledger.status(args.id))]}`);
  });

task("dispute", "As a verifier, dispute a record")
  .addParam("id", "Record id", undefined, types.int)
  .addParam("evidence", "File with your evidence (its sha256 goes on chain)")
  .addParam("reason", "Short reason")
  .addOptionalParam("signer", "Signer index", undefined, types.int)
  .setAction(async (args, hre) => {
    const ledger = await loadLedger(hre);
    const signer = await signerFor(hre, "verifier", args.signer);
    const h = sha256File(path.resolve(ROOT, args.evidence));
    await (await ledger.connect(signer).dispute(args.id, h, args.reason)).wait();
    console.log(`Disputed record #${args.id}. Status: ${STATUS[Number(await ledger.status(args.id))]}`);
  });

task("list-records", "Print every record on the ledger").setAction(async (_, hre) => {
  const ledger = await loadLedger(hre);
  const n = Number(await ledger.recordCount());
  for (let i = 1; i <= n; i++) {
    const r = await ledger.getRecord(i);
    console.log(`#${i} [${STATUS[Number(await ledger.status(i))]}] ${KIND[Number(r.kind)]} ${r.region} ` +
      `${r.tco2eLow}..${r.tco2eCentral}..${r.tco2eHigh} tCO2e  attest=${r.attestations} disputes=${r.disputes}`);
  }
});
