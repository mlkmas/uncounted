# Uncounted

**An open, verifiable ledger for the emissions nobody reports: wildfires and war.**

Track: **Climate Data & Environmental Monitoring** (IEEE ClimateChain Global Hackathon 2026)

Wildfires and armed conflicts release large amounts of greenhouse gases, yet these emissions are among the least accounted for in climate reporting. Military emissions reporting to the UN climate convention is voluntary, and wildfire emissions are often treated as "natural" and left out of national totals. When numbers do appear, they are hard to check and easy to dispute.

Uncounted turns free satellite data into emission estimates that anyone can reproduce, and anchors every estimate on a blockchain so it cannot be quietly edited, deleted or counted twice.

## How it works

```
NASA FIRMS satellite fires ──► AI baseline model ──► emissions + uncertainty ──► canonical report
                                (conflict only)        (Monte Carlo)               │ sha256
                                                                                   ▼
             anyone re-runs the open pipeline  ◄──── EmissionsLedger smart contract
             and attests "I got the same hash"        (append only, anti double counting)
```

1. **Satellite data.** Active fire detections from NASA FIRMS (VIIRS, 375 m), with fire radiative power (FRP) for every detection. The exact data used is frozen as a snapshot file and hashed.
2. **AI attribution (conflicts).** A gradient-boosted model learns how much fire each grid cell normally produces in each week of the year, from peacetime years (harvest burning, recurring wildfires). In a conflict period, fire activity above that baseline is attributed to the conflict, the same way excess mortality is calculated. The model is validated by hiding each peacetime year and predicting it; the spread of those errors becomes part of the uncertainty.
3. **Emissions with honest uncertainty.** FRP is converted to burned biomass (Wooster et al. 2005), then to CO2, CH4 and N2O with published emission factors, then to CO2e with IPCC AR6 GWP100. 20,000 Monte Carlo draws produce a 5th to 95th percentile range. Numbers are rounded to 3 significant figures; false precision is a red flag for any expert.
4. **Canonical report.** Inputs, parameters, model settings, validation results and outputs go into one canonical JSON file. Its SHA-256 is the `reportHash`.
5. **On chain.** The `EmissionsLedger` contract stores the range, the report hash and the data hash.
   - **Append only.** A correction is a new record that supersedes the old one; history stays visible.
   - **No double counting.** One active record per subject (kind, region, period); the same satellite data cannot back two records; a report hash can be used once.
   - **Independent verification.** Verifiers re-run the open pipeline on the published data and call `attest` with the hash they reproduced. The contract rejects mismatching hashes and self-verification. After a quorum (default 2), the record is Verified. Anyone with contrary evidence can `dispute`, storing the evidence hash on chain.
6. **Dashboard.** A map of hotspots, the range, the peacetime validation table, and an in-browser hash check. Change one number in a report and the hash no longer matches the chain.

## Why a blockchain and not a database

The people who need these numbers do not trust each other: governments involved in a conflict, UN agencies, NGOs, insurers, reconstruction funds, carbon market registries. A database run by any one of them can be edited by that one party. A shared, append-only ledger with independent verifiers gives everyone the same record that nobody controls, and it keeps the full history of corrections. The heavy data stays off chain; only hashes and the headline range go on chain, so it is cheap.

## Cases included

| Case | Kind | Region | Period |
|---|---|---|---|
| `manavgat-2021` | Wildfire | Manavgat area, Antalya, Türkiye (COP31 host province) | 28 Jul to 12 Aug 2021 |
| `kherson-2022` | Conflict | Kherson Oblast, Ukraine, with 2017 to 2021 as peacetime baseline | Mar to Oct 2022 |

Add your own in `cases.json`.

## Quick start

Requirements: Node 18+, Python 3.10+.

