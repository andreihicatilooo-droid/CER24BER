import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const port = Number(process.env.PORT || 8092);
const apiBase = (process.env.CEER_API_BASE || "http://127.0.0.1:8089").replace(/\/$/, "");

app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));

app.get("/health", (_req, res) => {
  res.json({ status: "ok", apiBase });
});

app.get("/api/state/:gameId", async (req, res) => {
  const gameId = req.params.gameId;
  const playerId = req.query.player_id;
  const url = new URL(`${apiBase}/api/durak/${gameId}`);
  if (playerId) {
    url.searchParams.set("player_id", String(playerId));
  }

  try {
    const response = await fetch(url, {
      headers: {
        "X-Telegram-Init-Data": req.headers["x-telegram-init-data"] || "",
      },
    });
    const payload = await response.text();
    res.status(response.status).type(response.headers.get("content-type") || "application/json").send(payload);
  } catch (error) {
    res.status(502).json({ detail: `Durak API is unavailable: ${String(error)}` });
  }
});

app.post("/api/move/:gameId", async (req, res) => {
  const gameId = req.params.gameId;
  try {
    const response = await fetch(`${apiBase}/api/durak/${gameId}/move`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-Init-Data": req.headers["x-telegram-init-data"] || "",
      },
      body: JSON.stringify(req.body || {}),
    });
    const payload = await response.text();
    res.status(response.status).type(response.headers.get("content-type") || "application/json").send(payload);
  } catch (error) {
    res.status(502).json({ detail: `Durak API is unavailable: ${String(error)}` });
  }
});

app.get("/config.js", (_req, res) => {
  res.type("application/javascript");
  res.send(`window.DURAK_NODE_CONFIG = ${JSON.stringify({ apiBase: "" })};`);
});

app.listen(port, () => {
  console.log(`Durak Node app started on http://127.0.0.1:${port}`);
  console.log(`Proxy API base: ${apiBase}`);
});
