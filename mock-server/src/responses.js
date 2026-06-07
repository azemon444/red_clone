export function loginIdpResponse(customerId = "DEMO-USER-001") {
  return {
    access_token: "mock-idp-access-token-demo",
    token_type: "Bearer",
    refresh_token: "mock-idp-refresh-token-demo",
    last_login: new Date().toISOString(),
    customer_id: customerId,
    expires_in: 3600,
    saf_enabled: false,
    pre_assigned: false,
    under_aged: { statusTypeCode: "ADULT" },
  };
}

export function loginLosResponse() {
  return {
    access_token: "mock-los-access-token-demo",
    token_type: "Bearer",
    refresh_token: "mock-los-refresh-token-demo",
    expires_in: "3600",
    scope: ["openid", "profile", "banking"],
    saf_enabled: false,
  };
}

export function emptySuccess() {
  return { data: {}, meta: { code: "0", description: "OK" } };
}

export function emptyList(key = "items") {
  return { [key]: [], total: 0 };
}

export function challengeResponse() {
  return {
    challenge_id: "mock-challenge-001",
    challenge_type: "none",
    status: "completed",
  };
}

export function safInformations(customerInfo) {
  return {
    customerId: customerInfo.customerId,
    firstName: customerInfo.firstName,
    lastName: customerInfo.lastName,
    email: customerInfo.email,
    phone: customerInfo.phone,
    segment: customerInfo.segment,
    language: customerInfo.language,
  };
}

export function safStatus() {
  return { status: "INACTIVE", contactId: "MOCK-CONTACT-001", enabled: false };
}

export function deviceList() {
  return {
    devices: [
      {
        deviceId: "DEVICE-EMULATOR-001",
        name: "Android Emulator",
        model: "Medium Phone",
        os: "Android 16",
        lastAccess: new Date().toISOString(),
        current: true,
      },
    ],
    total: 1,
  };
}

export function notificationsList() {
  return { notifications: [], total: 0, unread: 0 };
}

export function mailboxNotificationsList(notificationsData) {
  const unread = notificationsData.notifications.filter((n) => !n.read).length;
  return {
    ...notificationsData,
    total: notificationsData.notifications.length,
    unread,
  };
}

export function notificationsSummary(notificationsData) {
  const unread = notificationsData.notifications.filter((n) => !n.read).length;
  return {
    _totalCount: notificationsData.notifications.length,
    notificationCount: [
      { category: "transactional", unreadCount: unread, totalCount: notificationsData.notifications.length },
    ],
  };
}

export function standingOrders() {
  return { standingOrders: [], total: 0 };
}

export function consents() {
  return {
    consents: [
      { id: "marketing", accepted: true, required: false },
      { id: "analytics", accepted: true, required: false },
      { id: "terms", accepted: true, required: true },
    ],
  };
}

export function precarioCondicoes() {
  const base = (process.env.PUBLIC_URL || "http://10.0.2.2:9090").replace(/\/$/, "");
  return {
    sections: [
      {
        id: "accounts",
        title: "Contas",
        url: `${base}/demo/precario/accounts`,
      },
      {
        id: "cards",
        title: "Cartões",
        url: `${base}/demo/precario/cards`,
      },
    ],
  };
}

export function resolveHelpList() {
  return { cases: [], total: 0 };
}

export function resolveServiceCatalog() {
  return {
    services: [
      { id: "transfer", name: "Transferências", active: true },
      { id: "cards", name: "Cartões", active: true },
      { id: "payments", name: "Pagamentos", active: true },
    ],
  };
}

export function proxyLookupAssociation() {
  return { associations: [], status: "OK" };
}

export function simulationResult(amount = 50) {
  return {
    simulationId: "SIM-MOCK-001",
    amount: { value: amount, currency: "EUR" },
    fees: { value: 0, currency: "EUR" },
    status: "OK",
  };
}

export function executionResult() {
  return {
    transactionId: `TX-MOCK-${Date.now()}`,
    status: "COMPLETED",
    timestamp: new Date().toISOString(),
  };
}

export function smartStub(path, method) {
  const p = path.toLowerCase();

  if (p.includes("simulation") || p.includes("simulate")) return simulationResult();
  if (p.includes("execution") || p.includes("execute")) return executionResult();
  if (p.includes("transactions")) return emptyList("transactions");
  if (p.includes("payees")) return emptyList("payees");
  if (p.includes("notifications")) return notificationsList();
  if (p.includes("devices")) return deviceList();
  if (p.includes("standing_orders")) return standingOrders();
  if (p.includes("consents")) return consents();
  if (p.includes("mbway")) return { cards: [], notifications: [], contacts: [] };
  if (p.includes("loans")) return { loans: [], payments: [] };
  if (p.includes("providers")) return { providers: [] };
  if (p.includes("scheduled_payments")) return emptyList("scheduledPayments");
  if (p.includes("resolve")) return resolveHelpList();
  if (p.includes("verification") || p.includes("credentials")) return { status: "OK", verified: true };
  if (p.includes("pin") || p.includes("password")) return { status: "OK" };
  if (p.includes("carbon") || p.includes("assertion")) return { token: "mock-assertion-token", valid: true };
  if (p.includes("kyc")) return { status: "OK", result: "PASS" };
  if (p.includes("precario") || p.includes("price")) return precarioCondicoes();
  if (p.includes("proxy_lookup")) return proxyLookupAssociation();
  if (p.includes("retail_mbnet") || p.includes("mbnet")) return { cards: [], virtualCards: [] };
  if (p.includes("minor_channel")) return { authorizations: [], accounts: [], contacts: [] };
  if (p.includes("beneficiary")) return { verified: true, match: "MATCH" };
  if (p.includes("debt_collection") || p.includes("late_payments")) return { references: [], total: 0 };
  if (p.includes("comparaja") || p.includes("leads")) return { status: "OK" };
  if (p.includes("app2app") || p.includes("oba_app2app")) return loginLosResponse();
  if (p.includes("card_token")) return { status: "OK", activated: true };
  if (p.includes("security_darwin")) return loginLosResponse();
  if (p.includes("legacy_service")) {
    const base = (process.env.PUBLIC_URL || "http://10.0.2.2:9090").replace(/\/$/, "");
    return { url: `${base}/demo/legacy` };
  }
  if (p.includes("banks_branches")) return { bic: "BSCHPTPL", bank: "Santander" };
  if (p.includes("special_prices")) return { prices: [] };
  if (p.includes("receipt")) return { receiptId: "RCPT-MOCK-001", url: "" };
  if (p.includes("iban_proof")) return { status: "SENT" };
  if (p.includes("limits")) return { canHire: false, currentLimit: 5000 };
  if (method === "POST" || method === "PUT" || method === "PATCH" || method === "DELETE") {
    return { status: "OK", success: true, ...emptySuccess() };
  }
  return emptySuccess();
}
