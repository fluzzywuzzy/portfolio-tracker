function formatPercent(value, digits = 2) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "N/A";
  }
  return `${value.toFixed(digits)}%`;
}

const APP_CONFIG = window.APP_CONFIG || {};
const subscribeButton = document.getElementById("subscribe-button");
const subscriptionStatus = document.getElementById("subscription-status");

function normalizeSupabaseUrl(value) {
  if (typeof value !== "string") {
    return "";
  }

  let normalized = value.trim().replace(/\/+$/, "");
  if (normalized.endsWith("/rest/v1")) {
    normalized = normalized.slice(0, -"/rest/v1".length);
  }

  return normalized;
}

function formatDate(isoString) {
  if (!isoString) {
    return "Snapshot time unavailable";
  }

  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return "Snapshot time unavailable";
  }

  return `Updated ${date.toLocaleString("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  })} UTC`;
}

function formatPurchaseTime(value) {
  if (!value) {
    return "Time unavailable";
  }

  const date = new Date(value);
  if (!Number.isNaN(date.getTime())) {
    return date.toLocaleString("en-GB", {
      dateStyle: "medium",
      timeStyle: "short",
    });
  }

  return value;
}

function formatOrderType(value) {
  const normalized = typeof value === "string" ? value.trim().toUpperCase() : "";
  if (normalized === "SELL") {
    return "Sell";
  }
  if (normalized === "BUY") {
    return "Buy";
  }
  return "Order";
}

function formatPrice(value, currency) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "Spot price unavailable";
  }

  if (typeof currency === "string" && /^[A-Z]{3}$/.test(currency.trim().toUpperCase())) {
    try {
      return new Intl.NumberFormat("en-GB", {
        style: "currency",
        currency: currency.trim().toUpperCase(),
        maximumFractionDigits: 2,
      }).format(value);
    } catch (_error) {
      // Fall back to plain numeric formatting if the currency code is unsupported.
    }
  }

  return value.toFixed(2);
}

function formatHoldingPeriod(value) {
  if (!Number.isInteger(value) || value < 0) {
    return null;
  }

  if (value >= 90) {
    const months = Math.max(1, Math.round(value / 30));
    return `${months} month${months === 1 ? "" : "s"}`;
  }

  return `${value} day${value === 1 ? "" : "s"}`;
}

function createSummaryCard(label, value) {
  const card = document.createElement("article");
  card.className = "summary-card";

  const labelElement = document.createElement("p");
  labelElement.className = "summary-label";
  labelElement.textContent = label;

  const valueElement = document.createElement("p");
  valueElement.className = "summary-value";
  valueElement.textContent = value;

  card.append(labelElement, valueElement);
  return card;
}

function formatSignedPercent(value, digits = 2) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "N/A";
  }

  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

function performanceClass(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "is-neutral";
  }
  if (value > 0) {
    return "is-positive";
  }
  if (value < 0) {
    return "is-negative";
  }
  return "is-neutral";
}

function renderSummary(data) {
  const summaryRoot = document.getElementById("summary-cards");
  summaryRoot.replaceChildren(
    createSummaryCard("Holdings", String(data.summary.holdings ?? 0)),
    createSummaryCard(
      `Gain Since 1 Jan ${new Date().getFullYear()}`,
      formatSignedPercent(data.summary.ytdPerformancePercent)
    )
  );
}

function renderAccounts(data) {
  const root = document.getElementById("accounts-root");
  const accountTemplate = document.getElementById("account-template");
  const holdingTemplate = document.getElementById("holding-template");

  root.replaceChildren();

  for (const account of data.accounts ?? []) {
    const accountNode = accountTemplate.content.firstElementChild.cloneNode(true);
    accountNode.querySelector(".account-name").textContent = account.accountName;
    accountNode.querySelector(".account-allocation").textContent =
      `${formatPercent(account.allocationPercent)} of portfolio`;

    const holdingsRoot = accountNode.querySelector(".holdings");

    for (const holding of account.holdings ?? []) {
      const holdingNode = holdingTemplate.content.firstElementChild.cloneNode(true);
      holdingNode.querySelector(".holding-name").textContent = holding.name;
      holdingNode.querySelector(".holding-ticker").textContent = holding.ticker || "";
      holdingNode.querySelector(".holding-type").textContent = holding.type || "";
      holdingNode.querySelector(".holding-allocation").textContent =
        `${formatPercent(holding.allocationPercent)} allocation`;

      const performance = holdingNode.querySelector(".holding-performance");
      performance.textContent =
        holding.performancePercent == null
          ? "Total return unavailable"
          : `${formatPercent(holding.performancePercent)} total return`;
      performance.classList.add(performanceClass(holding.performancePercent));

      holdingsRoot.appendChild(holdingNode);
    }

    root.appendChild(accountNode);
  }
}

