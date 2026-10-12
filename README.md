# Uncounted

**An open, verifiable ledger for the emissions nobody reports: wildfires and war.**

Track: **Climate Data & Environmental Monitoring** (IEEE ClimateChain Global Hackathon 2026)

Wildfires and armed conflicts release large amounts of greenhouse gases, yet these emissions are among the least accounted for in climate reporting. Military emissions reporting to the UN climate convention is voluntary, and wildfire emissions are often treated as "natural" and left out of national totals. When numbers do appear, they are hard to check and easy to dispute.

Uncounted turns free satellite data into emission estimates that anyone can reproduce, and anchors every estimate on a blockchain so it cannot be quietly edited, deleted or counted twice.

## Results (real NASA satellite data)

| Record | What | Estimate (t CO2e, 90% range) | Status |
|---|---|---|---|
| #1 Wildfire | Manavgat area, Antalya, Türkiye, 28 Jul to 12 Aug 2021 | **0.99 to 2.74 million**, median 1.82 million | Verified |
| #2 Conflict | Kherson Oblast, Ukraine, Mar to Oct 2022 | **112,000 to 756,000**, median 358,000 | Verified |

- **Manavgat cross-check.** A second, independent method (56,663 ha of mapped burned area x IPCC fuel consumption) gives 1.83 to 2.55 million t CO2e. The two methods agree.
- **Kherson.** Of 44,600 MW of fire power observed in the period, about 14,400 MW does not fit any peacetime fire pattern after subtracting peacetime false alarms. The strongest hotspots sit on the 2022 front line (Davydiv Brid sector, Posad-Pokrovske and Chornobaivka, the Oleshky shore of the Dnipro). A simpler independent method (each grid cell against its own peacetime maximum) gives a similar 11,400 MW. This is a lower bound: fuel use, munitions and reconstruction are not counted.

## How it works

```
NASA FIRMS satellite fires ──► AI conflict attribution ──► emissions + uncertainty ──► canonical report
                                (conflict cases)            (Monte Carlo)                │ sha256
                                                                                         ▼
             anyone re-runs the open pipeline  ◄──── EmissionsLedger smart contract
             and attests to the report hash           (append only, anti double counting)
```

1. **Satellite data.** Active fire detections from NASA FIRMS (VIIRS, 375 m), with fire radiative power (FRP) for every detection. The exact data used is frozen as a snapshot file and hashed.
2. **AI attribution (conflicts).** Normal farm burning hides war fires, and peacetime fire activity can vary threefold from year to year, so comparing totals does not work. Instead, a gradient-boosted classifier learns what peacetime fires look like (where, when, day or night, how intense) and estimates, for each conflict-year fire, the share that no peacetime pattern explains. Training is cross-fitted on spatial blocks, so a fire is always scored by a model that never saw its own area. The exact same test is run on every peacetime year; what it flags there is noise and is subtracted. On synthetic data with a known answer, the method recovers about 82% of injected conflict fires and finds almost nothing in peacetime, so it errs on the conservative side.
3. **Emissions with honest uncertainty.** FRP is converted to burned biomass (Wooster et al. 2005), then to CO2, CH4 and N2O with IPCC emission factors, then to CO2e with IPCC AR6 GWP100. 20,000 Monte Carlo draws give a 5th to 95th percentile range. Numbers are rounded to 3 significant figures.
4. **Canonical report.** Inputs, parameters, model settings, validation results and outputs go into one canonical JSON file. Its SHA-256 is the `reportHash`.
5. **On chain.** The `EmissionsLedger` contract stores the range, the report hash and the data hash.
   - **Append only.** A correction is a new record that supersedes the old one; history stays visible.
   - **No double counting.** One active record per subject (kind, region, period); the same satellite data cannot back two records; a report hash can be used once.
   - **Independent verification.** Verifiers re-run the open pipeline on the published data. Inputs must be identical and results must match (bit for bit with the same library versions, or within 5% across different computers). Only then can they `attest`. Publishers cannot verify their own records. After a quorum (default 2) the record is Verified. Anyone with contrary evidence can `dispute`.
6. **Dashboard.** Hotspot map, the range, the peacetime check, the cross-check, and an in-browser hash check. Change one number in a report and the hash no longer matches the chain.

## Why a blockchain and not a database

