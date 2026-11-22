// Dashboard: polls /api/status every 1 s and on each Ping click (DESIGN.md 6.6).
// applyStatus() is the only function that writes status to the page.

(function () {
  "use strict";

  const POLL_MS = 1000;
  const STATUS_TEXT = {
    queued: "Queued",
    delivered: "Delivered",
    completed: "Completed",
    expired: "Expired",
    failed: "Failed",
  };
  const IN_FLIGHT = ["queued", "delivered"];

  const $ = (id) => document.getElementById(id);
  const els = {
    boardName: $("board-name"),
    boardOnline: $("board-online"),
    boardSeen: $("board-seen"),
    boardMeta: $("board-meta"),
    pingBtn: $("ping-btn"),
    pingMessage: $("ping-message"),
    pingStatus: $("ping-status"),
    pingBoard: $("ping-board"),
    pingDelivery: $("ping-delivery"),
    pingRtt: $("ping-rtt"),
    pingTime: $("ping-time"),
    connError: $("conn-error"),
  };

  let pingInFlight = false;
  let requesting = false;

  const dash = (v) => (v === null || v === undefined || v === "" ? "—" : String(v));
  const ms = (v) => (typeof v === "number" ? v + " ms" : "—");

  function localTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return isNaN(d) ? "—" : d.toLocaleTimeString();
  }

  function applyStatus(data) {
    const board = data.board;
    if (board) {
      els.boardName.textContent = board.name;
      els.boardOnline.textContent = board.online ? "Online" : "Offline";
      els.boardOnline.classList.toggle("is-on", board.online);
      els.boardOnline.classList.toggle("is-off", !board.online);
      els.boardSeen.textContent = "Last seen " + Math.round(board.last_seen_s) + " s ago";
      const parts = [];
      parts.push("fw " + dash(board.fw));
      parts.push("RSSI " + (typeof board.rssi === "number" ? board.rssi + " dBm" : "—"));
      els.boardMeta.textContent = parts.join(" · ");
    } else {
      els.boardName.textContent = "No board has checked in";
      els.boardOnline.textContent = "Offline";
      els.boardOnline.classList.remove("is-on");
      els.boardOnline.classList.add("is-off");
      els.boardSeen.textContent = "—";
      els.boardMeta.textContent = "—";
    }

    const ping = data.ping;
    if (ping) {
      els.pingStatus.textContent = STATUS_TEXT[ping.status] || dash(ping.status);
      els.pingStatus.dataset.status = ping.status;
      els.pingBoard.textContent = dash(ping.board);
      els.pingDelivery.textContent = ms(ping.delivery_ms);
      els.pingRtt.textContent = ms(ping.round_trip_ms);
      els.pingTime.textContent = localTime(ping.created_at);
      pingInFlight = IN_FLIGHT.includes(ping.status);
    } else {
      pingInFlight = false;
    }
    els.pingBtn.disabled = pingInFlight || requesting;
  }

  async function refresh() {
    try {
      const res = await fetch("/api/status", { cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      applyStatus(await res.json());
      els.connError.hidden = true;
    } catch (err) {
      els.connError.hidden = false;
    }
  }

  async function sendPing() {
    if (pingInFlight || requesting) return;
    requesting = true;
    els.pingBtn.disabled = true;
    els.pingMessage.textContent = "";
    try {
      const res = await fetch("/api/ping", { method: "POST", cache: "no-store" });
      if (res.status === 409) {
        els.pingMessage.textContent = "No board online.";
      } else if (!res.ok) {
        els.pingMessage.textContent = "Ping failed (HTTP " + res.status + ").";
      }
    } catch (err) {
      els.pingMessage.textContent = "Can't reach the server.";
    } finally {
      requesting = false;
      await refresh();
    }
  }

  els.pingBtn.addEventListener("click", sendPing);
  refresh();
  setInterval(refresh, POLL_MS);
})();
