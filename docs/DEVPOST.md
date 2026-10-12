# Devpost submission text

Copy each section into the matching Devpost field.

## Project name

Uncounted: a verifiable ledger for the emissions nobody reports

## Elevator pitch

Satellite AI measures the emissions of wildfires and war, and a blockchain makes every estimate reproducible, tamper-proof and impossible to count twice.

## Track alignment

**Climate Data & Environmental Monitoring.** The track asks for reliable, verifiable climate data. Uncounted is a climate data verification platform: it turns fragmented satellite fire data into emission estimates, and gives every estimate an on-chain record that independent verifiers must reproduce before it counts as Verified.

## Inspiration

In summer 2021, wildfires burned through the Manavgat area of Antalya, the province now hosting COP31. Fires like these, and the fires of war, release large amounts of greenhouse gases that almost no climate report counts. Military emissions reporting to the UN climate convention is voluntary, and wildfire emissions are often left out of national totals as "natural". I live in a region affected by conflict, and I wanted a tool that measures this damage in a way no single side controls.

## The problem

Emissions from wildfires and armed conflicts are large, poorly counted and easy to dispute. Satellites see every major fire, but the data is fragmented, estimates are made by different parties with different methods, and nobody can easily check whether a published number was changed, inflated or counted twice.

## What it does

- Pulls NASA FIRMS satellite fire detections for any region and period, and freezes the exact data as a hashed snapshot.
- For conflicts, an AI classifier learns what peacetime fires look like (where, when, day or night, how intense) and measures how much conflict-year fire fits no peacetime pattern. The same test on every peacetime year gives the noise level, which is subtracted.
- Converts fire radiative power into CO2, CH4 and N2O with IPCC factors, and reports a range (5th to 95th percentile) from 20,000 Monte Carlo draws instead of one falsely precise number.
- Writes everything into one canonical report and records its SHA-256 hash and the emissions range on chain.
- Independent verifiers re-run the open pipeline on the same data. They can only attest when inputs are identical and results match, and a publisher cannot verify itself.
- The smart contract is append only (corrections supersede, history stays) and blocks double counting: one active record per region and period, and the same satellite data cannot back two records.
- A dashboard shows the hotspot map, the range, the peacetime check and the cross-check, and lets anyone check a report against the chain in their browser. Change one number and the hash breaks.

## Results

- **Manavgat wildfires, Antalya, 2021:** 0.99 to 2.74 million t CO2e, median 1.82 million. An independent burned-area method (56,663 ha mapped by Gebze Technical University x IPCC fuel consumption) gives 1.83 to 2.55 million t. The two methods agree.
- **Kherson Oblast, Ukraine, Mar to Oct 2022:** 112,000 to 756,000 t CO2e, median 358,000, from conflict-attributable fires alone. About 14,400 MW of the 44,600 MW of fire power observed fits no peacetime pattern, and the hotspots line up with the 2022 front line. A simpler independent method gives a similar 11,400 MW. This is a lower bound: fuel use, munitions and reconstruction are not counted.
- Both records are published on chain and Verified by two independent re-runs.
- On synthetic data with a known answer, the AI attribution recovers about 82% of injected conflict fires and finds almost nothing in peacetime years.

## How I built it

- **Data:** NASA FIRMS VIIRS 375 m active fires (free API).
- **AI:** scikit-learn gradient-boosted classifier with spatially cross-fitted density-ratio estimation, calibrated on leave-one-year-out peacetime tests; Monte Carlo uncertainty in NumPy.
- **Science:** Wooster et al. (2005) combustion factor, IPCC 2006 emission factors and fuel consumption, IPCC AR6 GWP100.
- **Blockchain:** Solidity 0.8.24, OpenZeppelin AccessControl, Hardhat.
- **Front end:** a single HTML page with ethers.js, Leaflet and in-browser SHA-256.
- **Tests:** 16 contract tests and 13 pipeline tests, including ground-truth recovery.

## Target users

UN agencies and researchers documenting environmental damage, national inventory teams, reconstruction funds and insurers that need an agreed baseline, and carbon registries checking whether forest credits burned.

## How it scales and how easily it can be adopted

The satellite data is free and global, so any region and period is one entry in a config file. Only hashes and ranges go on chain, so each record costs one small transaction. The pipeline is open source and runs on a laptop. A new organization joins as a verifier with one role grant.

## Challenges

My first conflict method compared total fire activity with a peacetime baseline, and on real data it said zero. Two things hid the war: peacetime fire activity in Kherson varies threefold between years, and in 2022 normal farm burning dropped while front-line fires rose, so the two cancelled out. I replaced it with an AI classifier that looks at the pattern of each fire instead of the total, and found and fixed a cross-fitting flaw that made it recover only 18% of known conflict fires on test data; after the fix it recovers about 82%. Making verification work across Windows and Linux, where machine-learning results differ very slightly, meant requiring identical inputs plus results within 5% instead of a bit-exact match.

## What's next

Weather features in the peacetime model, Sentinel-2 burned-area mapping as a second method for conflicts, emission factors for non-vegetation fuels, a public testnet deployment, and inviting research groups to act as verifiers.

## Built with

python, scikit-learn, numpy, pandas, solidity, hardhat, openzeppelin, ethers.js, leaflet, nasa-firms