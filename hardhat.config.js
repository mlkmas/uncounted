require("@nomicfoundation/hardhat-toolbox");
const { subtask } = require("hardhat/config");
const { TASK_COMPILE_SOLIDITY_GET_SOLC_BUILD } = require("hardhat/builtin-tasks/task-names");

// Use the solc-js compiler bundled in node_modules when LOCAL_SOLC=1
// (useful offline or behind a firewall). Otherwise Hardhat downloads solc as usual.
if (process.env.LOCAL_SOLC === "1") {
  subtask(TASK_COMPILE_SOLIDITY_GET_SOLC_BUILD, async (args, hre, runSuper) => {
    if (args.solcVersion === "0.8.24") {
      const solc = require("solc");
      return {
        compilerPath: require.resolve("solc/soljson.js"),
        isSolcJs: true,
        version: args.solcVersion,
        longVersion: solc.version(),
      };
    }
    return runSuper();
  });
}

require("./tasks/ledger");

const keys = (process.env.PRIVATE_KEYS || "").split(",").map((k) => k.trim()).filter(Boolean);

module.exports = {
  solidity: { version: "0.8.24", settings: { optimizer: { enabled: true, runs: 200 } } },
  networks: {
    localhost: { url: "http://127.0.0.1:8545" },
    // Public testnet. PRIVATE_KEYS: comma separated, first key is admin and publisher.
    sepolia: { url: process.env.SEPOLIA_RPC_URL || "", accounts: keys },
  },
};
