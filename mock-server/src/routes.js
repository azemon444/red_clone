import {
  challengeResponse,
  consents,
  deviceList,
  emptyList,
  emptySuccess,
  executionResult,
  loginIdpResponse,
  loginLosResponse,
  mailboxNotificationsList,
  notificationsList,
  notificationsSummary,
  precarioCondicoes,
  proxyLookupAssociation,
  resolveHelpList,
  resolveServiceCatalog,
  safInformations,
  safStatus,
  simulationResult,
  smartStub,
  standingOrders,
} from "./responses.js";
import { registerMicrositeRoutes } from "./microsite.js";
import { publicBase, rewriteLocalUrls } from "./url-utils.js";

export function registerRoutes(app, { dataStore, getCredentials }) {
  const log = (tag, req) => console.log(`[${tag}] ${req.method} ${req.path}`);

  // ── Health ──────────────────────────────────────────────────────────────────
  app.get("/health", (_req, res) => {
    const { demoUsername, demoPassword } = getCredentials();
    res.json({
      status: "ok",
      message: "Santander clone mock API — live data via Admin UI",
      publicUrl: publicBase(),
      admin: `${publicBase()}/admin`,
      login: { username: demoUsername, password: demoPassword },
      endpoints: {
        eeic: "/santander/eeic/*",
        microsite: "/microsite/filesFF/*",
        web: "/web/api/*",
        pfm: "/pfm/*",
        rto: "/santander/eeic/rto_crm/*",
      },
    });
  });

  // ── Public files (microsite) — real bundled assets from patched APK ─────────
  const servePublicProducts = (req, res) => {
    log("microsite", req);
    const lang = req.path.includes("en_") ? "en" : "pt";
    res.json(
      rewriteLocalUrls(
        dataStore.get(lang === "en" ? "public-products-en" : "public-products-pt")
      )
    );
  };

  app.get("/microsite/filesFF/apps/SAN/pt_public_products.json", servePublicProducts);
  app.get("/microsite/filesFF/apps/SAN/en_public_products.json", servePublicProducts);
  app.get("/microsite/filesFF/apps/SAN/public_products.json", servePublicProducts);
  app.get("/microsite/filesFF/apps/SAN/precario_condicoes.json", (_req, res) => {
    res.json(precarioCondicoes());
  });
  registerMicrositeRoutes(app);

  // ── Web API (financial health, CRM, subscriptions) ──────────────────────────
  app.use("/web/api/v1/fhealth", (req, res) => {
    log("fhealth", req);
    res.json(smartStub(req.path, req.method));
  });
  app.use("/web/api/v1/crm", (req, res) => {
    log("crm", req);
    res.json(smartStub(req.path, req.method));
  });
  app.use("/web/api", (req, res) => {
    log("web", req);
    res.json(smartStub(req.path, req.method));
  });

  // ── PFM / subscriptions redirect targets ────────────────────────────────────
  app.use("/pfm", (req, res) => {
    log("pfm", req);
    res.json(smartStub(req.path, req.method));
  });

  // ── RTO CRM ─────────────────────────────────────────────────────────────────
  app.use("/santander/eeic/rto_crm", (req, res) => {
    log("rto", req);
    res.json(emptySuccess());
  });

  // ── Auth / Login ────────────────────────────────────────────────────────────
  app.post("/santander/eeic/idp-channel/oauth/token", (req, res) => {
    const { demoUsername, demoPassword } = getCredentials();
    const customerInfo = dataStore.get("customer-info");
    const { username, password, grant_type } = req.body;
    if (
      username &&
      password &&
      username !== demoUsername &&
      password !== demoPassword
    ) {
      log("login-reject", req);
      return res.status(401).json({
        error: "invalid_grant",
        error_description: `Invalid credentials (use ${demoUsername} / ${demoPassword})`,
      });
    }
    log("login-idp", req);
    if (grant_type === "refresh_token") {
      return res.json(loginIdpResponse(customerInfo.customerId));
    }
    res.json(loginIdpResponse(customerInfo.customerId));
  });

  app.post("/santander/eeic/idp-channel/oauth/challenge", (req, res) => {
    log("challenge", req);
    res.json(challengeResponse());
  });

  app.post("/santander/eeic/idp-channel/oauth/revoke", (req, res) => {
    log("logout", req);
    res.status(204).end();
  });

  app.post("/santander/eeic/oauth-server-channel/oauth/token", (req, res) => {
    log("login-los", req);
    res.json(loginLosResponse());
  });

  const securityDarwinToken = (req, res) => {
    log("corporate", req);
    res.json(loginLosResponse());
  };
  app.post("/santander/eeic/security_darwin/token", securityDarwinToken);
  app.get("/santander/eeic/security_darwin/token", securityDarwinToken);

  // ── App config / alerts ─────────────────────────────────────────────────────
  app.get("/santander/eeic/alert-ribbon-channel", (_req, res) => {
    res.json({ message: "", title: "", messageVariables: [] });
  });

  app.get("/santander/eeic/kyc_diagnostic_result/customers/me", (_req, res) => {
    res.json({ status: "OK", result: "PASS" });
  });

  // ── Global Position (dashboard) ─────────────────────────────────────────────
  app.get("/santander/eeic/global_position_app", (req, res) => {
    log("global-position", req);
    res.json(dataStore.get("global-position"));
  });

  app.get("/santander/eeic/global_position_app/monthly_balance", (_req, res) => {
    res.json(dataStore.get("monthly-balance"));
  });

  app.put("/santander/eeic/global_position_app/view", (req, res) => {
    log("gp-view", req);
    res.json({ status: "OK" });
  });

  // ── Customer ────────────────────────────────────────────────────────────────
  app.get("/santander/eeic/retail_customers_detail", (_req, res) => {
    log("customer", { method: "GET", path: "/retail_customers_detail" });
    res.json(dataStore.get("retail-customer"));
  });

  app.get("/santander/eeic/retail_customers_detail/contacts", (_req, res) => {
    const customerInfo = dataStore.get("customer-info");
    res.json({
      phones: [{ number: customerInfo.phone, type: "MOBILE", primary: true }],
      emails: [{ address: customerInfo.email, primary: true }],
    });
  });

  app.get("/santander/eeic/saf_activation_mgnt/saf/informations", (_req, res) => {
    res.json(safInformations(dataStore.get("customer-info")));
  });

  app.get("/santander/eeic/customer_informations", (_req, res) => {
    res.json(dataStore.get("customer-info"));
  });

  app.get("/santander/eeic/get_customer_informations", (_req, res) => {
    res.json(dataStore.get("customer-info"));
  });

  app.get("/santander/eeic/saf_activation_mgnt/saf/status", (_req, res) => {
    res.json(safStatus());
  });

  app.post("/santander/eeic/saf_activation_mgnt/saf/status", (_req, res) => {
    res.json({ status: "OK", enabled: false });
  });

  app.post("/santander/eeic/saf_activation_mgnt/click/call", (_req, res) => {
    res.json({ status: "OK" });
  });

  // ── Accounts ────────────────────────────────────────────────────────────────
  app.get("/santander/eeic/retail_accounts", (_req, res) => {
    const globalPosition = dataStore.get("global-position");
    res.json({
      accounts: globalPosition.contractsBalances.accounts.accountsList.map(
        (a) => a.accountDataDetail
      ),
    });
  });

  app.get("/santander/eeic/retail_accounts/:id", (req, res) => {
    const globalPosition = dataStore.get("global-position");
    const retailCustomer = dataStore.get("retail-customer");
    const acct = globalPosition.contractsBalances.accounts.accountsList.find(
      (a) => a.accountDataDetail.accountId === req.params.id
    );
    res.json(acct?.accountDataDetail || retailCustomer);
  });

  app.get("/santander/eeic/retail_accounts/:id/transactions", (req, res) => {
    log("account-transactions", req);
    res.json(dataStore.get("account-transactions"));
  });

  app.get("/santander/eeic/retail_accounts/:id/transactions/:txId", (req, res) => {
    const txs = dataStore.get("account-transactions")._transactionsDataList || [];
    const tx = txs.find((t) => t.transactionId === req.params.txId);
    res.json(
      tx || {
        id: req.params.txId,
        date: "2026-06-05",
        description: "Demo transaction",
        amount: -45.32,
        currency: "EUR",
      }
    );
  });

  // ── Cards ───────────────────────────────────────────────────────────────────
  app.get("/santander/eeic/retail_cards_info", (_req, res) => {
    const globalPosition = dataStore.get("global-position");
    res.json({
      cards: globalPosition.contractsBalances.cards.cardList.map(
        (c) => c.cardDataDetail
      ),
    });
  });

  app.get("/santander/eeic/retail_cards_info/:id", (req, res) => {
    const globalPosition = dataStore.get("global-position");
    const card = globalPosition.contractsBalances.cards.cardList.find(
      (c) => c.cardDataDetail.cardId === req.params.id
    );
    res.json(card?.cardDataDetail || {});
  });

  app.get("/santander/eeic/channel_cards/:id/card_transactions", (_req, res) => {
    res.json({
      transactions: [
        {
          id: "CTX-001",
          date: "2026-06-05",
          description: "Galp Energia",
          amount: -62.0,
          currency: "EUR",
        },
      ],
    });
  });

  app.get("/santander/eeic/retail_cards_info/:id/transactions/:txId", (req, res) => {
    res.json({
      id: req.params.txId,
      date: "2026-06-05",
      description: "Demo card transaction",
      amount: -62.0,
      currency: "EUR",
    });
  });

  // ── Payees / transfers / payments ───────────────────────────────────────────
  app.get("/santander/eeic/payees", (_req, res) => {
    res.json(dataStore.get("payees"));
  });

  app.post("/santander/eeic/payees", (_req, res) => {
    res.json({ payeeId: "PAYEE-NEW", status: "created" });
  });

  app.get("/santander/eeic/retail_standing_orders", (_req, res) => {
    res.json(standingOrders());
  });

  app.post("/santander/eeic/retail_instant_payments/simulate_payment", (_req, res) => {
    res.json(simulationResult());
  });

  app.post("/santander/eeic/retail_instant_payments", (_req, res) => {
    res.json(executionResult());
  });

  // ── MB WAY ──────────────────────────────────────────────────────────────────
  app.get("/santander/eeic/mbway/cards", (_req, res) => {
    res.json(dataStore.get("mbway-cards"));
  });

  app.get("/santander/eeic/mbway/contacts", (_req, res) => {
    res.json({ contacts: [] });
  });

  app.get("/santander/eeic/mbway/recent_contacts", (_req, res) => {
    res.json({ contacts: [] });
  });

  app.get("/santander/eeic/mbway/notifications", (_req, res) => {
    res.json(notificationsList());
  });

  app.get("/santander/eeic/mbway/3ds_active_notifications", (_req, res) => {
    res.json({ notifications: [] });
  });

  // ── Notifications mailbox ─────────────────────────────────────────────────────
  app.get("/santander/eeic/v2/notifications_2g", (_req, res) => {
    res.json(mailboxNotificationsList(dataStore.get("mailbox-notifications")));
  });

  app.get("/santander/eeic/notifications/v2/", (_req, res) => {
    res.json(mailboxNotificationsList(dataStore.get("mailbox-notifications")));
  });

  app.get("/santander/eeic/ch_customer_notifications/summary", (_req, res) => {
    res.json(notificationsSummary(dataStore.get("mailbox-notifications")));
  });

  app.post("/santander/eeic/notifications/v2/pushtoken", (_req, res) => {
    res.json({ status: "OK" });
  });

  // ── Device management ───────────────────────────────────────────────────────
  app.get("/santander/eeic/user_device_mgmt/devices", (_req, res) => {
    res.json(deviceList());
  });

  // ── GDPR / consents ─────────────────────────────────────────────────────────
  app.get("/santander/eeic/gdpr_consents_channel/consents", (_req, res) => {
    res.json(consents());
  });

  app.put("/santander/eeic/gdpr_consents_channel/consents", (_req, res) => {
    res.json({ status: "OK" });
  });

  // ── Registry / verification ─────────────────────────────────────────────────
  app.post("/santander/eeic/customer_verification/verify_customer", (_req, res) => {
    res.json({ status: "OK", verified: true });
  });

  app.post("/santander/eeic/customer_verification/validate_verification", (_req, res) => {
    res.json({ status: "OK", valid: true });
  });

  app.post("/santander/eeic/authentication_devices/credentials", (_req, res) => {
    res.json({ status: "OK" });
  });

  // ── Resolve / help ────────────────────────────────────────────────────────────
  app.get("/santander/eeic/channel_customer_case/resolve/customers/0", (_req, res) => {
    res.json(resolveHelpList());
  });

  app.get(
    "/santander/eeic/channel_customer_case/resolve/services",
    (_req, res) => {
      res.json(resolveServiceCatalog());
    }
  );

  app.post("/santander/eeic/channel_customer_case/resolve", (_req, res) => {
    res.json({ caseId: "CASE-MOCK-001", status: "OPEN" });
  });

  // ── Proxy lookup / SPIN ─────────────────────────────────────────────────────
  app.get("/santander/eeic/proxy_lookup_retail/association", (_req, res) => {
    res.json(proxyLookupAssociation());
  });

  app.get("/santander/eeic/proxy_lookup_retail/association_history", (_req, res) => {
    res.json({ history: [] });
  });

  app.get("/santander/eeic/proxy_lookup_retail/active_contacts", (_req, res) => {
    res.json({ contacts: [] });
  });

  // ── Loans ───────────────────────────────────────────────────────────────────
  app.get("/santander/eeic/loans/:id", (_req, res) => {
    res.json({ loanId: _req.params.id, status: "ACTIVE", balance: 15000 });
  });

  app.get("/santander/eeic/loans/:id/payments", (_req, res) => {
    res.json(emptyList("payments"));
  });

  // ── Topups / service payments ───────────────────────────────────────────────
  app.get("/santander/eeic/retail_topups_payments/providers/:id", (_req, res) => {
    res.json({ providers: [{ id: "MEO", name: "MEO" }, { id: "VOD", name: "Vodafone" }] });
  });

  app.post("/santander/eeic/retail_topups_payments/simulation", (_req, res) => {
    res.json(simulationResult());
  });

  app.post("/santander/eeic/retail_topups_payments/execution", (_req, res) => {
    res.json(executionResult());
  });

  app.post("/santander/eeic/retail_service_payments/simulation", (_req, res) => {
    res.json(simulationResult());
  });

  app.post("/santander/eeic/retail_service_payments/execution", (_req, res) => {
    res.json(executionResult());
  });

  app.post("/santander/eeic/retail_state_payments/simulation", (_req, res) => {
    res.json(simulationResult());
  });

  app.post("/santander/eeic/retail_state_payments/execution", (_req, res) => {
    res.json(executionResult());
  });

  // ── App2App / OBA ───────────────────────────────────────────────────────────
  app.use("/santander/eeic/oba_app2app", (req, res) => {
    log("app2app", req);
    res.json(smartStub(req.path, req.method));
  });

  app.use("/santander/eeic/v2/card_token_services", (req, res) => {
    log("card-token", req);
    res.json({ status: "OK", activated: true });
  });

  // ── Pin / identity ──────────────────────────────────────────────────────────
  app.use("/santander/eeic/user_identity_mgmt", (req, res) => {
    log("identity", req);
    res.json(smartStub(req.path, req.method));
  });

  // ── Minor authorizations ────────────────────────────────────────────────────
  app.use("/santander/eeic/minor_channel_authorizations", (req, res) => {
    log("minor", req);
    res.json(smartStub(req.path, req.method));
  });

  // ── MBNet ───────────────────────────────────────────────────────────────────
  app.use("/santander/eeic/retail_mbnet", (req, res) => {
    log("mbnet", req);
    res.json(smartStub(req.path, req.method));
  });

  // ── Catch-all EEIC (must be last for /santander/eeic) ───────────────────────
  app.use("/santander/eeic", (req, res) => {
    log("stub", req);
    res.json(smartStub(req.path, req.method));
  });

  // ── Demo product pages (offline links from public products) ─────────────────
  app.get("/demo/products/:id", (req, res) => {
    res.json({ product: req.params.id, demo: true, message: "Offline demo product page" });
  });

  app.use("/demo", (_req, res) => {
    res.json({ demo: true, status: "ok" });
  });
}
