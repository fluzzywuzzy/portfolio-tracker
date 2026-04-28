function formatPercent(value, digits = 2) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "N/A";
  }
  return `${value.toFixed(digits)}%`;
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
    createSummaryCard("Accounts", String(data.summary.accounts ?? 0)),
    createSummaryCard("Holdings", String(data.summary.holdings ?? 0)),
    createSummaryCard(
      "Published Allocation",
      formatPercent(data.summary.totalAllocationPercent ?? 0, 0)
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

  const purchases = data.recentPurchases ?? [];
  if (purchases.length === 0) {
    const empty = document.createElement("p");
    empty.className = "purchase-empty";
    empty.textContent = "No purchase history available in the current snapshot.";
    root.appendChild(empty);
    return;
  }

  for (const purchase of purchases) {
    const node = template.content.firstElementChild.cloneNode(true);
    node.querySelector(".purchase-name").textContent = purchase.name || "Unknown purchase";
    node.querySelector(".purchase-time").textContent = formatPurchaseTime(purchase.tradeDate);
    node.querySelector(".purchase-impact").textContent =
      `${formatPercent(purchase.portfolioImpactPercent)} of portfolio`;
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

async function loadPortfolio() {
  const response = await fetch("./portfolio.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Could not load portfolio snapshot: ${response.status}`);
  }
  return response.json();
}

async function main() {
  try {
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