The people who need these numbers do not trust each other: governments involved in a conflict, UN agencies, NGOs, insurers, reconstruction funds, carbon market registries. A database run by any one of them can be edited by that one party. A shared, append-only ledger with independent verifiers gives everyone the same record that nobody controls, and it keeps the full history of corrections. The heavy data stays off chain; only hashes and the headline range go on chain, so it is cheap.

## Quick start

Requirements: Node 18+, Python 3.10+.

```bash
npm install
pip install -e "pipeline[test]"

# 1. data (free key: https://firms.modaps.eosdis.nasa.gov/api/map_key/)
export FIRMS_MAP_KEY=your_key          # Windows PowerShell: $env:FIRMS_MAP_KEY="your_key"
cd pipeline
python -m uncounted fetch manavgat-2021
python -m uncounted fetch kherson-2022
python -m uncounted estimate manavgat-2021
python -m uncounted estimate kherson-2022
cd ..

# 2. chain (in a second terminal: npx hardhat node)
npx hardhat deploy-ledger --network localhost
npx hardhat publish-report --report reports/manavgat-2021.json --network localhost
npx hardhat publish-report --report reports/kherson-2022.json --network localhost

# 3. independent verification
cd pipeline
python -m uncounted verify ../reports/manavgat-2021.json
python -m uncounted verify ../reports/kherson-2022.json
cd ..
npx hardhat attest --id 1 --verification reports/reproduced/manavgat-2021.verification.json --signer 2 --network localhost
npx hardhat attest --id 1 --verification reports/reproduced/manavgat-2021.verification.json --signer 3 --network localhost
npx hardhat attest --id 2 --verification reports/reproduced/kherson-2022.verification.json --signer 2 --network localhost
npx hardhat attest --id 2 --verification reports/reproduced/kherson-2022.verification.json --signer 3 --network localhost

# 4. dashboard
python -m http.server 8000      # then open http://localhost:8000/web/
```

No FIRMS key? `scripts/demo-local.sh` runs the whole flow on clearly labeled synthetic data. If Hardhat cannot download the Solidity compiler, prefix commands with `LOCAL_SOLC=1`.

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
cd pipeline && python -m pytest       # 13 pipeline tests
```

Pipeline tests include a ground-truth check (synthetic background fires plus injected "front line" fires of known size: the method must recover most of them and put the top hotspot on the front line), a peacetime check (little excess when there is no conflict), unit checks by hand, the burned-area cross-check, the FIRMS download (mocked), and the verification tolerance rules.

## Limits (stated, not hidden)

- **Duration model.** Turning instantaneous FRP into energy needs an assumption about how long each detection represents. This is the largest physical uncertainty and is sampled across a wide range. The burned-area cross-check exists to catch it going wrong; for Manavgat the two agree.
- **Conflict estimates are a lower bound.** Only fires whose pattern differs from peacetime are counted. Extra burning that looks like normal burning, military fuel use, munitions, destroyed infrastructure and reconstruction are not included.
- **Fuel types.** Vegetation emission factors are used for all fires, including burning buildings and fuel depots.
- **Reproducibility.** Machine-learning steps can differ by tiny amounts across operating systems and library versions. Verification therefore requires identical inputs and results within 5% (well inside the stated range). With the versions in `pipeline/requirements-lock.txt` reproduction is usually bit for bit.

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
pipeline/uncounted/             satellite data, AI attribution, emissions, reports, verification
cases.json                      what to estimate
web/index.html                  dashboard
scripts/demo-local.sh           end-to-end demo on synthetic data
docs/                           Devpost text and demo script
```

## Sources

- NASA FIRMS, VIIRS 375 m active fire product.
- Wooster, M. J., et al. (2005). Retrieval of biomass combustion rates and totals from fire radiative power observations. JGR Atmospheres 110, D24311.
- IPCC (2006). Guidelines for National Greenhouse Gas Inventories, Vol. 4, Ch. 2, Tables 2.4 and 2.5; IPCC (2019) Refinement, Table 2.4.
- Andreae, M. O., & Merlet, P. (2001). Emission of trace gases and aerosols from biomass burning. Global Biogeochemical Cycles 15(4).
- IPCC (2021). AR6 WG1, Ch. 7 (GWP100).
- Manavgat burned area: Gebze Technical University, Department of Geomatics Engineering, reported by Bianet (Aug 2021).

## License

MIT