function renderPurchases(data) {
  const root = document.getElementById("purchases-root");
  const template = document.getElementById("purchase-template");
  root.replaceChildren();

  const purchases = data.recentOrders ?? data.recentPurchases ?? [];
  if (purchases.length === 0) {
    const empty = document.createElement("p");
    empty.className = "purchase-empty";
    empty.textContent = "No buy or sell history available in the current snapshot.";
    root.appendChild(empty);
    return;
  }

  for (const purchase of purchases) {
    const node = template.content.firstElementChild.cloneNode(true);
    node.querySelector(".purchase-name").textContent =
      `${formatOrderType(purchase.orderType)} · ${purchase.name || "Unknown order"}`;
    node.querySelector(".purchase-time").textContent = formatPurchaseTime(purchase.tradeDate);
    node.querySelector(".purchase-price").textContent =
      `Spot price: ${formatPrice(purchase.spotPrice, purchase.priceCurrency)}`;
    node.querySelector(".purchase-impact").textContent =
      `${formatPercent(purchase.portfolioImpactPercent)} of portfolio`;

    const resultNode = node.querySelector(".purchase-result");
    if (purchase.orderType === "SELL" && typeof purchase.sellPerformancePercent === "number") {
      const holdingPeriod = formatHoldingPeriod(purchase.matchedHoldingPeriodDays);
      resultNode.textContent = holdingPeriod
        ? `${formatSignedPercent(purchase.sellPerformancePercent)} in ${holdingPeriod}`
        : formatSignedPercent(purchase.sellPerformancePercent);
      resultNode.classList.add(performanceClass(purchase.sellPerformancePercent));
    } else if (purchase.orderType === "SELL") {
      resultNode.textContent = "no matched buy";
      resultNode.classList.add("is-neutral");
    } else {
      resultNode.remove();
    }

    root.appendChild(node);
  }
}

function renderMeta(data) {
  document.title = data.title || "Portfolio Tracker";
  document.getElementById("page-title").textContent = data.title || "Portfolio Tracker";
  document.getElementById("page-note").textContent =
    data.publicNote || "Percentages only. No monetary values are published.";
  document.getElementById("page-updated").textContent = formatDate(data.generatedAt);
  document.getElementById("page-owner").textContent = data.owner
    ? `Shared by ${data.owner}`
    : "";
}

function setSubscriptionStatus(message) {
  subscriptionStatus.textContent = message;
}

async function parseErrorMessage(response, fallbackMessage) {
  let details = "";

  try {
    const payload = await response.json();
    if (payload && typeof payload === "object") {
      details =
        payload.message || payload.msg || payload.error_description || payload.error || "";
    }
  } catch (_error) {
    // Ignore JSON parsing errors and fall back to the generic message.
  }

  return details ? `${fallbackMessage}: ${details}` : fallbackMessage;
}

function notificationsConfigured() {
  return Boolean(
    normalizeSupabaseUrl(APP_CONFIG.supabaseUrl) &&
      APP_CONFIG.supabaseAnonKey &&
      APP_CONFIG.webPushPublicKey
  );
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = `${base64String}${padding}`.replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let index = 0; index < rawData.length; index += 1) {
    outputArray[index] = rawData.charCodeAt(index);
  }

  return outputArray;
}

