#!/usr/bin/env bash
# End-to-end demo on SYNTHETIC data (no FIRMS key needed).
# Starts a local chain, estimates both cases, publishes, reproduces, attests,
# shows the double-counting guard, and serves the dashboard.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Starting local chain"
npx hardhat node > .hardhat-node.log 2>&1 &
NODE_PID=$!
trap 'kill $NODE_PID 2>/dev/null || true' EXIT
for i in $(seq 1 30); do curl -s -X POST -H 'content-type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' http://127.0.0.1:8545 >/dev/null && break; sleep 1; done

echo "== Estimating (synthetic data)"
(cd pipeline
 python3 -m uncounted synthetic manavgat-2021
 python3 -m uncounted estimate manavgat-2021 --synthetic
 python3 -m uncounted synthetic kherson-2022
 python3 -m uncounted estimate kherson-2022 --synthetic)

echo "== Deploying and publishing"
npx hardhat deploy-ledger --network localhost
npx hardhat publish-report --report reports/synthetic-manavgat-2021.json --network localhost
npx hardhat publish-report --report reports/synthetic-kherson-2022.json --network localhost

echo "== Double counting attempt (should be refused)"
npx hardhat publish-report --report reports/synthetic-manavgat-2021.json --network localhost 2>&1 | grep -m1 "already active" || true

echo "== Independent verifiers re-run the pipeline and attest"
(cd pipeline
 python3 -m uncounted verify ../reports/synthetic-manavgat-2021.json
 python3 -m uncounted verify ../reports/synthetic-kherson-2022.json)
npx hardhat attest --id 1 --report reports/reproduced/synthetic-manavgat-2021.json --signer 2 --network localhost
npx hardhat attest --id 1 --report reports/reproduced/synthetic-manavgat-2021.json --signer 3 --network localhost
npx hardhat attest --id 2 --report reports/reproduced/synthetic-kherson-2022.json --signer 2 --network localhost
npx hardhat list-records --network localhost

echo "== Dashboard at http://localhost:8000/web/  (Ctrl+C to stop)"
python3 -m http.server 8000
