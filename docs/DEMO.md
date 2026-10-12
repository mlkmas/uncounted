# Demo video script (about 4 minutes)

Record the screen with the dashboard and a terminal side by side. Speak slowly; judges watch many videos.

## 0:00 to 0:30, the problem

*Screen: dashboard, Manavgat record selected, map visible.*

"In summer 2021, wildfires burned through Manavgat, in Antalya, the province hosting COP31. Fires like this, and the fires of war, release huge amounts of greenhouse gases. Almost none of it is counted. Military emissions reporting is voluntary, and wildfire emissions are often left out as natural. And when someone does publish a number, nobody can check it."

## 0:30 to 1:15, the estimate

*Screen: terminal, run `python -m uncounted estimate manavgat-2021`.*

"Uncounted takes NASA satellite fire detections, the exact data frozen and hashed. It converts fire radiative power into burned biomass and then into CO2, methane and nitrous oxide, using published scientific factors. It never gives one fake-precise number: 20,000 Monte Carlo draws give a range."

*Screen: dashboard, point at the big median and the 90% range, then the map.*

## 1:15 to 2:00, the AI part: conflict

*Screen: select the Kherson record, scroll to the peacetime table.*

"For war, the hard question is: which fires are caused by the conflict? Farmers burn fields every summer. So an AI model learns normal fire activity for every grid cell and week from five peacetime years. Fire above that baseline is attributed to the conflict, the same idea as excess mortality. To prove the model is honest, I hide each peacetime year and predict it. Here are the results. And this is a lower bound: it only counts fires, not fuel or reconstruction."

## 2:00 to 3:15, the blockchain part

*Screen: terminal.*

1. `npx hardhat publish-report ...` "The report's hash and range go on chain."
2. Publish the same case again. "If someone tries to count the same fire twice, the contract refuses: one active record per region and period, and the same satellite data can't back two records."
3. `python -m uncounted verify ...` then `npx hardhat attest ...` twice. "An independent verifier re-runs the open pipeline on the published data. The contract only accepts the attestation if they get the exact same hash, and a publisher can't verify itself. After two verifiers, the record is Verified."

*Screen: dashboard, the Verified badge.*

## 3:15 to 3:45, the tamper moment

*Screen: verify panel. Click "Tamper and re-check".*

"Anyone can check a report in their browser. Watch what happens if I change one number, the median. The hash breaks completely. Corrections are possible, but only as a new record that supersedes the old one, so the history always stays visible."

## 3:45 to 4:15, impact

"Who uses this? UN agencies documenting environmental damage, inventory teams checking wildfire emissions, reconstruction funds and insurers that need a number all sides accept. The data is free and global, only hashes go on chain, and any organization can join as a verifier. Uncounted makes the emissions nobody reports impossible to ignore, and impossible to quietly change."

## Recording tips

- Run `scripts/demo-local.sh` once before recording so everything is warm, then reset with real data.
- Use the real-data reports in the video, not the synthetic ones (synthetic records say SYNTHETIC in the name).
- Zoom the browser to 125% so text is readable in the video.
