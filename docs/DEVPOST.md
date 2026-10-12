# Devpost submission text

Copy each section into the matching Devpost field. Replace the bracketed parts after you run the real data.

## Project name

Uncounted: a verifiable ledger for the emissions nobody reports

## Elevator pitch (one line)

Satellite AI estimates the emissions of wildfires and war, and a blockchain makes every estimate reproducible, tamper-proof and impossible to count twice.

## Track alignment

**Climate Data & Environmental Monitoring.** The track asks for reliable, verifiable climate data. Uncounted is a climate data verification platform: it turns fragmented satellite fire data into emission estimates, and gives every estimate an on-chain record that independent verifiers must reproduce before it counts as Verified.

## Inspiration

In summer 2021, wildfires burned through the Manavgat area of Antalya, the province now hosting COP31. Fires like these, and the fires of war, release large amounts of greenhouse gases that almost no climate report counts. Military emissions reporting to the UN climate convention is voluntary, and wildfire emissions are often left out of national totals as "natural". I live in a region affected by conflict, and I wanted a tool that measures this damage in a way no single side controls.

## The problem

Emissions from wildfires and armed conflicts are large, poorly counted and easy to dispute. The data exists (satellites see every major fire) but it is fragmented, the estimates are made by different parties with different methods, and nobody can easily check whether a published number was changed, inflated or counted twice.

## What it does

- Pulls NASA FIRMS satellite fire detections for any region and period, and freezes the exact data as a hashed snapshot.
- For conflicts, an AI model learns normal fire activity from peacetime years and measures the fire activity above that baseline, like excess mortality. It is validated on held-out peacetime years.
- Converts fire radiative power into CO2, CH4 and N2O with published scientific factors, and reports a range (5th to 95th percentile) from 20,000 Monte Carlo draws instead of one false-precision number.
- Writes everything into one canonical report and records its SHA-256 hash and the emissions range on chain.
- Independent verifiers re-run the open pipeline on the same data. The smart contract only accepts their attestation if they reproduce the exact hash, and a publisher cannot verify itself.
- The contract is append only (corrections supersede, history stays) and blocks double counting: one active record per region and period, and the same satellite data cannot back two records.
- A dashboard shows the hotspot map, the range, the peacetime validation, and lets anyone check a report against the chain in their browser.

## How I built it

- **Data:** NASA FIRMS VIIRS 375 m active fires (free API).
- **AI:** scikit-learn gradient boosting (Poisson loss) on cell-week fire power, with leave-one-year-out validation; Monte Carlo uncertainty in NumPy.
- **Science:** Wooster et al. (2005) combustion factor, Andreae & Merlet (2001) / IPCC 2006 emission factors, IPCC AR6 GWP100.
- **Blockchain:** Solidity 0.8.24, OpenZeppelin AccessControl, Hardhat (16 tests), deployed on [Sepolia: contract address].
- **Front end:** a single HTML page with ethers.js, Leaflet and in-browser SHA-256.

## Results

[Fill in after running real data. Suggested sentences:]

- Manavgat wildfires 2021: [p05] to [p95] t CO2e, median [p50].
- Kherson Oblast, Mar to Oct 2022: [share]% of observed fire power was above the peacetime baseline, about [p05] to [p95] t CO2e from conflict-attributable fires alone. This is a lower bound: it excludes fuel use, munitions and reconstruction.
- Peacetime validation: predicted fire activity for held-out years was within [range] of observed.

On a synthetic test with a known injected amount, the model recovered 42,800 MW (range 34,700 to 49,000) against a true 39,900 MW.

## Target users

UN agencies and researchers documenting environmental damage, national inventory teams, reconstruction funds and insurers that need an agreed baseline, and carbon registries checking whether forest credits burned.

## How it scales and how easily it can be adopted

The satellite data is free and global, so any region and period is one entry in a config file. Only hashes and ranges go on chain, so each record costs one small transaction. The pipeline is open source and runs on a laptop. A new organization joins as a verifier with one role grant.

## Challenges

Turning instantaneous satellite fire power into total energy needs an assumption about fire duration. Instead of hiding it, I sample it across a wide range, report it in the uncertainty, and support an independent burned-area cross-check. Making the pipeline reproducible bit for bit, so independent verifiers can get the exact same hash, required canonical JSON and rounding to meaningful precision.

## What's next

Weather features in the baseline model, Sentinel-2 burned-area mapping as a second independent method, emission factors for non-vegetation fuels, and inviting research groups to act as verifiers.

## Built with

python, scikit-learn, numpy, pandas, solidity, hardhat, openzeppelin, ethers.js, leaflet, nasa-firms