```bash
npm install
pip install -e "pipeline[test]"

# 1. data (free key: https://firms.modaps.eosdis.nasa.gov/api/map_key/)
export FIRMS_MAP_KEY=your_key
cd pipeline
python -m uncounted fetch manavgat-2021
python -m uncounted fetch kherson-2022          # baseline years too; a few hundred requests
python -m uncounted estimate manavgat-2021
python -m uncounted estimate kherson-2022
cd ..

# 2. chain (second terminal: npx hardhat node)
npx hardhat deploy-ledger --network localhost
npx hardhat publish-report --report reports/manavgat-2021.json --network localhost
npx hardhat publish-report --report reports/kherson-2022.json --network localhost

# 3. independent verification
(cd pipeline && python -m uncounted verify ../reports/manavgat-2021.json)
npx hardhat attest --id 1 --verification reports/reproduced/manavgat-2021.verification.json --signer 2 --network localhost
npx hardhat attest --id 1 --verification reports/reproduced/manavgat-2021.verification.json --signer 3 --network localhost

# 4. dashboard
python3 -m http.server 8000      # then open http://localhost:8000/web/
```

No FIRMS key yet? `scripts/demo-local.sh` runs the whole flow on clearly labeled synthetic data.

If Hardhat cannot download the Solidity compiler (offline or behind a firewall), prefix commands with `LOCAL_SOLC=1` to use the compiler bundled in `node_modules`.

### Public testnet

```bash
export SEPOLIA_RPC_URL=...            # your RPC endpoint
export PRIVATE_KEYS=0xadmin,0xverifier1,0xverifier2
export VERIFIER_ADDRESSES=0x...,0x...
export PUBLIC_RPC_URL=https://...     # read-only RPC the dashboard can use
export EXPLORER_URL=https://sepolia.etherscan.io
npx hardhat deploy-ledger --network sepolia
npx hardhat publish-report --report reports/manavgat-2021.json --network sepolia
npx hardhat attest --id 1 --verification reports/reproduced/manavgat-2021.verification.json --signer 1 --network sepolia
```

Commit `reports/` and `data/snapshots/` so verifiers can re-run; GitHub Pages can then host the dashboard at `/web/`.

## Tests

```bash
npx hardhat test                      # 16 contract tests
cd pipeline && python -m pytest       # 11 pipeline tests
```

The pipeline tests include a ground-truth check: synthetic background fires plus injected "front line" fires with a known total. The model must recover the injected amount inside its range, and must find little excess in a peacetime year. In the current run, injected fire power was 39,900 MW and the estimate was 34,700 to 49,000 MW (median 42,800).

## Limits (stated, not hidden)

- **Duration model.** Turning instantaneous FRP into energy needs an assumption about how long each detection represents. This is the largest uncertainty, and it is sampled across a wide range. The optional burned-area cross-check (`crosscheck` in `cases.json`) gives an independent estimate to compare against.
- **Conflict estimates are a lower bound.** Only fire emissions above the peacetime baseline are counted. Military fuel use, munitions, destroyed infrastructure and reconstruction are not included.
- **Fuel types.** Vegetation emission factors are used for all fires, including burning buildings and fuel depots.
- **Weather.** The baseline model does not use weather, so an unusually hot or dry year can look like excess. Adding weather features is the next step.
- **Reproducibility.** Results are rounded to 3 significant figures so tiny floating-point differences between machines do not change the hash. Pin the versions in `pipeline/pyproject.toml` when verifying.

## Who would use it

- **UN agencies and researchers** documenting the environmental cost of conflicts and disasters.
- **National inventory teams** checking wildfire emissions against an independent number.
- **Reconstruction funds and insurers** who need an agreed, tamper-evident baseline.
- **Carbon markets and registries** checking whether forest carbon credits burned.

Adoption cost is low: free satellite data, open code, and a contract that only stores hashes and ranges.

## Repository layout

```
contracts/EmissionsLedger.sol   append-only ledger
test/                           contract tests
tasks/ledger.js                 deploy, publish, attest, dispute, list
pipeline/uncounted/             satellite data, AI attribution, emissions, reports
cases.json                      what to estimate
web/index.html                  dashboard
scripts/demo-local.sh           end-to-end demo on synthetic data
```

## Sources for parameters

- Wooster, M. J., et al. (2005). Retrieval of biomass combustion rates and totals from fire radiative power observations. JGR Atmospheres 110, D24311.
- Andreae, M. O., & Merlet, P. (2001). Emission of trace gases and aerosols from biomass burning. Global Biogeochemical Cycles 15(4).
- IPCC (2006). Guidelines for National Greenhouse Gas Inventories, Vol. 4, Ch. 2.
- IPCC (2021). AR6 WG1, Ch. 7 (GWP100).
- NASA FIRMS, VIIRS 375 m active fire product.

## License

MIT
