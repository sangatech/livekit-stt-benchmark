const path = require("path");

const appDir = process.env.APP_DIR || path.resolve(__dirname, "../..");
const pythonBin = process.env.PYTHON_BIN || path.join(appDir, "venv/bin/python");
const logDir = process.env.LOG_DIR || path.join(appDir, "logs");

module.exports = {
  apps: [
    {
      name: "stt-dashboard",
      cwd: appDir,
      script: pythonBin,
      args: "-m uvicorn api.benchmark_app:app --host 0.0.0.0 --port 8090",
      interpreter: "none",
      autorestart: true,
      max_restarts: 20,
      restart_delay: 5000,
      out_file: path.join(logDir, "dashboard.log"),
      error_file: path.join(logDir, "dashboard-error.log"),
      log_file: path.join(logDir, "dashboard-combined.log"),
      time: true,
      env: {
        APP_DIR: appDir,
        LOG_DIR: logDir,
        DASHBOARD_HOST: "0.0.0.0",
        DASHBOARD_PORT: "8090",
      },
    },
    {
      name: "stt-agent",
      cwd: appDir,
      script: pythonBin,
      args: "agent.py start",
      interpreter: "none",
      autorestart: true,
      max_restarts: 20,
      restart_delay: 5000,
      out_file: path.join(logDir, "agent.log"),
      error_file: path.join(logDir, "agent-error.log"),
      log_file: path.join(logDir, "agent-combined.log"),
      time: true,
      env: {
        APP_DIR: appDir,
        LOG_DIR: logDir,
        AGENT_MODE: "start",
      },
    },
  ],
};