async function saveSubscription(subscription) {
  const response = await fetch(
    `${normalizeSupabaseUrl(APP_CONFIG.supabaseUrl)}/rest/v1/push_subscriptions?on_conflict=endpoint`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        apikey: APP_CONFIG.supabaseAnonKey,
        Authorization: `Bearer ${APP_CONFIG.supabaseAnonKey}`,
        Prefer: "resolution=merge-duplicates,return=minimal",
      },
      body: JSON.stringify([
        {
          endpoint: subscription.endpoint,
          subscription,
          user_agent: navigator.userAgent,
          updated_at: new Date().toISOString(),
        },
      ]),
    }
  );

  if (!response.ok) {
    throw new Error(
      await parseErrorMessage(response, `Subscription save failed (${response.status})`)
    );
  }
}

async function clearPushSubscription(subscription) {
  try {
    await subscription.unsubscribe();
  } catch (_error) {
    // Ignore unsubscribe failures; the browser subscription may already be gone.
  }
}

async function ensurePushSubscription() {
  const registration = await navigator.serviceWorker.register("./sw.js");
  let subscription = await registration.pushManager.getSubscription();
  let createdNewSubscription = false;

  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(APP_CONFIG.webPushPublicKey),
    });
    createdNewSubscription = true;
  }

  try {
    await saveSubscription(subscription.toJSON());
  } catch (error) {
    if (subscription && createdNewSubscription) {
      await clearPushSubscription(subscription);
    }
    throw error;
  }

  return subscription;
}

async function refreshSubscriptionUi() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    subscribeButton.disabled = true;
    setSubscriptionStatus("This browser does not support push notifications.");
    return;
  }

  if (!notificationsConfigured()) {
    subscribeButton.disabled = true;
    setSubscriptionStatus("Notifications are not configured for this deployment yet.");
    return;
  }

  if (Notification.permission === "denied") {
    subscribeButton.disabled = true;
    setSubscriptionStatus("Notifications are blocked in this browser.");
    return;
  }

  const registration = await navigator.serviceWorker.register("./sw.js");
  const subscription = await registration.pushManager.getSubscription();

  if (subscription) {
    try {
      await saveSubscription(subscription.toJSON());
    } catch (error) {
      await clearPushSubscription(subscription);
      subscribeButton.textContent = "Enable alerts";
      subscribeButton.disabled = false;
      setSubscriptionStatus(
        error instanceof Error ? error.message : "Could not verify the notification subscription."
      );
      return;
    }

    subscribeButton.textContent = "Alerts enabled";
    subscribeButton.disabled = true;
    setSubscriptionStatus("This browser is subscribed to new order alerts.");
    return;
  }

  subscribeButton.textContent = "Enable alerts";
  subscribeButton.disabled = false;
  setSubscriptionStatus("Allow notifications to get alerted on new orders.");
}

async function setupNotifications() {
  try {
    await refreshSubscriptionUi();
  } catch (error) {
    subscribeButton.disabled = true;
    setSubscriptionStatus(
      error instanceof Error ? error.message : "Could not initialize notifications."
    );
    return;
  }

  subscribeButton.addEventListener("click", async () => {
    subscribeButton.disabled = true;
    setSubscriptionStatus("Requesting notification permission...");

    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setSubscriptionStatus("Notification permission was not granted.");
        subscribeButton.disabled = false;
        return;
      }

      await ensurePushSubscription();
      subscribeButton.textContent = "Alerts enabled";
      setSubscriptionStatus("Notifications enabled for new orders.");
    } catch (error) {
      subscribeButton.textContent = "Enable alerts";
      subscribeButton.disabled = false;
      setSubscriptionStatus(
        error instanceof Error ? error.message : "Could not subscribe to notifications."
      );
    }
  });
}

async function loadPortfolio() {
  const response = await fetch("./portfolio.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Could not load portfolio snapshot: ${response.status}`);
  }
  return response.json();
}

async function main() {
  try {
    await setupNotifications();
    const data = await loadPortfolio();
    renderMeta(data);
    renderSummary(data);
    renderAccounts(data);
    renderPurchases(data);
  } catch (error) {
    document.getElementById("page-note").textContent =
      error instanceof Error ? error.message : "Could not load portfolio snapshot.";
  }
}

main();
